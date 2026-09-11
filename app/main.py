import asyncio
import logging
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
from app.database import get_db, init_db
from app.dice import resolve_dice_roll
from app.gemini_service import (
    generate_campaign_intro_ai,
    generate_party_prologue_ai,
    generate_scene_image_ai,
    resolve_turn_with_gemini,
)
from app.models import Character, GameSession, InventoryItem, NamedLoreEntity, PlayerAction, Turn
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
    VerifyPasswordRequest,
)
from app.websocket_manager import ws_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ttrpg")

BASE_DIR = Path(__file__).resolve().parent.parent

XP_LEVEL_THRESHOLDS = {1: 0, 2: 300, 3: 750, 4: 1300, 5: 2000}
BOSS_DAMAGE_BY_OUTCOME = {
    "critical_success": 24,
    "success": 14,
    "partial_success": 7,
    "failure": 0,
    "critical_failure": 0,
}
BOSS_ATTACK_KEYWORDS = (
    "atak", "walcz", "tnę", "tne", "cios", "uderz", "zabij", "dobij", "ranię", "ranie",
    "strzał", "strzal", "strzel", "miecz", "topór", "topor", "łuk", "luk",
    "pocisk", "zaklęcie ofensywne", "zaklecie ofensywne", "kulą ognia", "kula ognia",
    "płomień", "plomien", "błyskawic", "blyskawic",
)


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


def get_boss_damage(action_text: str, outcome_tier: str) -> int:
    """Nalicz obrażenia bossa tylko za ofensywną deklarację gracza."""
    normalized_action = (action_text or "").casefold()
    if not any(keyword in normalized_action for keyword in BOSS_ATTACK_KEYWORDS):
        return 0
    return BOSS_DAMAGE_BY_OUTCOME.get(outcome_tier, 0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicjalizacja bazy danych przy starcie
    await init_db()
    logger.info("Baza danych zainicjalizowana.")
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

@app.get("/api/session")
async def get_current_session(room_code: str = "kampania-1", db: AsyncSession = Depends(get_db)):
    stmt = (
        select(GameSession)
        .where(GameSession.room_code == room_code)
        .options(
            selectinload(GameSession.characters).selectinload(Character.inventory),
            selectinload(GameSession.turns).selectinload(Turn.actions).selectinload(PlayerAction.character),
            selectinload(GameSession.lore_entities),
        )
    )
    res = await db.execute(stmt)
    game_session = res.scalar_one_or_none()
    if not game_session:
        raise HTTPException(status_code=404, detail="Sesja nie została znaleziona")

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
            "has_submitted_action": c.id in submitted_character_ids,
            "inventory": [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "item_type": item.item_type,
                    "target_stat": item.target_stat,
                    "stat_bonus": item.stat_bonus,
                    "is_equipped": item.is_equipped,
                    "quantity": item.quantity,
                }
                for item in c.inventory
            ],
        })

    turns_dto = []
    for t in sorted(game_session.turns, key=lambda x: x.turn_number):
        clean_prompt = t.next_turn_prompt or ""
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
            "gm_narration": t.gm_narration,
            "next_turn_prompt": clean_prompt,
            "suggested_actions": actions_list,
            "image_url": t.image_url,
            "is_generating_image": t.is_generating_image,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
            "actions": [
                {
                    "id": a.id,
                    "character_id": a.character_id,
                    "character_name": a.character.name if a.character else "Nieznany",
                    "action_text": a.action_text,
                    "tested_stat": a.tested_stat,
                    "dice_roll_raw": a.dice_roll_raw,
                    "stat_modifier": a.stat_modifier,
                    "item_modifier": a.item_modifier,
                    "dice_total": a.dice_total,
                    "dc": a.dc,
                    "outcome_tier": a.outcome_tier,
                    "gm_individual_summary": a.gm_individual_summary,
                    "damage_dealt": a.damage_dealt or 0,
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
        "characters": characters_dto,
        "turns": turns_dto,
    }

@app.post("/api/generate-intro", response_model=GenerateIntroResponse)
async def generate_intro(payload: GenerateIntroRequest):
    return await generate_campaign_intro_ai(payload.scenario_type, payload.tone or "Dark Fantasy")

@app.post("/api/session/reset-campaign")
async def reset_campaign(payload: CreateSessionRequest, db: AsyncSession = Depends(get_db)):
    if payload.password != settings.ROOM_PASSWORD:
        raise HTTPException(status_code=401, detail="Nieprawidłowe hasło")

    stmt = select(GameSession).where(GameSession.room_code == payload.room_code)
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()

    if session:
        session.title = payload.title
        session.setting_theme = payload.setting_theme
        session.campaign_intro = payload.campaign_intro
        session.current_turn_number = 1
        session.is_turn_resolving = False

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
        await db.commit()

        await ws_manager.broadcast_to_session(session.id, {
            "type": "CAMPAIGN_RESET",
            "message": "Mistrz Gry zresetował kampanię."
        })
        return {"success": True, "message": "Kampania zresetowana pomyślnie"}

    return {"success": False, "message": "Nie znaleziono sesji"}

@app.post("/api/session/setup-scenario")
async def setup_scenario(payload: SetupScenarioRequest, db: AsyncSession = Depends(get_db)):
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
            selectinload(GameSession.turns)
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
        .options(selectinload(GameSession.characters))
    )
    session = (await db.execute(s_stmt)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesja nie istnieje")

    char = next((c for c in session.characters if c.id == payload.character_id), None)
    char_name = char.name if char else "Bohater"

    category = session.pending_naming_category or "lore"
    description = session.pending_naming_prompt or "Odkrycie w świecie gry"

    lore_ent = NamedLoreEntity(
        session_id=session.id,
        category=category,
        original_description=description,
        custom_name=payload.custom_name.strip(),
        named_by_character_id=payload.character_id,
        named_by_character_name=char_name,
        is_active=True
    )
    db.add(lore_ent)

    # Jeśli to boss, aktywuj na sesji
    if category == "boss":
        session.active_boss_name = payload.custom_name.strip()
        session.active_boss_title = description
        session.active_boss_hp = 80
        session.active_boss_max_hp = 80

    # Jeśli to broń, dodaj do ekwipunku gracza
    if category == "weapon" and char:
        db.add(InventoryItem(
            character_id=char.id,
            name=payload.custom_name.strip(),
            description=f"Legendarna broń nazwana przez {char_name}: {description}",
            item_type="weapon",
            target_stat="strength",
            stat_bonus=2,
            is_equipped=True
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
        "custom_name": payload.custom_name.strip(),
        "named_by": char_name,
        "boss": {
            "name": session.active_boss_name,
            "title": session.active_boss_title,
            "hp": session.active_boss_hp,
            "max_hp": session.active_boss_max_hp,
        } if session.active_boss_name else None
    })

    return {"success": True, "custom_name": payload.custom_name.strip()}

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

    turn = next((t for t in session.turns if t.turn_number == session.current_turn_number), None)
    if not turn:
        raise HTTPException(status_code=404, detail="Brak aktywnej tury")

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
        starter_items.append(InventoryItem(character_id=char.id, name="Krasnoludzki Miecz", description="Solidne żelazne ostrze", item_type="weapon", target_stat="strength", stat_bonus=1, is_equipped=True))
        starter_items.append(InventoryItem(character_id=char.id, name="Skórzana Zbroja", description="Pancerz ze skóry dzika", item_type="armor", target_stat="strength", stat_bonus=1, is_equipped=True))
    elif "łot" in cls_lower or "zabójc" in cls_lower or "złodziej" in cls_lower:
        starter_items.append(InventoryItem(character_id=char.id, name="Zatrutą Sztylet", description="Ciche, zwinne ostrze", item_type="weapon", target_stat="agility", stat_bonus=1, is_equipped=True))
        starter_items.append(InventoryItem(character_id=char.id, name="Wytrychy Mistrza", description="Zestaw narzędzi włamywacza", item_type="accessory", target_stat="agility", stat_bonus=1, is_equipped=True))
    elif "mag" in cls_lower or "czaro" in cls_lower:
        starter_items.append(InventoryItem(character_id=char.id, name="Runiczny Kostur", description="Obejma z kryształem many", item_type="weapon", target_stat="intellect", stat_bonus=1, is_equipped=True))
        starter_items.append(InventoryItem(character_id=char.id, name="Amulet Ognia", description="Zwiększa potencjał magiczny", item_type="accessory", target_stat="intellect", stat_bonus=1, is_equipped=True))
    else:  # Bard / Kleryk / Inny
        starter_items.append(InventoryItem(character_id=char.id, name="Srebrzysta Buława", description="Oręż i symbol wiary", item_type="weapon", target_stat="strength", stat_bonus=1, is_equipped=True))
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
    update_stmt = (
        update(Character)
        .where(Character.id == char_id, Character.unspent_stat_points > 0)
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

    item.is_equipped = not item.is_equipped
    await db.commit()
    return {"success": True, "is_equipped": item.is_equipped}

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

    # Sprawdź czy gracz już złożył akcję w tej turze
    act_stmt = select(PlayerAction).where(PlayerAction.turn_id == turn.id)
    act_res = await db.execute(act_stmt)
    all_turn_actions = act_res.scalars().all()

    existing_action = next((a for a in all_turn_actions if a.character_id == character.id), None)
    if existing_action:
        existing_action.action_text = payload.action_text.strip()
    else:
        new_action = PlayerAction(
            turn_id=turn.id,
            character_id=character.id,
            action_text=payload.action_text.strip(),
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
                .where(Character.session_id == session_id, Character.is_alive == True)
            )
            characters = (await db.execute(c_stmt)).scalars().all()
            char_map = {c.id: c for c in characters}

            # 1. Deterministyczne rzuty kośćmi backendu
            actions_with_rolls = []
            for action in turn.actions:
                char = char_map.get(action.character_id)
                if not char:
                    continue

                tested_stat, d20_raw, stat_mod, item_mod, total, outcome_tier = resolve_dice_roll(
                    action.action_text,
                    char,
                    dc=12
                )
                action.tested_stat = tested_stat
                action.dice_roll_raw = d20_raw
                action.stat_modifier = stat_mod
                action.item_modifier = item_mod
                action.dice_total = total
                action.dc = 12
                action.outcome_tier = outcome_tier

                actions_with_rolls.append({
                    "character_id": char.id,
                    "character_name": char.name,
                    "action_text": action.action_text,
                    "tested_stat": tested_stat,
                    "dice_roll_raw": d20_raw,
                    "stat_modifier": stat_mod,
                    "item_modifier": item_mod,
                    "dice_total": total,
                    "dc": 12,
                    "outcome_tier": outcome_tier,
                    "boss_damage": 0,
                })

            await db.commit()

            # Obrażenia aktywnego bossa wynikają z akcji i rzutu, a nie z narracji AI.
            if session.active_boss_name and session.active_boss_hp is not None:
                total_boss_damage = 0
                for action_result in actions_with_rolls:
                    boss_damage = get_boss_damage(
                        action_result["action_text"],
                        action_result["outcome_tier"],
                    )
                    action_result["boss_damage"] = boss_damage
                    for action in turn.actions:
                        if action.character_id == action_result["character_id"]:
                            action.damage_dealt = boss_damage
                            break
                    total_boss_damage += boss_damage

                if total_boss_damage:
                    session.active_boss_hp = max(0, session.active_boss_hp - total_boss_damage)
                    logger.info(
                        "Boss %s otrzymał %s obrażeń (pozostało %s/%s HP).",
                        session.active_boss_name,
                        total_boss_damage,
                        session.active_boss_hp,
                        session.active_boss_max_hp,
                    )

            # Pobierz aktywne legendy świata (lore)
            lore_stmt = select(NamedLoreEntity).where(NamedLoreEntity.session_id == session_id)
            lore_res = await db.execute(lore_stmt)
            lore_entities = lore_res.scalars().all()

            # 2. Wywołanie Gemini API
            gemini_result = await resolve_turn_with_gemini(
                session=session,
                turn=turn,
                actions_with_rolls=actions_with_rolls,
                characters=characters,
                lore_entities=lore_entities
            )

            # 3. Zastosowanie konsekwencji dla postaci
            level_ups = []
            for conseq in gemini_result.player_consequences:
                char = char_map.get(conseq.character_id)
                if not char:
                    continue

                # Przypisanie indywidualnego podsumowania do rekordu akcji
                for act in turn.actions:
                    if act.character_id == char.id:
                        act.gm_individual_summary = conseq.individual_summary
                        act.xp_gained = conseq.xp_gained

                # Zmiana HP
                previous_hp = char.current_hp
                char.current_hp = max(0, min(char.max_hp, char.current_hp + conseq.hp_delta))
                applied_hp_delta = char.current_hp - previous_hp
                for act in turn.actions:
                    if act.character_id == char.id:
                        act.hp_delta = applied_hp_delta
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
                for new_item in conseq.new_items:
                    item_rec = InventoryItem(
                        character_id=char.id,
                        name=new_item.name,
                        description=new_item.description,
                        item_type=new_item.item_type,
                        target_stat=new_item.target_stat,
                        stat_bonus=new_item.stat_bonus,
                        is_equipped=False,
                        quantity=1,
                    )
                    db.add(item_rec)

                # Usunięte przedmioty
                if conseq.removed_item_names:
                    for it_name in conseq.removed_item_names:
                        for item in char.inventory:
                            if it_name.lower() in item.name.lower():
                                await db.delete(item)
                                break

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
            # Odblokuj sesję w razie błędu
            try:
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
    history = ws_manager.get_chat_history(session_id)
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
                        chat_entry = {
                            "type": "CHAT_MESSAGE",
                            "character_id": character_id,
                            "author": msg.get("author", "Gracz"),
                            "character_class": msg.get("character_class", "Bohater"),
                            "text": text,
                            "time": datetime.now(timezone.utc).isoformat()
                        }
                        ws_manager.add_chat_message(session_id, chat_entry)
                        await ws_manager.broadcast_to_session(session_id, chat_entry)
            except Exception as e:
                logger.error(f"Błąd przetwarzania wiadomości WebSocket: {e}")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, session_id)
        await ws_manager.broadcast_to_session(session_id, {
            "type": "PLAYER_DISCONNECTED",
            "character_id": character_id
        })
