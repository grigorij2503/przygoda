import asyncio
import hashlib
import hmac
import html
import logging
import re
import time
import unicodedata
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import Request

import secrets
import json
from datetime import datetime, timezone

from app.config import UPLOADS_DIR, settings
from app.combat import (
    action_dc,
    build_boss_encounter,
    ensure_boss_encounter,
    infer_action_intent,
    infer_item_damage_power,
    resolve_boss_turn,
    resolve_status_turn,
    status_list,
    status_roll_penalty,
)
from app.database import AsyncSessionLocal, get_db, init_db
from app.dice import resolve_dice_roll
from app.inventory import (
    EQUIPMENT_SLOT_LIMITS,
    equipment_slot_group,
    get_effectively_equipped_items,
    hands_used,
)
from app.map_generator import (
    GENERATOR_VERSION,
    adjacent_node_ids,
    generate_campaign_map,
    serialize_campaign_map,
)
from app.gemini_service import (
    generate_campaign_intro_ai,
    generate_party_prologue_ai,
    generate_scene_image_ai,
    resolve_turn_with_gemini,
)
from app.models import CampaignMap, ChatMessage, Character, GameSession, InventoryItem, NamedLoreEntity, PlayerAction, Turn
from app.schemas import (
    CharacterDto,
    CreateSessionRequest,
    CreateCharacterRequest,
    GenerateImageRequest,
    GenerateIntroRequest,
    GenerateIntroResponse,
    NameEntityRequest,
    PrologueRequest,
    PrologueResponse,
    ResolveTurnRequest,
    SetupScenarioRequest,
    SubmitActionRequest,
    SpendStatPointRequest,
    TriggerNamingRequest,
    TurnDto,
    UpdatePersonalNoteRequest,
    VerifyGmPinRequest,
    VerifyPasswordRequest,
)
from app.websocket_manager import ws_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ttrpg")

BASE_DIR = Path(__file__).resolve().parent.parent

MAX_LEVEL = 25
MAX_BASE_ATTRIBUTE = 12
CHAT_HISTORY_LIMIT = 50
GM_SESSION_COOKIE = "ttrpg_gm_session"
GM_SESSION_TTL_SECONDS = 8 * 60 * 60
GM_UNLOCK_MAX_ATTEMPTS = 5
GM_UNLOCK_WINDOW_SECONDS = 5 * 60
gm_unlock_attempts: dict[str, list[float]] = {}
XP_LEVEL_THRESHOLDS = {1: 0, 2: 300, 3: 750, 4: 1300, 5: 2000}
for target_level in range(6, MAX_LEVEL + 1):
    # Po 5. poziomie koszt awansu rośnie łagodnie: od 725 do 1200 XP.
    XP_LEVEL_THRESHOLDS[target_level] = (
        XP_LEVEL_THRESHOLDS[target_level - 1] + 700 + (target_level - 5) * 25
    )
ITEM_CLAIM_RULES = (
    ("Tarcza", ("tarc", "pawez", "puklerz"), ("tarc", "pawez", "puklerz"), {"shield"}),
    ("Miecz", ("miecz", "szabl", "rapier"), ("miecz", "szabl", "rapier"), {"weapon"}),
    ("Sztylet", ("sztylet", "noz"), ("sztylet", "noz"), {"weapon"}),
    ("Topór", ("topor", "siekier"), ("topor", "siekier"), {"weapon"}),
    ("Łuk", ("luk", "kusz"), ("luk", "kusz"), {"weapon"}),
    ("Kostur", ("kostur", "lask", "rozdzk"), ("kostur", "lask", "rozdzk"), {"weapon"}),
    ("Młot", ("mlot", "bulaw"), ("mlot", "bulaw"), {"weapon"}),
    ("Włócznia", ("wlocz", "oszczep"), ("wlocz", "oszczep"), {"weapon"}),
    ("Zbroja", ("zbroj", "pancerz"), ("zbroj", "pancerz"), {"armor"}),
)
ITEM_CLAIM_VERBS = (
    "uzyw", "wyciag", "dobyw", "zaklad", "chwyt", "trzym", "blokuj",
    "zaslani", "oslani", "bron sie", "atak", "walcz", "strzel", "wystrzel",
    "strzal", "cios", "celuj", "tnij", "tne", "siek", "pchn", "kluj",
    "rzuc", "uderz", "rani", "zabij", "dobij",
)


def create_gm_session_token(expires_at: int) -> str:
    payload = f"gm:{expires_at}"
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{expires_at}.{signature}"


def is_gm_authenticated(request: Request) -> bool:
    token = request.cookies.get(GM_SESSION_COOKIE, "")
    try:
        expires_raw, supplied_signature = token.split(".", 1)
        expires_at = int(expires_raw)
    except (TypeError, ValueError):
        return False
    if expires_at <= int(time.time()):
        return False
    expected_signature = create_gm_session_token(expires_at).split(".", 1)[1]
    return secrets.compare_digest(supplied_signature, expected_signature)


def require_gm(request: Request) -> None:
    if not is_gm_authenticated(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Wymagane odblokowanie Narzędzi MG",
        )
CRAFTING_KEYWORDS = (
    "lacz", "polacz", "wzmacn", "ulepsz", "przekuw", "przerab", "wytwarz",
)
LEGACY_STARTER_ITEM_UPDATES = {
    ("Krasnoludzki Miecz", "Solidne żelazne ostrze"): (
        "Krasnoludzki Miecz",
        "Pewnie leży w dłoni i dodaje siły każdemu cięciu",
    ),
    ("Skórzana Zbroja", "Pancerz ze skóry dzika"): (
        "Skórzana Zbroja",
        "Chroni przed tym, co miało tylko drasnąć",
    ),
    ("Zatrutą Sztylet", "Ciche, zwinne ostrze"): (
        "Zatruty Sztylet",
        "Ciche ostrze do szybkich i precyzyjnych ataków",
    ),
    ("Wytrychy Mistrza", "Zestaw narzędzi włamywacza"): (
        "Wytrychy Mistrza",
        "Otwierają zamki, które miały pozostać zamknięte",
    ),
    ("Runiczny Kostur", "Obejma z kryształem many"): (
        "Runiczny Kostur",
        "Skupia magię i pomaga odczytać najciemniejsze runy",
    ),
    ("Amulet Ognia", "Zwiększa potencjał magiczny"): (
        "Amulet Ognia",
        "Podsyca zaklęcia i odwagę właściciela",
    ),
    ("Srebrzysta Buława", "Oręż i symbol wiary"): (
        "Srebrzysta Buława",
        "Dodaje powagi modlitwom i ciężaru uderzeniom",
    ),
}


async def replace_campaign_map(db: AsyncSession, session: GameSession) -> CampaignMap:
    """Tworzy nową mapę bez modyfikowania tur, postaci ani mechaniki kampanii."""
    seed = secrets.randbits(63)
    layout = generate_campaign_map(seed, session.title or "Wyprawa", session.setting_theme or "Dark Fantasy")
    existing = (
        await db.execute(select(CampaignMap).where(CampaignMap.session_id == session.id))
    ).scalar_one_or_none()
    if existing:
        existing.seed = seed
        existing.generator_version = GENERATOR_VERSION
        existing.layout = layout
        existing.current_node_id = layout["start_node_id"]
        existing.discovered_node_ids = [layout["start_node_id"]]
        existing.updated_at = datetime.now(timezone.utc)
        campaign_map = existing
    else:
        campaign_map = CampaignMap(
            session=session,
            seed=seed,
            generator_version=GENERATOR_VERSION,
            layout=layout,
            current_node_id=layout["start_node_id"],
            discovered_node_ids=[layout["start_node_id"]],
        )
        db.add(campaign_map)
    await db.flush()
    return campaign_map


def build_map_narrator_context(campaign_map: CampaignMap) -> dict:
    """Udostępnia narratorowi wyłącznie bieżący węzeł i legalne sąsiednie przejścia."""
    layout = campaign_map.layout or {}
    current_node_id = campaign_map.current_node_id or layout.get("start_node_id")
    allowed_ids = {current_node_id, *adjacent_node_ids(layout, current_node_id)}
    nodes_by_id = {
        str(node.get("id")): node
        for node in layout.get("nodes", [])
    }
    return {
        "current_node_id": current_node_id,
        "allowed_destinations": [
            {
                "id": node_id,
                "name": nodes_by_id[node_id].get("name", "Lokacja"),
                "type": nodes_by_id[node_id].get("type", "unknown"),
            }
            for node_id in sorted(allowed_ids)
            if node_id in nodes_by_id
        ],
        "visited_locations": [
            {
                "id": node_id,
                "name": nodes_by_id[node_id].get("name", "Lokacja"),
            }
            for node_id in (campaign_map.discovered_node_ids or [])
            if node_id in nodes_by_id
        ],
    }


def apply_map_narrative_update(
    campaign_map: CampaignMap,
    map_update,
    turn_number: int,
) -> None:
    """Waliduje ruch narratora i zapisuje opis odwiedzonego miejsca w JSON mapy."""
    if not map_update:
        return

    layout = json.loads(json.dumps(campaign_map.layout or {}))
    current_node_id = campaign_map.current_node_id or layout.get("start_node_id")
    allowed_ids = {current_node_id, *adjacent_node_ids(layout, current_node_id)}
    requested_node_id = str(map_update.destination_node_id or "").strip()
    destination_node_id = requested_node_id if requested_node_id in allowed_ids else current_node_id
    known_node_ids = {str(node.get("id")) for node in layout.get("nodes", [])}
    if destination_node_id not in known_node_ids:
        return

    discovered = list(campaign_map.discovered_node_ids or [])
    first_visit = destination_node_id not in discovered
    if first_visit:
        discovered.append(destination_node_id)

    for node in layout.get("nodes", []):
        if str(node.get("id")) != destination_node_id:
            continue
        summary = decode_display_text(map_update.location_summary)
        if summary:
            node["exploration_summary"] = summary[:1200]
        elements = [
            decode_display_text(str(element))[:100]
            for element in (map_update.notable_elements or [])[:5]
            if decode_display_text(str(element))
        ]
        if elements:
            node["notable_elements"] = list(dict.fromkeys(elements))
        if first_visit or node.get("discovered_turn") is None:
            node["discovered_turn"] = turn_number
        node["last_visited_turn"] = turn_number
        break

    campaign_map.layout = layout
    campaign_map.current_node_id = destination_node_id
    campaign_map.discovered_node_ids = discovered
    campaign_map.updated_at = datetime.now(timezone.utc)


def apply_custom_location_name(
    campaign_map: CampaignMap,
    custom_name: str,
    named_by: str,
) -> str | None:
    """Przypisuje nazwę z Kroniki do aktualnie odwiedzanego węzła mapy."""
    layout = json.loads(json.dumps(campaign_map.layout or {}))
    current_node_id = campaign_map.current_node_id or layout.get("start_node_id")
    for node in layout.get("nodes", []):
        if str(node.get("id")) != current_node_id:
            continue
        node["system_name"] = node.get("system_name") or node.get("name") or "Lokacja"
        node["custom_name"] = custom_name
        node["named_by"] = named_by
        campaign_map.layout = layout
        campaign_map.updated_at = datetime.now(timezone.utc)
        return current_node_id
    return None


def get_xp_progress(level: int, xp: int) -> dict:
    """Zwraca postęp XP wewnątrz bieżącego poziomu."""
    level_start = XP_LEVEL_THRESHOLDS.get(level, 0)
    next_level_xp = XP_LEVEL_THRESHOLDS.get(level + 1)
    if next_level_xp is None:
        return {
            "xp_progress": 100,
            "xp_progress_current": 0,
            "xp_progress_required": 0,
            "xp_next_level": None,
        }

    required = next_level_xp - level_start
    current = max(0, min(required, xp - level_start))
    return {
        "xp_progress": round((current / required) * 100, 2) if required else 100,
        "xp_progress_current": current,
        "xp_progress_required": required,
        "xp_next_level": level + 1,
    }


def normalize_game_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", (value or "").casefold())
    return "".join(character for character in normalized if not unicodedata.combining(character))


def decode_display_text(value: str | None) -> str:
    """Dekoduje encje zwrócone przez model; UI nadal renderuje wynik bezpiecznie przez x-text."""
    return html.unescape(value or "").replace("\u00a0", " ").strip()


def validate_action_item_claim(action_text: str, inventory: List[InventoryItem]) -> str | None:
    """Blokuje jawne użycie broni lub pancerza, którego postać nie ma albo nie założyła."""
    normalized_action = normalize_game_text(action_text)
    action_clauses = re.split(r"[,.!?;]", normalized_action)
    effectively_equipped_items = get_effectively_equipped_items(inventory)

    for label, claim_aliases, inventory_aliases, item_types in ITEM_CLAIM_RULES:
        claims_item = any(
            any(alias in clause for alias in claim_aliases)
            and any(verb in clause for verb in ITEM_CLAIM_VERBS)
            for clause in action_clauses
        )
        if not claims_item:
            continue

        matching_items = [
            item
            for item in inventory
            if (
                item.item_type in item_types
                or any(alias in normalize_game_text(item.name) for alias in inventory_aliases)
            )
            and (
                item.item_type == "shield"
                or any(
                    alias in normalize_game_text(f"{item.name} {item.description}")
                    for alias in inventory_aliases
                )
            )
        ]
        if not matching_items:
            return f"Nie masz wymaganego przedmiotu: {label}. Zmień opis akcji albo zdobądź go w grze."
        if not any(item in effectively_equipped_items for item in matching_items):
            return f"{label} znajduje się w plecaku, ale nie w aktywnym slocie. Najpierw użyj przycisku „Załóż”."

    return None


def infer_crafting_source_items(
    action_text: str,
    inventory: List[InventoryItem],
) -> list[InventoryItem]:
    """Rozpoznaje posiadane przedmioty wymienione w akcji łączenia lub ulepszania."""
    normalized_action = normalize_game_text(action_text)
    if not any(keyword in normalized_action for keyword in CRAFTING_KEYWORDS):
        return []

    ignored_name_parts = {
        "magicz", "runicz", "starozy", "wzmocn", "krasnol", "mistrz", "ognia", "cienia",
    }
    matched_items = []
    for item in inventory:
        normalized_name = normalize_game_text(item.name)
        if normalized_name in normalized_action:
            matched_items.append(item)
            continue

        meaningful_parts = [
            part
            for part in re.findall(r"[a-z0-9]+", normalized_name)
            if len(part) >= 4 and not any(part.startswith(ignored) for ignored in ignored_name_parts)
        ]
        if any(part[:4] in normalized_action for part in meaningful_parts):
            matched_items.append(item)

    # Automatyczny fallback jest celowo konserwatywny: dwa wymienione składniki
    # jasno wskazują na crafting. Dla ulepszeń jednego przedmiotu źródło zwraca Gemini.
    return matched_items if len(matched_items) >= 2 else []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicjalizacja bazy danych przy starcie
    await init_db()
    logger.info("Baza danych zainicjalizowana.")
    if not settings.GM_PIN:
        logger.warning("GM_PIN nie jest ustawiony. Narzędzia Mistrza Gry pozostaną zablokowane.")
    # Upewnij się, że istnieje domyślna sesja
    async for db in get_db():
        stmt = select(GameSession).where(GameSession.room_code == "kampania-1")
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        if not session:
            new_session = GameSession(
                room_code="kampania-1",
                title="Cienie Nad Przeklętą Kryptą",
                setting_theme="Dark Fantasy / Gotycki Horror",
                campaign_intro=(
                    "Krople lodowatej wody spadają ze sklepienia prastarej krypty, rozbijając się o kamienne płyty. "
                    "Wasza czwórka przekroczyła próg zniszczonych wrót, uciekając przed szalejącą na powierzchni nawałnicą cieni. "
                    "W mroku przed wami rozbrzmiewa metaliczny zgrzyt oręża i ciche, gardłowe warczenie. "
                    "Pochodnia oświetla ołtarz z czarnego obsydianu, na którym spoczywa starożytny relikwiarz, strzeżony przez ożywione kościotrupy strażników."
                ),
                current_turn_number=1,
            )
            db.add(new_session)
            await db.commit()
            await db.refresh(new_session)

            # Utwórz początkową turę
            initial_turn = Turn(
                session_id=new_session.id,
                turn_number=1,
                status="waiting_for_actions",
                gm_narration=new_session.campaign_intro,
                next_turn_prompt="Szkielety unoszą zardzewiałe miecze, a w ich pustych oczodołach płonie błękitny ogień. Co robicie?",
                suggested_actions=[
                    "⚔️ Ścieżka Siły: Bezpośredni atak na szkielety z wykorzystaniem przewagi zaskoczenia.",
                    "🏹 Ścieżka Sprytu: Przyjęcie pozycji obronnej i próba zwabienia strażników w wąskie przejście.",
                    "🔮 Ścieżka Magii/Wiedzy: Zbadanie aury relikwiarza i próba rozproszenia magii ożywiającej kości."
                ],
                image_prompt="Dark fantasy oil painting of four fantasy adventurers entering a Gothic crypt with glowing blue-eyed skeletal guardians, atmospheric torchlight and mist, cinematic composition",
            )
            db.add(initial_turn)
            await db.commit()
            logger.info("Utworzono domyślną sesję gry 'kampania-1'.")
        # Starsze, już rozgrywane kampanie otrzymują mapę bez resetowania ich stanu.
        sessions = (
            await db.execute(select(GameSession).options(selectinload(GameSession.campaign_map)))
        ).scalars().all()
        backfilled_maps = 0
        for existing_session in sessions:
            if existing_session.campaign_map is None:
                await replace_campaign_map(db, existing_session)
                backfilled_maps += 1
        if backfilled_maps:
            await db.commit()
            logger.info("Utworzono mapy dla %s istniejących kampanii.", backfilled_maps)
        # Porządkuje starsze zapisy, w których można było założyć dowolną liczbę
        # przedmiotów. Najnowsze przedmioty zostają w dostępnych slotach.
        characters = (
            await db.execute(select(Character).options(selectinload(Character.inventory)))
        ).scalars().all()
        normalized_items = 0
        migrated_items = 0
        for character in characters:
            for item in character.inventory:
                normalized_item_name = normalize_game_text(item.name)
                if (
                    item.item_type not in {"shield", "consumable"}
                    and any(alias in normalized_item_name for alias in ("tarc", "pawez", "puklerz"))
                ):
                    item.item_type = "shield"
                    item.hands_required = 1
                    migrated_items += 1
                if item.name == "Runiczny Kostur" and item.hands_required != 2:
                    item.hands_required = 2
                    migrated_items += 1
            effective_ids = {
                item.id for item in get_effectively_equipped_items(character.inventory)
            }
            for item in character.inventory:
                if item.is_equipped and item.id not in effective_ids:
                    item.is_equipped = False
                    normalized_items += 1
                legacy_update = LEGACY_STARTER_ITEM_UPDATES.get((item.name, item.description))
                if legacy_update:
                    item.name, item.description = legacy_update
                    migrated_items += 1
        if normalized_items or migrated_items:
            await db.commit()
        if normalized_items:
            logger.info("Przeniesiono %s nadmiarowych przedmiotów do plecaków.", normalized_items)
        if migrated_items:
            logger.info("Zaktualizowano %s starszych przedmiotów do nowego modelu.", migrated_items)
        break
    yield

app = FastAPI(
    title="Gemini TTRPG Master",
    description="Wieloosobowy turowy RPG prowadzony przez Gemini AI z deterministycznymi rzutami kością",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Statyczne pliki
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# --- PWA & Static Root Endpoints ---
@app.get("/manifest.json", include_in_schema=False)
async def serve_manifest():
    manifest_path = BASE_DIR / "app" / "static" / "manifest.json"
    return FileResponse(
        manifest_path,
        media_type="application/manifest+json",
        headers={"Cache-Control": "public, max-age=3600"}
    )

@app.get("/sw.js", include_in_schema=False)
async def serve_service_worker():
    sw_path = BASE_DIR / "app" / "static" / "sw.js"
    return FileResponse(
        sw_path,
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Service-Worker-Allowed": "/"
        }
    )

@app.get("/favicon.ico", include_in_schema=False)
async def serve_favicon():
    fav_path = BASE_DIR / "app" / "static" / "icons" / "favicon.png"
    return FileResponse(fav_path, media_type="image/png")

# --- HTML View ---
@app.get("/", response_class=HTMLResponse)
async def serve_ui(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

# --- Auth & Session Endpoints ---
@app.post("/api/verify-password")
async def verify_password(payload: VerifyPasswordRequest):
    if payload.password == settings.ROOM_PASSWORD:
        return {"success": True, "message": "Autoryzacja pomyślna"}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowe hasło do pokoju gry")


@app.get("/api/admin/status")
async def get_admin_status(request: Request):
    return {"authenticated": is_gm_authenticated(request)}


@app.post("/api/admin/unlock")
async def unlock_admin_tools(payload: VerifyGmPinRequest, response: Response, request: Request):
    if not settings.GM_PIN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PIN Mistrza Gry nie jest skonfigurowany. Ustaw GM_PIN w pliku .env.",
        )

    client_key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    recent_attempts = [
        attempted_at
        for attempted_at in gm_unlock_attempts.get(client_key, [])
        if now - attempted_at < GM_UNLOCK_WINDOW_SECONDS
    ]
    gm_unlock_attempts[client_key] = recent_attempts
    if len(recent_attempts) >= GM_UNLOCK_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Zbyt wiele nieudanych prób. Spróbuj ponownie za kilka minut.",
            headers={"Retry-After": str(GM_UNLOCK_WINDOW_SECONDS)},
        )
    if not secrets.compare_digest(payload.pin, settings.GM_PIN):
        gm_unlock_attempts[client_key].append(now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowy PIN Mistrza Gry",
        )

    gm_unlock_attempts.pop(client_key, None)
    expires_at = int(time.time()) + GM_SESSION_TTL_SECONDS
    response.set_cookie(
        key=GM_SESSION_COOKIE,
        value=create_gm_session_token(expires_at),
        max_age=GM_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return {"success": True, "expires_in": GM_SESSION_TTL_SECONDS}


@app.post("/api/admin/lock")
async def lock_admin_tools(response: Response):
    response.delete_cookie(key=GM_SESSION_COOKIE, path="/", samesite="strict")
    return {"success": True}

@app.get("/api/session")
async def get_current_session(room_code: str = "kampania-1", db: AsyncSession = Depends(get_db)):
    stmt = (
        select(GameSession)
        .where(GameSession.room_code == room_code)
        .options(
            selectinload(GameSession.characters).selectinload(Character.inventory),
            selectinload(GameSession.turns).selectinload(Turn.actions).selectinload(PlayerAction.character),
            selectinload(GameSession.lore_entities),
            selectinload(GameSession.campaign_map),
        )
    )
    res = await db.execute(stmt)
    game_session = res.scalar_one_or_none()
    if not game_session:
        raise HTTPException(status_code=404, detail="Sesja nie została znaleziona")
    session_changed = ensure_boss_encounter(game_session, game_session.characters)
    if game_session.campaign_map is None:
        game_session.campaign_map = await replace_campaign_map(db, game_session)
        session_changed = True
    if session_changed:
        await db.commit()

    current_turn = next(
        (t for t in game_session.turns if t.turn_number == game_session.current_turn_number),
        None,
    )
    submitted_character_ids = [a.character_id for a in current_turn.actions] if current_turn else []

    characters_dto = []
    for c in game_session.characters:
        xp_progress = get_xp_progress(c.level, c.xp)
        characters_dto.append({
            "id": c.id,
            "player_name": c.player_name,
            "name": c.name,
            "character_class": c.character_class,
            "level": c.level,
            "xp": c.xp,
            **xp_progress,
            "current_hp": c.current_hp,
            "max_hp": c.max_hp,
            "strength": c.strength,
            "agility": c.agility,
            "intellect": c.intellect,
            "charisma": c.charisma,
            "unspent_stat_points": c.unspent_stat_points or 0,
            "is_alive": c.is_alive,
            "is_ready": bool(getattr(c, "is_ready", False)),
            "status_effects": status_list(c.status_effects),
            "has_submitted_action": c.id in submitted_character_ids,
            "inventory": [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "item_type": item.item_type,
                    "target_stat": item.target_stat,
                    "stat_bonus": item.stat_bonus,
                    "damage_power": infer_item_damage_power(item),
                    "hands_required": item.hands_required,
                    "is_equipped": item.is_equipped,
                    "quantity": item.quantity,
                }
                for item in c.inventory
            ],
        })

    turns_dto = []
    for t in sorted(game_session.turns, key=lambda x: x.turn_number):
        clean_prompt = decode_display_text(t.next_turn_prompt)
        actions_list = t.suggested_actions if isinstance(t.suggested_actions, list) else []
        if not actions_list and isinstance(t.suggested_actions, str):
            try:
                parsed = json.loads(t.suggested_actions)
                if isinstance(parsed, list):
                    actions_list = parsed
            except Exception:
                pass

        if "Sugerowane ścieżki działania:" in clean_prompt:
            parts = clean_prompt.split("Sugerowane ścieżki działania:", 1)
            clean_prompt = parts[0].strip()
            if not actions_list:
                actions_list = [line.strip() for line in parts[1].strip().split("\n") if line.strip()]

        turns_dto.append({
            "id": t.id,
            "turn_number": t.turn_number,
            "status": t.status,
            "gm_narration": decode_display_text(t.gm_narration),
            "next_turn_prompt": clean_prompt,
            "suggested_actions": actions_list,
            "image_url": t.image_url,
            "is_generating_image": t.is_generating_image,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
            "mechanics_resolved_at": t.mechanics_resolved_at.isoformat() if t.mechanics_resolved_at else None,
            "combat_events": t.combat_events or [],
            "actions": [
                {
                    "id": a.id,
                    "character_id": a.character_id,
                    "character_name": a.character.name if a.character else "Nieznany",
                    "action_text": a.action_text,
                    "intent": a.intent,
                    "target_ref": a.target_ref,
                    "tested_stat": a.tested_stat,
                    "dice_roll_raw": a.dice_roll_raw,
                    "stat_modifier": a.stat_modifier,
                    "item_modifier": a.item_modifier,
                    "status_modifier": a.status_modifier or 0,
                    "dice_total": a.dice_total,
                    "dc": a.dc,
                    "outcome_tier": a.outcome_tier,
                    "gm_individual_summary": a.gm_individual_summary,
                    "damage_dealt": a.damage_dealt or 0,
                    "damage_roll": a.damage_roll or 0,
                    "damage_base": a.damage_base or 0,
                    "damage_reduction": a.damage_reduction or 0,
                    "hp_delta": a.hp_delta or 0,
                    "xp_gained": a.xp_gained or 0,
                }
                for a in t.actions
            ],
        })

    return {
        "session_id": game_session.id,
        "room_code": game_session.room_code,
        "title": game_session.title,
        "setting_theme": game_session.setting_theme,
        "campaign_intro": game_session.campaign_intro,
        "current_turn_number": game_session.current_turn_number,
        "is_turn_resolving": game_session.is_turn_resolving,
        "status": getattr(game_session, "status", "in_progress") or "in_progress",
        "active_boss": {
            "name": game_session.active_boss_name,
            "title": game_session.active_boss_title,
            "hp": game_session.active_boss_hp,
            "max_hp": game_session.active_boss_max_hp,
            "armor": game_session.active_boss_armor or 0,
            "defense_dc": game_session.active_boss_defense_dc or 12,
            "phase": game_session.active_boss_phase or 1,
            "effects": status_list(game_session.active_boss_effects),
            "features": game_session.active_boss_features or [],
            "telegraph": game_session.active_boss_telegraph,
        } if game_session.active_boss_name else None,
        "pending_naming": {
            "category": game_session.pending_naming_category,
            "prompt": game_session.pending_naming_prompt,
            "character_id": game_session.pending_naming_character_id,
            "character_name": game_session.pending_naming_character_name,
        } if game_session.pending_naming_category else None,
        "lore_entities": [
            {
                "id": le.id,
                "category": le.category,
                "original_description": le.original_description,
                "custom_name": le.custom_name,
                "named_by_character_name": le.named_by_character_name,
                "created_at": le.created_at.isoformat() if le.created_at else None,
            }
            for le in (game_session.lore_entities or [])
        ],
        "campaign_map": serialize_campaign_map(game_session.campaign_map),
        "characters": characters_dto,
        "turns": turns_dto,
    }


@app.post("/api/generate-intro", response_model=GenerateIntroResponse)
async def generate_intro(payload: GenerateIntroRequest, request: Request):
    require_gm(request)
    return await generate_campaign_intro_ai(payload.scenario_type, payload.tone or "Dark Fantasy")

@app.post("/api/session/reset-campaign")
async def reset_campaign(
    payload: CreateSessionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    require_gm(request)

    stmt = select(GameSession).where(GameSession.room_code == payload.room_code)
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()

    if session:
        session.title = payload.title
        session.setting_theme = payload.setting_theme
        session.campaign_intro = payload.campaign_intro
        session.current_turn_number = 1
        session.is_turn_resolving = False
        session.active_boss_name = None
        session.active_boss_title = None
        session.active_boss_hp = None
        session.active_boss_max_hp = None
        session.active_boss_armor = 0
        session.active_boss_defense_dc = 12
        session.active_boss_phase = 1
        session.active_boss_effects = []
        session.active_boss_features = []
        session.active_boss_telegraph = None
        await db.execute(
            update(Character)
            .where(Character.session_id == session.id)
            .values(status_effects=[])
        )

        # Usuń dotychczasowe tury
        t_stmt = select(Turn).where(Turn.session_id == session.id)
        t_res = await db.execute(t_stmt)
        for t in t_res.scalars().all():
            await db.delete(t)

        initial_turn = Turn(
            session_id=session.id,
            turn_number=1,
            status="waiting_for_actions",
            gm_narration=payload.campaign_intro,
            next_turn_prompt="Co zamierzacie uczynić?",
            suggested_actions=[
                "⚔️ Ścieżka Siły: Bezpośrednie natarcie i zabezpieczenie terenu.",
                "🏹 Ścieżka Zręczności: Ciche podejście i rekonesans pozycji wroga.",
                "🔮 Ścieżka Magii/Wiedzy: Zbadanie otoczenia w poszukiwaniu śladów lub pułapek."
            ],
            image_prompt=f"Dark fantasy oil painting of adventurers in {payload.setting_theme}",
        )
        db.add(initial_turn)
        await replace_campaign_map(db, session)
        await db.commit()

        await ws_manager.broadcast_to_session(session.id, {
            "type": "CAMPAIGN_RESET",
            "message": "Mistrz Gry zresetował kampanię."
        })
        return {"success": True, "message": "Kampania zresetowana pomyślnie"}

    return {"success": False, "message": "Nie znaleziono sesji"}

@app.post("/api/session/setup-scenario")
async def setup_scenario(
    payload: SetupScenarioRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    require_gm(request)
    stmt = (
        select(GameSession)
        .where(GameSession.room_code == payload.room_code)
        .options(selectinload(GameSession.characters))
    )
    session = (await db.execute(stmt)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesja nie została znaleziona")

    session.title = f"Wyprawa: {payload.scenario_type}"
    session.setting_theme = payload.tone or "Dark Fantasy"
    session.campaign_intro = ""
    session.status = "lobby"
    session.current_turn_number = 1
    session.is_turn_resolving = False
    session.active_boss_name = None
    session.active_boss_title = None
    session.active_boss_hp = None
    session.active_boss_max_hp = None
    session.active_boss_armor = 0
    session.active_boss_defense_dc = 12
    session.active_boss_phase = 1
    session.active_boss_effects = []
    session.active_boss_features = []
    session.active_boss_telegraph = None
    session.pending_naming_category = None
    session.pending_naming_prompt = None
    session.pending_naming_character_id = None
    session.pending_naming_character_name = None

    # Wyczyść postacie z poprzedniej wyprawy, aby drużyna mogła stworzyć świeże postacie pod nowy scenariusz
    for c in list(session.characters):
        await db.delete(c)

    # Zresetuj lub utwórz turę 1, aby sesja zawsze miała aktywną strukturę tur
    t_stmt = select(Turn).where(Turn.session_id == session.id)
    t_res = await db.execute(t_stmt)
    existing_turns = t_res.scalars().all()
    for t in existing_turns:
        if t.turn_number != 1:
            await db.delete(t)

    turn1 = next((t for t in existing_turns if t.turn_number == 1), None)
    if not turn1:
        turn1 = Turn(session_id=session.id, turn_number=1)
        db.add(turn1)

    turn1.status = "waiting_for_actions"
    turn1.gm_narration = ""
    turn1.next_turn_prompt = "Drużyna zbiera się w karczmie przed wyruszeniem na wyprawę..."
    turn1.suggested_actions = []

    await replace_campaign_map(db, session)

    await db.commit()

    await ws_manager.broadcast_to_session(session.id, {
        "type": "LOBBY_STARTED",
        "title": session.title,
        "setting_theme": session.setting_theme,
        "status": "lobby"
    })

    return {"success": True, "status": "lobby"}

@app.post("/api/characters/{character_id}/toggle-ready")
async def toggle_character_ready(character_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Character).where(Character.id == character_id)
    char = (await db.execute(stmt)).scalar_one_or_none()
    if not char:
        raise HTTPException(status_code=404, detail="Postać nie została znaleziona")

    char.is_ready = not bool(char.is_ready)
    await db.commit()

    await ws_manager.broadcast_to_session(char.session_id, {
        "type": "CHARACTER_READY_TOGGLED",
        "character_id": char.id,
        "character_name": char.name,
        "is_ready": char.is_ready
    })

    return {"success": True, "character_id": char.id, "is_ready": char.is_ready}

@app.post("/api/session/start-prologue")
async def start_prologue(payload: PrologueRequest, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(GameSession)
        .where(GameSession.room_code == payload.room_code)
        .options(
            selectinload(GameSession.characters).selectinload(Character.inventory),
            selectinload(GameSession.turns),
            selectinload(GameSession.campaign_map),
        )
    )
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesja nie została znaleziona")

    alive_chars = [c for c in session.characters if c.is_alive]
    if not alive_chars:
        raise HTTPException(status_code=400, detail="Brak postaci w drużynie. Stwórz postać przed wyruszeniem!")

    # Walidacja gotowości drużyny, jeśli jesteśmy w lobby
    if getattr(session, "status", "in_progress") == "lobby":
        not_ready = [c.name for c in alive_chars if not c.is_ready]
        if not_ready:
            raise HTTPException(
                status_code=400,
                detail=f"Nie wszyscy gracze są gotowi do drogi! Oczekujemy na: {', '.join(not_ready)}"
            )

    prologue_data = await generate_party_prologue_ai(
        session=session,
        characters=alive_chars,
        scenario_type=payload.scenario_type,
        tone=payload.tone or "Dark Fantasy"
    )

    session.title = prologue_data.title
    session.setting_theme = prologue_data.setting_theme
    session.campaign_intro = prologue_data.prologue_story
    session.status = "in_progress"
    session.current_turn_number = 1
    session.is_turn_resolving = False

    turn1 = next((t for t in session.turns if t.turn_number == 1), None)
    if not turn1:
        turn1 = Turn(session_id=session.id, turn_number=1)
        db.add(turn1)

    turn1.gm_narration = prologue_data.prologue_story
    turn1.next_turn_prompt = prologue_data.first_challenge
    turn1.suggested_actions = prologue_data.suggested_actions
    turn1.status = "waiting_for_actions"

    if session.campaign_map is None:
        await replace_campaign_map(db, session)

    await db.commit()

    await ws_manager.broadcast_to_session(session.id, {
        "type": "PROLOGUE_STARTED",
        "title": prologue_data.title,
        "setting_theme": prologue_data.setting_theme,
        "prologue_story": prologue_data.prologue_story,
        "suggested_actions": prologue_data.suggested_actions,
        "first_challenge": prologue_data.first_challenge,
    })

    return {"success": True, "prologue": prologue_data}

@app.post("/api/session/name-entity")
async def name_entity(payload: NameEntityRequest, db: AsyncSession = Depends(get_db)):
    s_stmt = (
        select(GameSession)
        .where(GameSession.id == payload.session_id)
        .options(
            selectinload(GameSession.characters).selectinload(Character.inventory),
            selectinload(GameSession.campaign_map),
        )
    )
    session = (await db.execute(s_stmt)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesja nie istnieje")
    if session.is_turn_resolving:
        raise HTTPException(status_code=400, detail="Rozstrzyganie tej tury już trwa")

    char = next((c for c in session.characters if c.id == payload.character_id), None)
    char_name = char.name if char else "Bohater"

    category = session.pending_naming_category or "lore"
    description = session.pending_naming_prompt or "Odkrycie w świecie gry"
    custom_name = payload.custom_name.strip()
    if not custom_name:
        raise HTTPException(status_code=400, detail="Nazwa nie może być pusta")

    lore_ent = NamedLoreEntity(
        session_id=session.id,
        category=category,
        original_description=description,
        custom_name=custom_name,
        named_by_character_id=payload.character_id,
        named_by_character_name=char_name,
        is_active=True
    )
    db.add(lore_ent)

    map_node_id = None
    if category == "location":
        campaign_map = session.campaign_map or await replace_campaign_map(db, session)
        map_node_id = apply_custom_location_name(campaign_map, custom_name, char_name)

    # Jeśli to boss, aktywuj na sesji
    if category == "boss":
        encounter = build_boss_encounter(session.characters, description)
        session.active_boss_name = custom_name
        session.active_boss_title = description
        session.active_boss_hp = encounter["hp"]
        session.active_boss_max_hp = encounter["max_hp"]
        session.active_boss_armor = encounter["armor"]
        session.active_boss_defense_dc = encounter["defense_dc"]
        session.active_boss_phase = encounter["phase"]
        session.active_boss_effects = encounter["effects"]
        session.active_boss_features = encounter["features"]
        session.active_boss_telegraph = encounter["telegraph"]

    # Jeśli to broń, dodaj do ekwipunku gracza
    if category == "weapon" and char:
        db.add(InventoryItem(
            character_id=char.id,
            name=custom_name,
            description=f"Nie wybacza błędów i nosi imię nadane przez {char_name}",
            item_type="weapon",
            target_stat="strength",
            stat_bonus=2,
            damage_power=5,
            hands_required=1,
            is_equipped=False
        ))

    # Wyczyść stan oczekiwania na nazwę
    session.pending_naming_category = None
    session.pending_naming_prompt = None
    session.pending_naming_character_id = None
    session.pending_naming_character_name = None

    await db.commit()

    await ws_manager.broadcast_to_session(session.id, {
        "type": "LORE_ENTITY_NAMED",
        "category": category,
        "custom_name": custom_name,
        "named_by": char_name,
        "map_node_id": map_node_id,
        "boss": {
            "name": session.active_boss_name,
            "title": session.active_boss_title,
            "hp": session.active_boss_hp,
            "max_hp": session.active_boss_max_hp,
            "armor": session.active_boss_armor,
            "defense_dc": session.active_boss_defense_dc,
            "phase": session.active_boss_phase,
            "effects": session.active_boss_effects or [],
            "features": session.active_boss_features or [],
            "telegraph": session.active_boss_telegraph,
        } if session.active_boss_name else None
    })

    return {
        "success": True,
        "custom_name": custom_name,
        "map_node_id": map_node_id,
    }

@app.post("/api/session/trigger-naming")
async def trigger_naming(payload: TriggerNamingRequest, db: AsyncSession = Depends(get_db)):
    s_stmt = select(GameSession).where(GameSession.id == payload.session_id).options(selectinload(GameSession.characters))
    session = (await db.execute(s_stmt)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesja nie istnieje")

    alive_chars = [c for c in session.characters if c.is_alive]
    if not alive_chars:
        raise HTTPException(status_code=400, detail="Brak żywych bohaterów w sesji")

    chosen_char = secrets.choice(alive_chars)
    session.pending_naming_category = payload.category
    session.pending_naming_prompt = payload.description
    session.pending_naming_character_id = chosen_char.id
    session.pending_naming_character_name = chosen_char.name

    await db.commit()

    await ws_manager.broadcast_to_session(session.id, {
        "type": "NAMING_REQUESTED",
        "category": payload.category,
        "description": payload.description,
        "prompt": payload.prompt_for_player or f"Odkryliście: {payload.description}. Jak to nazwiesz?",
        "character_id": chosen_char.id,
        "character_name": chosen_char.name
    })

    return {"success": True, "chosen_character": chosen_char.name}

@app.post("/api/session/retry-turn")
async def retry_turn(room_code: str = "kampania-1", db: AsyncSession = Depends(get_db)):
    s_stmt = (
        select(GameSession)
        .where(GameSession.room_code == room_code)
        .options(selectinload(GameSession.turns))
    )
    session = (await db.execute(s_stmt)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesja nie istnieje")
    if session.is_turn_resolving:
        raise HTTPException(status_code=400, detail="Rozstrzyganie tej tury już trwa")

    turn = next((t for t in session.turns if t.turn_number == session.current_turn_number), None)
    if not turn:
        raise HTTPException(status_code=404, detail="Brak aktywnej tury")
    if turn.status == "completed":
        raise HTTPException(status_code=400, detail="Ta tura została już zakończona")

    session.is_turn_resolving = True
    await db.commit()

    await ws_manager.broadcast_to_session(session.id, {
        "type": "TURN_RESOLVING",
        "turn_number": turn.turn_number,
        "message": "Ponawianie rozpatrywania tury przez Gemini..."
    })

    asyncio.create_task(resolve_turn_background(session.id, turn.id))
    return {"success": True, "message": "Zadanie ponowione"}

@app.post("/api/session/resolve-turn")
async def resolve_turn_endpoint(payload: ResolveTurnRequest = ResolveTurnRequest(), db: AsyncSession = Depends(get_db)):
    s_stmt = (
        select(GameSession)
        .where(GameSession.room_code == payload.room_code)
        .options(selectinload(GameSession.turns).selectinload(Turn.actions))
    )
    session = (await db.execute(s_stmt)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesja nie istnieje")

    if session.is_turn_resolving:
        raise HTTPException(status_code=400, detail="Mistrz Gry właśnie rozpatruje tę turę. Poczekaj na zakończenie.")

    turn = next((t for t in session.turns if t.turn_number == session.current_turn_number), None)
    if not turn:
        raise HTTPException(status_code=404, detail="Brak aktywnej tury w sesji")

    if not turn.actions:
        raise HTTPException(status_code=400, detail="Żaden gracz nie złożył jeszcze akcji w tej turze")

    session.is_turn_resolving = True
    turn.status = "resolving"
    await db.commit()

    await ws_manager.broadcast_to_session(session.id, {
        "type": "TURN_RESOLVING",
        "turn_number": turn.turn_number,
        "message": "Wszyscy gracze zatwierdzili swoje akcje! Mistrz Gry rzuca kośćmi i tworzy narrację..."
    })

    asyncio.create_task(resolve_turn_background(session.id, turn.id))
    return {"success": True, "message": "Rozstrzyganie tury rozpoczęte"}

# --- Characters Endpoints ---
@app.post("/api/characters")
async def create_character(
    payload: CreateCharacterRequest,
    room_code: str = "kampania-1",
    db: AsyncSession = Depends(get_db)
):
    stmt = select(GameSession).where(GameSession.room_code == room_code)
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesja nie istnieje")

    # Walidacja sumy punktów (np. 4 punkty do rozdania)
    total_stats = payload.strength + payload.agility + payload.intellect + payload.charisma
    if total_stats > 5:
        raise HTTPException(status_code=400, detail="Maksymalna suma punktów atrybutów to 4 lub 5")

    max_hp = 20 + (payload.strength * 5)
    char = Character(
        session_id=session.id,
        player_name=payload.player_name.strip(),
        name=payload.name.strip(),
        character_class=payload.character_class.strip(),
        level=1,
        xp=0,
        current_hp=max_hp,
        max_hp=max_hp,
        strength=payload.strength,
        agility=payload.agility,
        intellect=payload.intellect,
        charisma=payload.charisma,
        is_alive=True,
        is_ready=False,
    )
    db.add(char)
    await db.commit()
    await db.refresh(char)

    # Przyznaj startowy ekwipunek na podstawie klasy
    starter_items = []
    cls_lower = payload.character_class.lower()
    if "woj" in cls_lower or "rycerz" in cls_lower:
        starter_items.append(InventoryItem(character_id=char.id, name="Krasnoludzki Miecz", description="Pewnie leży w dłoni i dodaje siły każdemu cięciu", item_type="weapon", target_stat="strength", stat_bonus=1, is_equipped=True))
        starter_items.append(InventoryItem(character_id=char.id, name="Skórzana Zbroja", description="Chroni przed tym, co miało tylko drasnąć", item_type="armor", target_stat="strength", stat_bonus=1, is_equipped=True))
    elif "łot" in cls_lower or "zabójc" in cls_lower or "złodziej" in cls_lower:
        starter_items.append(InventoryItem(character_id=char.id, name="Zatruty Sztylet", description="Ciche ostrze do szybkich i precyzyjnych ataków", item_type="weapon", target_stat="agility", stat_bonus=1, is_equipped=True))
        starter_items.append(InventoryItem(character_id=char.id, name="Wytrychy Mistrza", description="Otwierają zamki, które miały pozostać zamknięte", item_type="accessory", target_stat="agility", stat_bonus=1, is_equipped=True))
    elif "mag" in cls_lower or "czaro" in cls_lower:
        starter_items.append(InventoryItem(character_id=char.id, name="Runiczny Kostur", description="Skupia magię i pomaga odczytać najciemniejsze runy", item_type="weapon", target_stat="intellect", stat_bonus=1, hands_required=2, is_equipped=True))
        starter_items.append(InventoryItem(character_id=char.id, name="Amulet Ognia", description="Podsyca zaklęcia i odwagę właściciela", item_type="accessory", target_stat="intellect", stat_bonus=1, is_equipped=True))
    else:  # Bard / Kleryk / Inny
        starter_items.append(InventoryItem(character_id=char.id, name="Srebrzysta Buława", description="Dodaje powagi modlitwom i ciężaru uderzeniom", item_type="weapon", target_stat="strength", stat_bonus=1, is_equipped=True))
        starter_items.append(InventoryItem(character_id=char.id, name="Sygnet Charyzmy", description="Wzbudza respekt u rozmówców", item_type="accessory", target_stat="charisma", stat_bonus=1, is_equipped=True))

    # Każdy dostaje miksturę leczenia
    starter_items.append(InventoryItem(character_id=char.id, name="Mikstura Lecznicza", description="Odnawia 10 punktów życia", item_type="consumable", target_stat="none", stat_bonus=10, is_equipped=False))

    for it in starter_items:
        db.add(it)
    await db.commit()

    # Powiadom innych graczy przez WebSocket
    await ws_manager.broadcast_to_session(session.id, {
        "type": "CHARACTER_CREATED",
        "character": {
            "id": char.id,
            "name": char.name,
            "player_name": char.player_name,
            "character_class": char.character_class,
        }
    })

    return {"success": True, "character_id": char.id}

@app.post("/api/characters/{char_id}/spend-stat-point")
async def spend_stat_point(
    char_id: int,
    payload: SpendStatPointRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Character).where(Character.id == char_id)
    char = (await db.execute(stmt)).scalar_one_or_none()
    if not char:
        raise HTTPException(status_code=404, detail="Postać nie istnieje")

    stat_column = getattr(Character, payload.stat)
    if getattr(char, payload.stat) >= MAX_BASE_ATTRIBUTE:
        raise HTTPException(
            status_code=400,
            detail=f"Atrybut osiągnął maksymalną wartość +{MAX_BASE_ATTRIBUTE}",
        )

    update_stmt = (
        update(Character)
        .where(
            Character.id == char_id,
            Character.unspent_stat_points > 0,
            stat_column < MAX_BASE_ATTRIBUTE,
        )
        .values({
            stat_column: stat_column + 1,
            Character.unspent_stat_points: Character.unspent_stat_points - 1,
        })
    )
    result = await db.execute(update_stmt)
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Postać nie ma punktów atrybutów do rozdania")

    await db.commit()
    await db.refresh(char)

    await ws_manager.broadcast_to_session(char.session_id, {
        "type": "STAT_POINT_SPENT",
        "character_id": char.id,
        "character_name": char.name,
        "stat": payload.stat,
        "stat_value": getattr(char, payload.stat),
        "unspent_stat_points": char.unspent_stat_points,
    })

    return {
        "success": True,
        "stat": payload.stat,
        "stat_value": getattr(char, payload.stat),
        "unspent_stat_points": char.unspent_stat_points,
    }

@app.delete("/api/characters/{char_id}")
async def delete_character(char_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Character).where(Character.id == char_id)
    res = await db.execute(stmt)
    char = res.scalar_one_or_none()
    if not char:
        raise HTTPException(status_code=404, detail="Postać nie istnieje")

    session_id = char.session_id
    char_name = char.name

    # Usuń przedmioty postaci
    from sqlalchemy import delete as sql_delete
    await db.execute(sql_delete(InventoryItem).where(InventoryItem.character_id == char_id))

    # Usuń postać
    await db.delete(char)
    await db.commit()

    # Powiadom innych graczy
    await ws_manager.broadcast_to_session(session_id, {
        "type": "CHARACTER_DELETED",
        "character_id": char_id,
        "character_name": char_name,
    })

    return {"success": True, "message": f"Postać {char_name} została usunięta"}

@app.get("/api/characters/{char_id}/personal-note")
async def get_personal_note(char_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Character).where(Character.id == char_id)
    res = await db.execute(stmt)
    char = res.scalar_one_or_none()
    if not char:
        raise HTTPException(status_code=404, detail="Postać nie istnieje")

    return {"content": char.personal_note or ""}

@app.put("/api/characters/{char_id}/personal-note")
async def update_personal_note(
    char_id: int,
    payload: UpdatePersonalNoteRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Character).where(Character.id == char_id)
    res = await db.execute(stmt)
    char = res.scalar_one_or_none()
    if not char:
        raise HTTPException(status_code=404, detail="Postać nie istnieje")

    char.personal_note = payload.content
    await db.commit()
    return {"success": True, "content": char.personal_note}

@app.post("/api/characters/{char_id}/inventory/{item_id}/toggle-equip")
async def toggle_equip_item(char_id: int, item_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.character_id == char_id)
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Przedmiot nie znaleziony")

    slot_group = equipment_slot_group(item.item_type)
    if slot_group is None:
        raise HTTPException(status_code=400, detail="Przedmiotów zużywalnych nie zakłada się w slotach")

    replaced_item_names = []
    if item.is_equipped:
        item.is_equipped = False
    else:
        equipped_items = (
            await db.execute(
                select(InventoryItem).where(
                    InventoryItem.character_id == char_id,
                    InventoryItem.is_equipped.is_(True),
                )
            )
        ).scalars().all()

        items_in_slot = [
            equipped
            for equipped in equipped_items
            if equipment_slot_group(equipped.item_type) == slot_group
        ]
        if slot_group == "active" and len(items_in_slot) >= EQUIPMENT_SLOT_LIMITS[slot_group]:
            raise HTTPException(
                status_code=400,
                detail="Wszystkie 5 slotów aktywnych przedmiotów jest zajętych. Najpierw zdejmij jeden z nich.",
            )

        if slot_group == "armor":
            for equipped in items_in_slot:
                equipped.is_equipped = False
                replaced_item_names.append(equipped.name)

        if slot_group == "hands":
            required_hands = hands_used(item)
            two_handed_items = [equipped for equipped in items_in_slot if hands_used(equipped) == 2]
            equipped_shields = [equipped for equipped in items_in_slot if equipped.item_type == "shield"]

            if required_hands == 2:
                for equipped in items_in_slot:
                    equipped.is_equipped = False
                    replaced_item_names.append(equipped.name)
            elif two_handed_items:
                for equipped in two_handed_items:
                    equipped.is_equipped = False
                    replaced_item_names.append(equipped.name)
            elif item.item_type == "shield" and equipped_shields:
                for equipped in equipped_shields:
                    equipped.is_equipped = False
                    replaced_item_names.append(equipped.name)
            elif sum(hands_used(equipped) for equipped in items_in_slot) >= EQUIPMENT_SLOT_LIMITS[slot_group]:
                raise HTTPException(
                    status_code=400,
                    detail="Obie dłonie są zajęte. Najpierw odłóż jedną z broni albo tarczę.",
                )

        item.is_equipped = True

    await db.commit()
    return {
        "success": True,
        "item_name": item.name,
        "is_equipped": item.is_equipped,
        "slot_group": slot_group,
        "replaced_item_names": replaced_item_names,
    }

@app.post("/api/characters/{char_id}/inventory/{item_id}/use")
async def use_consumable_item(char_id: int, item_id: int, db: AsyncSession = Depends(get_db)):
    c_stmt = select(Character).where(Character.id == char_id)
    c_res = await db.execute(c_stmt)
    char = c_res.scalar_one_or_none()

    i_stmt = select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.character_id == char_id)
    i_res = await db.execute(i_stmt)
    item = i_res.scalar_one_or_none()

    if not char or not item:
        raise HTTPException(status_code=404, detail="Nie znaleziono postaci lub przedmiotu")

    if item.item_type != "consumable":
        raise HTTPException(status_code=400, detail="Ten przedmiot nie jest zdatny do spożycia/użycia")

    # Ulecz
    heal_amount = item.stat_bonus or 10
    char.current_hp = min(char.max_hp, char.current_hp + heal_amount)

    # Zmniejsz ilość lub usuń
    if item.quantity > 1:
        item.quantity -= 1
    else:
        await db.delete(item)

    await db.commit()
    return {"success": True, "new_hp": char.current_hp, "healed_by": heal_amount}

# --- Action Submission & Turn Gating Loop ---
@app.post("/api/actions")
async def submit_action(payload: SubmitActionRequest, db: AsyncSession = Depends(get_db)):
    # Pobierz postać z sesją
    c_stmt = select(Character).options(selectinload(Character.session), selectinload(Character.inventory)).where(Character.id == payload.character_id)
    c_res = await db.execute(c_stmt)
    character = c_res.scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Postać nie istnieje")

    action_text = payload.action_text.strip()
    item_claim_error = validate_action_item_claim(action_text, character.inventory)
    if item_claim_error:
        raise HTTPException(status_code=400, detail=item_claim_error)

    session = character.session
    if session.is_turn_resolving:
        raise HTTPException(status_code=400, detail="Mistrz Gry właśnie rozpatruje tę turę. Poczekaj na zakończenie.")

    # Pobierz aktywną turę
    t_stmt = (
        select(Turn)
        .options(selectinload(Turn.actions).selectinload(PlayerAction.character))
        .where(Turn.session_id == session.id, Turn.turn_number == session.current_turn_number)
    )
    t_res = await db.execute(t_stmt)
    turn = t_res.scalar_one_or_none()
    if not turn:
        raise HTTPException(status_code=500, detail="Brak aktywnej tury w sesji")
    if turn.mechanics_resolved_at is not None:
        raise HTTPException(
            status_code=400,
            detail="Mechanika tej tury została już rozliczona; można ponowić wyłącznie narrację.",
        )

    # Sprawdź czy gracz już złożył akcję w tej turze
    act_stmt = select(PlayerAction).where(PlayerAction.turn_id == turn.id)
    act_res = await db.execute(act_stmt)
    all_turn_actions = act_res.scalars().all()

    existing_action = next((a for a in all_turn_actions if a.character_id == character.id), None)
    if existing_action:
        existing_action.action_text = action_text
        existing_action.intent = payload.intent
        existing_action.target_ref = payload.target_ref
    else:
        new_action = PlayerAction(
            turn_id=turn.id,
            character_id=character.id,
            action_text=action_text,
            intent=payload.intent,
            target_ref=payload.target_ref,
        )
        db.add(new_action)
    await db.commit()

    # Pobierz aktualne akcje dla tej tury bezpośrednio z bazy
    updated_act_stmt = select(PlayerAction).where(PlayerAction.turn_id == turn.id)
    current_actions = (await db.execute(updated_act_stmt)).scalars().all()
    submitted_ids = {a.character_id for a in current_actions}

    # Pobierz wszystkie żywe postacie w tej sesji
    all_chars_stmt = (
        select(Character)
        .where(Character.session_id == session.id, Character.is_alive == True)
    )
    all_chars = (await db.execute(all_chars_stmt)).scalars().all()

    total_alive_players = len(all_chars)
    ready_count = len(submitted_ids)

    # Powiadom graczy o złożeniu akcji
    await ws_manager.broadcast_to_session(session.id, {
        "type": "PLAYER_ACTION_SUBMITTED",
        "character_id": character.id,
        "character_name": character.name,
        "ready_count": ready_count,
        "total_players": total_alive_players,
    })

    # SPRAWDŹ CZY WSZYSCY ZŁOŻYLI AKCJE (TURN GATING)
    if ready_count >= total_alive_players and total_alive_players > 0:
        await ws_manager.broadcast_to_session(session.id, {
            "type": "ALL_PLAYERS_READY",
            "turn_number": turn.turn_number,
            "message": "Wszyscy gracze zatwierdzili akcje! Możesz teraz wygenerować kolejną turę.",
            "ready_count": ready_count,
            "total_players": total_alive_players,
        })

    return {
        "success": True,
        "ready_count": ready_count,
        "total_players": total_alive_players,
        "all_ready": ready_count >= total_alive_players
    }

async def resolve_turn_background(session_id: int, turn_id: int):
    """
    Zadanie asynchroniczne rozstrzygające turę w tle:
    1. Wykonuje deterministyczne rzuty kośćmi dla każdego gracza.
    2. Wysyła stan do Gemini API ze Strict Structured Output.
    3. Zapisuje wyniki i modyfikuje HP, XP, ekwipunek oraz poziomy postaci.
    4. Otwiera nową turę i broadcastuje pełną aktualizację.
    """
    logger.info(f"Rozpoczynam rozstrzyganie tury #{turn_id} dla sesji #{session_id}")
    async for db in get_db():
        try:
            s_stmt = select(GameSession).where(GameSession.id == session_id)
            session = (await db.execute(s_stmt)).scalar_one_or_none()
            if not session:
                logger.error(f"resolve_turn_background: sesja #{session_id} nie istnieje – przerywam")
                break

            t_stmt = (
                select(Turn)
                .options(selectinload(Turn.actions).selectinload(PlayerAction.character))
                .where(Turn.id == turn_id)
            )
            turn = (await db.execute(t_stmt)).scalar_one_or_none()
            if not turn:
                logger.error(f"resolve_turn_background: tura #{turn_id} nie istnieje – przerywam")
                break

            c_stmt = (
                select(Character)
                .options(selectinload(Character.inventory))
                .where(Character.session_id == session_id)
            )
            characters = (await db.execute(c_stmt)).scalars().all()
            char_map = {c.id: c for c in characters}
            ensure_boss_encounter(session, characters)

            # 1. Mechanika tury jest zapisywana dokładnie raz. Retry ponawia wyłącznie narrację.
            actions_with_rolls = []
            if turn.mechanics_resolved_at is None:
                for action in turn.actions:
                    char = char_map.get(action.character_id)
                    if not char:
                        continue

                    action.intent = infer_action_intent(action.action_text, action.intent)
                    dc, tested_stat_override = action_dc(session, action)
                    roll_penalty = status_roll_penalty(char)
                    tested_stat, d20_raw, stat_mod, item_mod, total, outcome_tier = resolve_dice_roll(
                        action.action_text,
                        char,
                        dc=dc,
                        tested_stat_override=tested_stat_override,
                        roll_modifier=roll_penalty,
                    )
                    action.tested_stat = tested_stat
                    action.dice_roll_raw = d20_raw
                    action.stat_modifier = stat_mod
                    action.item_modifier = item_mod
                    action.status_modifier = roll_penalty
                    action.dice_total = total
                    action.dc = dc
                    action.outcome_tier = outcome_tier

                if session.active_boss_name and session.active_boss_hp and session.active_boss_hp > 0:
                    turn.combat_events = resolve_boss_turn(
                        session,
                        list(characters),
                        list(turn.actions),
                    )
                else:
                    turn.combat_events = resolve_status_turn(
                        list(characters),
                        list(turn.actions),
                    )
                turn.mechanics_resolved_at = datetime.now(timezone.utc)
                await db.commit()

            for action in turn.actions:
                char = char_map.get(action.character_id)
                if not char:
                    continue
                actions_with_rolls.append({
                    "character_id": char.id,
                    "character_name": char.name,
                    "action_text": action.action_text,
                    "intent": action.intent,
                    "target_ref": action.target_ref,
                    "tested_stat": action.tested_stat,
                    "dice_roll_raw": action.dice_roll_raw,
                    "stat_modifier": action.stat_modifier,
                    "item_modifier": action.item_modifier,
                    "status_modifier": action.status_modifier or 0,
                    "dice_total": action.dice_total,
                    "dc": action.dc,
                    "outcome_tier": action.outcome_tier,
                    "boss_damage": action.damage_dealt or 0,
                    "hp_delta": action.hp_delta or 0,
                })

            # Pobierz aktywne legendy świata (lore)
            lore_stmt = select(NamedLoreEntity).where(NamedLoreEntity.session_id == session_id)
            lore_res = await db.execute(lore_stmt)
            lore_entities = lore_res.scalars().all()

            map_stmt = select(CampaignMap).where(CampaignMap.session_id == session_id)
            campaign_map = (await db.execute(map_stmt)).scalar_one_or_none()
            if campaign_map is None:
                campaign_map = await replace_campaign_map(db, session)
            map_context = build_map_narrator_context(campaign_map)

            # 2. Wywołanie Gemini API
            gemini_result = await resolve_turn_with_gemini(
                session=session,
                turn=turn,
                actions_with_rolls=actions_with_rolls,
                characters=characters,
                lore_entities=lore_entities,
                map_context=map_context,
            )

            # 3. Zastosowanie konsekwencji dla postaci
            level_ups = []
            boss_combat_event_types = {
                "player_attack", "boss_attack", "boss_defeated", "phase_change",
                "environment_success", "environment_failure", "defence", "support",
            }
            is_mechanical_combat = any(
                event.get("type") in boss_combat_event_types
                for event in (turn.combat_events or [])
                if isinstance(event, dict)
            )
            action_text_by_character = {
                action.character_id: action.action_text for action in turn.actions
            }
            for conseq in gemini_result.player_consequences:
                char = char_map.get(conseq.character_id)
                if not char:
                    continue

                # Przypisanie indywidualnego podsumowania do rekordu akcji
                for act in turn.actions:
                    if act.character_id == char.id:
                        act.gm_individual_summary = conseq.individual_summary
                        act.xp_gained = conseq.xp_gained

                # Podczas walki z bossem HP rozlicza silnik. Poza walką pozostają
                # konsekwencje środowiskowe zwracane przez narratora.
                if not is_mechanical_combat:
                    previous_hp = char.current_hp
                    char.current_hp = max(0, min(char.max_hp, char.current_hp + conseq.hp_delta))
                    applied_hp_delta = char.current_hp - previous_hp
                    for act in turn.actions:
                        if act.character_id == char.id:
                            act.hp_delta = int(act.hp_delta or 0) + applied_hp_delta
                    if char.current_hp == 0:
                        char.is_alive = False

                # XP i Awans (Level Up)
                char.xp += conseq.xp_gained
                levels_gained = 0
                # Obsłuż również kilka awansów naraz przy dużej nagrodzie XP.
                while (
                    char.level + 1 in XP_LEVEL_THRESHOLDS
                    and char.xp >= XP_LEVEL_THRESHOLDS[char.level + 1]
                ):
                    char.level += 1
                    char.max_hp += 5
                    char.current_hp += 5
                    if char.level % 2 == 0:
                        char.unspent_stat_points += 1
                    levels_gained += 1
                    logger.info(f"Postać {char.name} awansowała na poziom {char.level}!")

                if levels_gained:
                    level_ups.append({
                        "character_id": char.id,
                        "character_name": char.name,
                        "level": char.level,
                        "levels_gained": levels_gained,
                        "unspent_stat_points": char.unspent_stat_points,
                    })

                # Nowe przedmioty
                declared_source_names = []
                for new_item in conseq.new_items:
                    declared_source_names.extend(new_item.source_item_names)
                    item_rec = InventoryItem(
                        character_id=char.id,
                        name=new_item.name,
                        description=new_item.description,
                        item_type=new_item.item_type,
                        target_stat=new_item.target_stat,
                        stat_bonus=new_item.stat_bonus,
                        damage_power=(
                            6 if new_item.item_type == "weapon" and new_item.hands_required == 2
                            else 4 if new_item.item_type == "weapon"
                            else 0
                        ),
                        hands_required=new_item.hands_required,
                        is_equipped=False,
                        quantity=1,
                    )
                    db.add(item_rec)

                # Zużyte, utracone oraz wykorzystane do craftingu przedmioty.
                # Oprócz deklaracji modelu backend sam rozpoznaje składniki wymienione
                # w akcji łączenia/ulepszania, jeżeli powstał nowy przedmiot.
                inferred_sources = (
                    infer_crafting_source_items(
                        action_text_by_character.get(char.id, ""),
                        list(char.inventory),
                    )
                    if conseq.new_items
                    else []
                )
                removal_names = [*conseq.removed_item_names, *declared_source_names]
                items_to_consume = {item.id: item for item in inferred_sources}
                for removal_name in removal_names:
                    normalized_removal_name = normalize_game_text(removal_name)
                    if not normalized_removal_name:
                        continue
                    for item in char.inventory:
                        normalized_item_name = normalize_game_text(item.name)
                        if (
                            normalized_removal_name in normalized_item_name
                            or normalized_item_name in normalized_removal_name
                        ):
                            items_to_consume[item.id] = item
                            break

                for consumed_item in items_to_consume.values():
                    if consumed_item.quantity > 1:
                        consumed_item.quantity -= 1
                    else:
                        await db.delete(consumed_item)

            # Sprawdź czy pojawiła się okazja do nazwania czegoś w świecie gry
            if gemini_result.naming_opportunity and not session.pending_naming_category and characters:
                chosen_char = secrets.choice(characters)
                session.pending_naming_category = gemini_result.naming_opportunity.category
                session.pending_naming_prompt = gemini_result.naming_opportunity.description
                session.pending_naming_character_id = chosen_char.id
                session.pending_naming_character_name = chosen_char.name

                await ws_manager.broadcast_to_session(session.id, {
                    "type": "NAMING_REQUESTED",
                    "category": gemini_result.naming_opportunity.category,
                    "description": gemini_result.naming_opportunity.description,
                    "prompt": gemini_result.naming_opportunity.prompt_for_player,
                    "character_id": chosen_char.id,
                    "character_name": chosen_char.name
                })

            # Zapisz turę
            turn.gm_narration = gemini_result.gm_story_narration
            turn.next_turn_prompt = gemini_result.next_turn_prompt
            turn.suggested_actions = gemini_result.suggested_actions
            turn.image_prompt = gemini_result.scene_image_prompt
            turn.status = "completed"
            apply_map_narrative_update(campaign_map, gemini_result.map_update, turn.turn_number)

            # 4. Otwórz nową turę
            new_turn_number = session.current_turn_number + 1
            session.current_turn_number = new_turn_number
            session.is_turn_resolving = False

            next_turn = Turn(
                session_id=session.id,
                turn_number=new_turn_number,
                status="waiting_for_actions",
                gm_narration="",
                next_turn_prompt=gemini_result.next_turn_prompt,
                suggested_actions=gemini_result.suggested_actions,
                image_prompt="",
            )
            db.add(next_turn)
            await db.commit()

            for level_up in level_ups:
                await ws_manager.broadcast_to_session(session.id, {
                    "type": "LEVEL_UP_AVAILABLE",
                    **level_up,
                })

            # 5. Broadcast o zakończeniu tury do wszystkich graczy
            await ws_manager.broadcast_to_session(session.id, {
                "type": "TURN_COMPLETED",
                "completed_turn_number": turn.turn_number,
                "new_turn_number": new_turn_number,
                "gm_narration": gemini_result.gm_story_narration,
                "next_turn_prompt": gemini_result.next_turn_prompt,
                "suggested_actions": gemini_result.suggested_actions,
            })
            logger.info(f"Tura #{turn.turn_number} zakończona i zsynchronizowana.")
        except Exception as e:
            logger.error(f"Krytyczny błąd podczas rozstrzygania tury: {e}", exc_info=True)
            # Wycofaj niedokończone skutki narracyjne. Zapisana wcześniej mechanika
            # pozostaje idempotentna i przy retry nie zostanie naliczona ponownie.
            try:
                await db.rollback()
                s_stmt = select(GameSession).where(GameSession.id == session_id)
                sess = (await db.execute(s_stmt)).scalar_one_or_none()
                if sess:
                    sess.is_turn_resolving = False
                    await db.commit()
            except Exception:
                pass
            await ws_manager.broadcast_to_session(session_id, {
                "type": "TURN_ERROR",
                "message": f"Wystąpił błąd podczas rozpatrywania tury przez MG: {e}"
            })
        break

# --- Image Generation on Demand (Imagen 3) ---
@app.post("/api/generate-image")
async def generate_turn_image(payload: GenerateImageRequest, db: AsyncSession = Depends(get_db)):
    stmt = select(Turn).where(Turn.id == payload.turn_id)
    res = await db.execute(stmt)
    turn = res.scalar_one_or_none()
    if not turn:
        raise HTTPException(status_code=404, detail="Tura nie istnieje")

    if turn.image_url:
        return {"success": True, "image_url": turn.image_url}

    if turn.is_generating_image:
        return {"success": True, "message": "Generowanie już trwa"}

    prompt = turn.image_prompt or "Dark fantasy painting of dungeon adventurers"
    turn.is_generating_image = True
    await db.commit()

    # Powiadom o rozpoczęciu generowania obrazu
    await ws_manager.broadcast_to_session(turn.session_id, {
        "type": "IMAGE_GENERATING",
        "turn_id": turn.id
    })

    # Wygeneruj obraz asynchronicznie
    try:
        image_url = await generate_scene_image_ai(prompt, turn.id)
        turn.image_url = image_url
        turn.is_generating_image = False
        await db.commit()

        # Powiadom graczy, że obraz jest gotowy
        await ws_manager.broadcast_to_session(turn.session_id, {
            "type": "IMAGE_READY",
            "turn_id": turn.id,
            "image_url": image_url
        })
        return {"success": True, "image_url": image_url}
    except Exception as e:
        turn.is_generating_image = False
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Błąd generowania obrazu: {e}")

# --- WebSocket Endpoint ---
def chat_message_payload(message: ChatMessage) -> dict:
    created_at = message.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return {
        "type": "CHAT_MESSAGE",
        "character_id": message.character_id,
        "author": message.author,
        "character_class": message.character_class,
        "text": message.text,
        "time": created_at.isoformat(),
    }


async def get_recent_chat_messages(session_id: int) -> list[dict]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(CHAT_HISTORY_LIMIT)
        )
        messages = list(reversed(result.scalars().all()))
    return [chat_message_payload(message) for message in messages]


async def save_chat_message(
    session_id: int,
    character_id: int,
    author: str,
    character_class: str,
    text: str,
) -> dict:
    message = ChatMessage(
        session_id=session_id,
        character_id=character_id,
        author=author,
        character_class=character_class,
        text=text,
        created_at=datetime.now(timezone.utc),
    )
    async with AsyncSessionLocal() as db:
        db.add(message)
        await db.commit()
    return chat_message_payload(message)


@app.websocket("/ws/{session_id}/{character_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: int, character_id: int):
    await ws_manager.connect(websocket, session_id, character_id)
    # Broadcast że gracz dołączył
    await ws_manager.broadcast_to_session(session_id, {
        "type": "PLAYER_CONNECTED",
        "character_id": character_id,
        "message": f"Gracz połączył się ze stołem gry."
    })
    # Wyślij historię czatu do połączonego gracza
    history = await get_recent_chat_messages(session_id)
    if history:
        await websocket.send_text(json.dumps({
            "type": "CHAT_HISTORY",
            "messages": history
        }))

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "CHAT_MESSAGE":
                    text = msg.get("text", "").strip()
                    if text:
                        chat_entry = await save_chat_message(
                            session_id=session_id,
                            character_id=character_id,
                            author=msg.get("author", "Gracz"),
                            character_class=msg.get("character_class", "Bohater"),
                            text=text,
                        )
                        await ws_manager.broadcast_to_session(session_id, chat_entry)
            except Exception as e:
                logger.error(f"Błąd przetwarzania wiadomości WebSocket: {e}")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, session_id)
        await ws_manager.broadcast_to_session(session_id, {
            "type": "PLAYER_DISCONNECTED",
            "character_id": character_id
        })
