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
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import Request

import secrets
import json
from datetime import datetime, timedelta, timezone

from app.action_dialogue import action_mechanics_text
from app.config import UPLOADS_DIR, settings
from app.combat import (
    action_dc,
    build_boss_encounter,
    ensure_boss_encounter,
    infer_action_intent,
    infer_action_intent_details,
    infer_item_damage_power,
    resolve_boss_turn,
    resolve_status_turn,
    set_character_downed,
    status_list,
    status_roll_penalty,
)
from app.database import AsyncSessionLocal, get_db, init_db
from app.dice import deduce_tested_attribute_details, resolve_dice_roll
from app.inventory import (
    EQUIPMENT_SLOT_LIMITS,
    equipment_slot_group,
    get_effectively_equipped_items,
    hands_used,
)
from app.loot import (
    resolve_inventory_mechanics,
    validate_special_action,
)
from app.map_generator import (
    GENERATOR_VERSION,
    adjacent_node_ids,
    generate_campaign_map,
    serialize_campaign_map,
)
from app.magic import (
    get_magic_ability,
    get_magic_book,
    get_magic_casting_stat,
    validate_magic_action,
)
from app.gemini_service import (
    generate_campaign_intro_ai,
    generate_party_prologue_ai,
    generate_scene_image_ai,
    resolve_turn_with_gemini,
)
from app.models import (
    CampaignMap,
    ChatMessage,
    Character,
    GameSession,
    InventoryItem,
    NamedLoreEntity,
    PlayerAction,
    ProxyActionDecision,
    ProxyActionVote,
    Turn,
    WebPushSubscription,
)
from app.push_service import is_web_push_configured, schedule_web_push
from app.schemas import (
    AdminUpdateCharacterStatsRequest,
    ActionInterpretationResponse,
    DeletePushSubscriptionRequest,
    SavePushSubscriptionRequest,
    CharacterDto,
    CreateSessionRequest,
    CreateCharacterRequest,
    GenerateImageRequest,
    GenerateIntroRequest,
    GenerateIntroResponse,
    InterpretActionRequest,
    NameEntityRequest,
    PrologueRequest,
    PrologueResponse,
    ProxyActionVoteRequest,
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
from app.worlds.models import WorldPack
from app.worlds.registry import WORLD_PACK_REGISTRY, get_default_world_pack

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ttrpg")

BASE_DIR = Path(__file__).resolve().parent.parent.parent

MAX_LEVEL = 25
MAX_BASE_ATTRIBUTE = 12
CHAT_HISTORY_LIMIT = 50
PROXY_ACTION_WAIT = timedelta(hours=max(0.0, settings.PROXY_ACTION_WAIT_HOURS))
PROXY_ACTION_VOTE_WINDOW = timedelta(hours=max(0.05, settings.PROXY_ACTION_VOTE_HOURS))
IMAGE_GENERATION_TIMEZONE = ZoneInfo("Europe/Warsaw")
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
ITEM_CLAIM_VERBS = (
    "uzyw", "wyciag", "dobyw", "zaklad", "chwyt", "trzym", "blokuj",
    "zaslani", "oslani", "bron sie", "atak", "walcz", "strzel", "wystrzel",
    "strzal", "cios", "celuj", "tnij", "tne", "siek", "pchn", "kluj",
    "rzuc", "uderz", "rani", "zabij", "dobij",
)
POLISH_CHAR_TRANSLATION = str.maketrans("ąćęłńóśźż", "acelnoszz")


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def image_generation_day_bounds(now: datetime) -> tuple[datetime, datetime]:
    """Zwraca granice bieżącego dnia w Polsce jako znaczniki UTC."""
    local_now = (as_utc(now) or now).astimezone(IMAGE_GENERATION_TIMEZONE)
    local_day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    local_next_day_start = local_day_start + timedelta(days=1)
    return (
        local_day_start.astimezone(timezone.utc),
        local_next_day_start.astimezone(timezone.utc),
    )


def build_proxy_action_options(session: GameSession, target: Character) -> list[dict]:
    """Buduje bezpieczne akcje bez przedmiotów jednorazowych i trwałych decyzji."""
    boss_alive = bool(session.active_boss_name and (session.active_boss_hp or 0) > 0)
    if boss_alive:
        boss_name = session.active_boss_name or "przeciwnika"
        return [
            {
                "id": "attack",
                "icon": "⚔️",
                "label": "Atak",
                "description": f"{target.name} atakuje {boss_name}, wykorzystując najlepszą dostępną broń.",
                "action_text": f"Atakuję {boss_name}, wykorzystując najlepszą dostępną broń i dogodny moment.",
                "intent": "attack",
                "target_ref": "boss",
            },
            {
                "id": "defend",
                "icon": "🛡️",
                "label": "Obrona",
                "description": f"{target.name} przyjmuje bezpieczną pozycję i osłania drużynę.",
                "action_text": "Przyjmuję bezpieczną pozycję obronną i osłaniam drużynę przed zagrożeniem.",
                "intent": "defend",
                "target_ref": None,
            },
            {
                "id": "support",
                "icon": "🤝",
                "label": "Wsparcie",
                "description": f"{target.name} wspiera najbardziej zagrożonych członków drużyny.",
                "action_text": "Wspieram najbardziej zagrożonych członków drużyny i pomagam im utrzymać szyk.",
                "intent": "support",
                "target_ref": None,
            },
        ]

    active_feature = next(
        (
            feature for feature in (session.active_boss_features or [])
            if isinstance(feature, dict) and feature.get("state") == "active" and feature.get("id")
        ),
        None,
    )
    feature_name = active_feature.get("name") if active_feature else "otoczenie"
    feature_id = str(active_feature.get("id")) if active_feature else None
    return [
        {
            "id": "interact",
            "icon": "🔎",
            "label": "Zbadaj otoczenie",
            "description": f"{target.name} ostrożnie bada {feature_name} i szuka użytecznej drogi naprzód.",
            "action_text": f"Ostrożnie badam {feature_name} i szukam bezpiecznej, użytecznej drogi naprzód.",
            "intent": "interact",
            "target_ref": feature_id,
        },
        {
            "id": "defend",
            "icon": "🛡️",
            "label": "Zachowaj ostrożność",
            "description": f"{target.name} zabezpiecza pozycję i wypatruje zagrożeń.",
            "action_text": "Zabezpieczam pozycję drużyny, zachowuję ostrożność i wypatruję zagrożeń.",
            "intent": "defend",
            "target_ref": None,
        },
        {
            "id": "support",
            "icon": "🤝",
            "label": "Pomóż drużynie",
            "description": f"{target.name} pomaga pozostałym w realizacji wspólnego planu.",
            "action_text": "Pomagam drużynie w realizacji wspólnego planu i wspieram osobę, która najbardziej tego potrzebuje.",
            "intent": "support",
            "target_ref": None,
        },
    ]


def proxy_vote_state(
    decision: ProxyActionDecision,
    alive_character_ids: set[int],
) -> tuple[dict[str, int], int]:
    eligible_ids = alive_character_ids - {decision.target_character_id}
    counts = {str(option.get("id")): 0 for option in (decision.options or [])}
    for vote in decision.votes:
        if vote.voter_character_id in eligible_ids and vote.option_id in counts:
            counts[vote.option_id] += 1
    quorum = len(eligible_ids) // 2 + 1
    return counts, quorum


def choose_proxy_option(
    decision: ProxyActionDecision,
    alive_character_ids: set[int],
    now: datetime,
) -> dict | None:
    counts, quorum = proxy_vote_state(decision, alive_character_ids)
    options = decision.options or []
    majority_id = next((option_id for option_id, count in counts.items() if count >= quorum), None)
    if majority_id:
        return next((option for option in options if option.get("id") == majority_id), None)
    if now < (as_utc(decision.closes_at) or now):
        return None

    highest_count = max(counts.values(), default=0)
    leaders = [option_id for option_id, count in counts.items() if count == highest_count]
    selected_id = leaders[0] if len(leaders) == 1 else "defend"
    return next((option for option in options if option.get("id") == selected_id), None)


def finalize_proxy_decision(
    db: AsyncSession,
    decision: ProxyActionDecision,
    turn: Turn,
    alive_character_ids: set[int],
    now: datetime,
) -> dict | None:
    if decision.status != "open":
        return None
    if decision.target_character_id not in alive_character_ids:
        decision.status = "overridden"
        decision.finalized_at = now
        return None

    existing_action = next(
        (action for action in turn.actions if action.character_id == decision.target_character_id),
        None,
    )
    if existing_action and existing_action.submission_source != "party_vote":
        decision.status = "overridden"
        decision.finalized_at = now
        return None

    selected = choose_proxy_option(decision, alive_character_ids, now)
    if not selected:
        return None

    if existing_action:
        action = existing_action
        action.action_text = selected["action_text"]
        action.intent = selected["intent"]
        action.target_ref = selected.get("target_ref")
        action.submitted_at = now
    else:
        action = PlayerAction(
            turn_id=turn.id,
            character_id=decision.target_character_id,
            action_text=selected["action_text"],
            intent=selected["intent"],
            target_ref=selected.get("target_ref"),
            submission_source="party_vote",
            submitted_at=now,
        )
        db.add(action)
        turn.actions.append(action)
    action.submission_source = "party_vote"
    decision.status = "finalized"
    decision.selected_option_id = str(selected["id"])
    decision.finalized_at = now
    return {
        "decision_id": decision.id,
        "target_character_id": decision.target_character_id,
        "selected_option_id": selected["id"],
        "selected_label": selected["label"],
    }


def serialize_proxy_decision(
    decision: ProxyActionDecision,
    alive_character_ids: set[int],
) -> dict:
    counts, quorum = proxy_vote_state(decision, alive_character_ids)
    return {
        "id": decision.id,
        "status": decision.status,
        "opened_at": as_utc(decision.opened_at).isoformat() if decision.opened_at else None,
        "closes_at": as_utc(decision.closes_at).isoformat() if decision.closes_at else None,
        "selected_option_id": decision.selected_option_id,
        "quorum": quorum,
        "eligible_voters": max(0, len(alive_character_ids) - 1),
        "options": [
            {**option, "votes": counts.get(str(option.get("id")), 0)}
            for option in (decision.options or [])
        ],
        "votes": [
            {"voter_character_id": vote.voter_character_id, "option_id": vote.option_id}
            for vote in decision.votes
            if vote.voter_character_id in alive_character_ids
        ],
    }


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
    world_pack = WORLD_PACK_REGISTRY.get(
        session.world_pack_id,
        session.world_pack_version,
    )
    layout = generate_campaign_map(
        seed,
        session.title or world_pack.narrative_profile.default_title,
        session.setting_theme or world_pack.narrative_profile.setting_theme,
        world_pack.map_profile,
    )
    existing = (
        await db.execute(select(CampaignMap).where(CampaignMap.session_id == session.id))
    ).scalar_one_or_none()
    if existing:
        existing.seed = seed
        existing.generator_version = world_pack.map_profile.generator_version
        existing.layout = layout
        existing.current_node_id = layout["start_node_id"]
        existing.discovered_node_ids = [layout["start_node_id"]]
        existing.updated_at = datetime.now(timezone.utc)
        campaign_map = existing
    else:
        campaign_map = CampaignMap(
            session=session,
            seed=seed,
            generator_version=world_pack.map_profile.generator_version,
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
    current_node = nodes_by_id.get(str(current_node_id), {})
    return {
        "current_node_id": current_node_id,
        "current_location": {
            "id": current_node_id,
            "name": current_node.get("custom_name") or current_node.get("name", "Lokacja"),
            "type": current_node.get("type", "unknown"),
            "description": current_node.get("exploration_summary") or current_node.get("description", ""),
            "notable_elements": current_node.get("notable_elements") or current_node.get("contents", []),
        },
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


def suggest_map_destination(campaign_map: CampaignMap, actions_with_rolls: list[dict]) -> str | None:
    """Wskazuje sąsiedni węzeł dla udanej deklaracji ruchu drużyny."""
    layout = campaign_map.layout or {}
    current_node_id = campaign_map.current_node_id or layout.get("start_node_id")
    adjacent = adjacent_node_ids(layout, current_node_id)
    if not adjacent:
        return None
    discovered = list(campaign_map.discovered_node_ids or [])
    nodes = [node for node in layout.get("nodes", []) if node.get("id") in adjacent]
    movement_pattern = re.compile(
        r"\b(ide|idziemy|pojde|udaj\w*|wchodz\w*|wychodz\w*|przechodz\w*|"
        r"przekracza\w*|rusza\w*|wyrusza\w*|przemieszcza\w*|"
        r"podaza\w*|wkracza\w*|wraca\w*|cofa\w*|ucieka\w*|odwrot)\b"
    )
    for action in actions_with_rolls:
        if action.get("outcome_tier") in {"failure", "critical_failure"}:
            continue
        declaration = normalize_game_text(action_mechanics_text(action.get("action_text") or ""))
        if not movement_pattern.search(declaration):
            continue
        for node in nodes:
            names = (node.get("custom_name"), node.get("name"))
            if any(normalize_game_text(name) in declaration for name in names if name):
                return str(node["id"])
        if re.search(r"\b(wraca\w*|cofa\w*|odwrot)\b", declaration):
            for node_id in reversed(discovered):
                if node_id in adjacent and node_id != current_node_id:
                    return node_id
        for node in nodes:
            if node["id"] not in discovered:
                return str(node["id"])
        return str(nodes[0]["id"])
    return None


def apply_map_narrative_update(
    campaign_map: CampaignMap,
    map_update,
    turn_number: int,
    fallback_destination_node_id: str | None = None,
) -> None:
    """Zapisuje kronikę, ale przemieszczenie bierze wyłącznie z mechaniki ruchu."""
    if not map_update and not fallback_destination_node_id:
        return

    layout = json.loads(json.dumps(campaign_map.layout or {}))
    current_node_id = campaign_map.current_node_id or layout.get("start_node_id")
    allowed_ids = {current_node_id, *adjacent_node_ids(layout, current_node_id)}
    destination_node_id = (
        fallback_destination_node_id
        if fallback_destination_node_id in allowed_ids
        else current_node_id
    )
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
        summary = decode_display_text(map_update.location_summary) if map_update else ""
        if summary:
            node["exploration_summary"] = summary[:1200]
        elements = [
            decode_display_text(str(element))[:100]
            for element in ((map_update.notable_elements or [])[:5] if map_update else [])
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
    normalized = normalized.translate(POLISH_CHAR_TRANSLATION)
    return "".join(character for character in normalized if not unicodedata.combining(character))


def decode_display_text(value: str | None) -> str:
    """Dekoduje encje zwrócone przez model; UI nadal renderuje wynik bezpiecznie przez x-text."""
    return html.unescape(value or "").replace("\u00a0", " ").strip()


def validate_action_item_claim(
    action_text: str,
    inventory: List[InventoryItem],
    ignored_labels: set[str] | None = None,
    world_pack: WorldPack | None = None,
) -> str | None:
    """Blokuje jawne użycie broni lub pancerza, którego postać nie ma albo nie założyła."""
    normalized_action = normalize_game_text(action_mechanics_text(action_text))
    action_clauses = re.split(r"[,.!?;]", normalized_action)
    effectively_equipped_items = get_effectively_equipped_items(inventory)
    ignored_labels = ignored_labels or set()
    world_pack = world_pack or get_default_world_pack()

    for vocabulary in world_pack.item_vocabulary:
        label = vocabulary.label
        if label in ignored_labels:
            continue
        claim_aliases = tuple(normalize_game_text(alias) for alias in vocabulary.aliases)
        inventory_aliases = claim_aliases
        item_types = set(vocabulary.item_types)
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    default_world = get_default_world_pack()
    narrative_profile = default_world.narrative_profile
    # Inicjalizacja bazy danych przy starcie
    await init_db()
    logger.info("Baza danych zainicjalizowana.")
    if not settings.GM_PIN:
        logger.warning("GM_PIN nie jest ustawiony. Narzędzia Mistrza Gry pozostaną zablokowane.")
    if not is_web_push_configured():
        logger.info("Web Push jest wyłączony. Uzupełnij VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY i VAPID_SUBJECT.")
    # Upewnij się, że istnieje domyślna sesja
    async for db in get_db():
        stmt = select(GameSession).where(GameSession.room_code == "kampania-1")
        result = await db.execute(stmt)
        session = result.scalar_one_or_none()
        if not session:
            new_session = GameSession(
                room_code="kampania-1",
                world_pack_id=default_world.id,
                world_pack_version=default_world.version,
                title=narrative_profile.default_title,
                setting_theme=narrative_profile.setting_theme,
                campaign_intro=narrative_profile.campaign_intro,
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
                next_turn_prompt=narrative_profile.first_challenge,
                suggested_actions=list(narrative_profile.suggested_actions),
                image_prompt=narrative_profile.initial_image_prompt,
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
