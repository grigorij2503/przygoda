import json
import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.combat import (
    build_enemy_encounter,
    ensure_enemy_encounter,
    infer_item_damage_power,
    set_character_downed,
    status_list,
)
from app.config import settings
from app.database import get_db
from app.gemini_service import generate_campaign_intro_ai, generate_party_prologue_ai
from app.magic import get_ability, get_ability_book
from app.map_generator import serialize_campaign_map
from app.models import (
    Character,
    GameSession,
    InventoryItem,
    NamedLoreEntity,
    PlayerAction,
    ProxyActionDecision,
    Turn,
)
from app.schemas import (
    CreateSessionRequest,
    GenerateIntroRequest,
    NameEntityRequest,
    PrologueRequest,
    SetupScenarioRequest,
    TriggerNamingRequest,
)
from app.services.runtime import (
    PROXY_ACTION_WAIT,
    apply_custom_location_name,
    as_utc,
    build_proxy_action_options,
    decode_display_text,
    finalize_proxy_decision,
    get_xp_progress,
    image_generation_day_bounds,
    replace_campaign_map,
    require_gm,
    serialize_proxy_decision,
)
from app.services.world_service import (
    get_session_world_pack,
    resolve_requested_world_pack,
    serialize_world_runtime,
)
from app.websocket_manager import ws_manager
from app.worlds.registry import WORLD_PACK_REGISTRY, WorldPackNotFoundError


async def get_current_session(room_code: str = "kampania-1", db: AsyncSession = Depends(get_db)):
    stmt = (
        select(GameSession)
        .where(GameSession.room_code == room_code)
        .options(
            selectinload(GameSession.characters).selectinload(Character.inventory),
            selectinload(GameSession.turns).selectinload(Turn.actions).selectinload(PlayerAction.character),
            selectinload(GameSession.turns).selectinload(Turn.proxy_decisions).selectinload(ProxyActionDecision.votes),
            selectinload(GameSession.lore_entities),
            selectinload(GameSession.campaign_map),
        )
    )
    res = await db.execute(stmt)
    game_session = res.scalar_one_or_none()
    if not game_session:
        raise HTTPException(status_code=404, detail="Sesja nie została znaleziona")
    world_pack = get_session_world_pack(game_session)
    session_changed = ensure_enemy_encounter(
        game_session, game_session.characters, world_pack
    )
    for character in game_session.characters:
        if character.current_hp <= 0 and getattr(character, "death_state", "alive") == "alive":
            set_character_downed(character)
            session_changed = True
    if game_session.campaign_map is None:
        game_session.campaign_map = await replace_campaign_map(db, game_session)
        session_changed = True
    current_turn = next(
        (t for t in game_session.turns if t.turn_number == game_session.current_turn_number),
        None,
    )
    now = datetime.now(timezone.utc)
    alive_character_ids = {character.id for character in game_session.characters if character.is_alive}
    characters_by_id = {character.id: character for character in game_session.characters}
    finalized_proxy_actions = []
    if current_turn and not game_session.is_turn_resolving:
        for decision in current_turn.proxy_decisions:
            previous_status = decision.status
            result = finalize_proxy_decision(db, decision, current_turn, alive_character_ids, now)
            if result:
                finalized_proxy_actions.append(result)
                session_changed = True
            elif decision.status != previous_status:
                session_changed = True

    if session_changed:
        await db.commit()

    for result in finalized_proxy_actions:
        target = characters_by_id.get(result["target_character_id"])
        await ws_manager.broadcast_to_session(game_session.id, {
            "type": "PROXY_ACTION_FINALIZED",
            **result,
            "target_character_name": target.name if target else "Nieznany bohater",
        })

    submitted_character_ids = [a.character_id for a in current_turn.actions] if current_turn else []
    current_actions_by_character = {
        action.character_id: action for action in current_turn.actions
    } if current_turn else {}
    proxy_decisions_by_character = {
        decision.target_character_id: decision for decision in current_turn.proxy_decisions
    } if current_turn else {}
    proxy_available_at = (
        (as_utc(current_turn.created_at) or now) + PROXY_ACTION_WAIT
        if current_turn else None
    )
    last_image_generated_at = as_utc(game_session.last_image_generated_at)
    image_day_start, next_image_day_start = image_generation_day_bounds(now)
    image_generated_today = bool(
        last_image_generated_at and last_image_generated_at >= image_day_start
    )
    next_image_available_at = next_image_day_start if image_generated_today else None

    characters_dto = []
    for c in game_session.characters:
        xp_progress = get_xp_progress(c.level, c.xp)
        current_action = current_actions_by_character.get(c.id)
        proxy_decision = proxy_decisions_by_character.get(c.id)
        characters_dto.append({
            "id": c.id,
            "player_name": c.player_name,
            "name": c.name,
            "character_class": c.character_class,
            "class_id": c.class_id,
            "level": c.level,
            "xp": c.xp,
            **xp_progress,
            "current_hp": c.current_hp,
            "max_hp": c.max_hp,
            "strength": c.strength,
            "agility": c.agility,
            "intellect": c.intellect,
            "charisma": c.charisma,
            "perception": c.perception,
            "unspent_stat_points": c.unspent_stat_points or 0,
            "is_alive": c.is_alive,
            "death_state": getattr(c, "death_state", "alive") or "alive",
            "death_failures": int(getattr(c, "death_failures", 0) or 0),
            "is_ready": bool(getattr(c, "is_ready", False)),
            "status_effects": status_list(c.status_effects),
            "ability_book": get_ability_book(world_pack, c.class_id, c.level),
            "magic_book": get_ability_book(world_pack, c.class_id, c.level),
            "quick_actions": [
                {
                    "id": action.id,
                    "icon": action.icon,
                    "label": action.label,
                    "text": action.action_text,
                    "intent": action.intent,
                    "tested_stat": action.tested_stat,
                    "target_ref": action.target_ref,
                }
                for action in WORLD_PACK_REGISTRY.get_class(
                    world_pack,
                    c.class_id,
                ).quick_actions
            ],
            "has_submitted_action": c.id in submitted_character_ids,
            "action_submission_source": current_action.submission_source if current_action else None,
            "proxy_action": {
                "available": bool(
                    c.is_alive
                    and not current_action
                    and current_turn
                    and current_turn.status == "waiting_for_actions"
                    and not game_session.is_turn_resolving
                    and proxy_available_at
                    and now >= proxy_available_at
                    and len(alive_character_ids) > 1
                ),
                "available_at": proxy_available_at.isoformat() if proxy_available_at else None,
                "options": (
                    proxy_decision.options if proxy_decision else build_proxy_action_options(game_session, c)
                ) if c.is_alive and current_turn else [],
                "decision": (
                    serialize_proxy_decision(proxy_decision, alive_character_ids)
                    if proxy_decision else None
                ),
            } if current_turn else None,
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
                    "character_name": characters_by_id.get(a.character_id).name if characters_by_id.get(a.character_id) else "Nieznany",
                    "action_text": a.action_text,
                    "magic_ability_id": a.magic_ability_id or a.ability_id,
                    "ability_id": a.ability_id or a.magic_ability_id,
                    "ability": get_ability(
                        world_pack,
                        characters_by_id.get(a.character_id).class_id,
                        a.ability_id or a.magic_ability_id,
                    ) if characters_by_id.get(a.character_id) else None,
                    "magic_ability": get_ability(
                        world_pack,
                        characters_by_id.get(a.character_id).class_id,
                        a.ability_id or a.magic_ability_id,
                    ) if characters_by_id.get(a.character_id) else None,
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
                    "submission_source": a.submission_source or "player",
                }
                for a in t.actions
            ],
        })

    return {
        "session_id": game_session.id,
        "room_code": game_session.room_code,
        "world_pack_id": world_pack.id,
        "world_pack_version": world_pack.version,
        "world_pack": serialize_world_runtime(world_pack),
        "title": game_session.title,
        "setting_theme": game_session.setting_theme,
        "campaign_intro": game_session.campaign_intro,
        "current_turn_number": game_session.current_turn_number,
        "is_turn_resolving": game_session.is_turn_resolving,
        "server_time": now.isoformat(),
        "image_generation": {
            "can_generate": not image_generated_today,
            "last_generated_at": (
                last_image_generated_at.isoformat() if last_image_generated_at else None
            ),
            "next_available_at": (
                next_image_available_at.isoformat() if next_image_available_at else None
            ),
        },
        "proxy_action_config": {
            "wait_hours": settings.PROXY_ACTION_WAIT_HOURS,
            "vote_hours": settings.PROXY_ACTION_VOTE_HOURS,
        },
        "inventory_rules": {
            "crafting_available": (
                int(game_session.crafting_available_until_turn or 0)
                == game_session.current_turn_number
            ),
            "crafting_available_until_turn": int(
                game_session.crafting_available_until_turn or 0
            ),
            "current_location_searched": bool(
                game_session.campaign_map
                and game_session.campaign_map.current_node_id
                in (game_session.looted_location_ids or [])
            ),
        },
        "status": getattr(game_session, "status", "in_progress") or "in_progress",
        "active_enemy": {
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


async def generate_intro(payload: GenerateIntroRequest, request: Request):
    require_gm(request)
    try:
        world_pack = WORLD_PACK_REGISTRY.get(
            payload.world_pack_id, payload.world_pack_version
        )
    except WorldPackNotFoundError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return await generate_campaign_intro_ai(
        payload.scenario_type, payload.tone, world_pack
    )

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
        world_pack = get_session_world_pack(session)
        narrative_profile = world_pack.narrative_profile
        session.title = payload.title or narrative_profile.default_title
        session.setting_theme = payload.setting_theme or narrative_profile.setting_theme
        session.campaign_intro = payload.campaign_intro or narrative_profile.campaign_intro
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
        session.last_loot_character_id = None
        session.looted_location_ids = []
        session.crafting_available_until_turn = 0
        session.pending_naming_category = None
        session.pending_naming_prompt = None
        session.pending_naming_character_id = None
        session.pending_naming_character_name = None
        await db.execute(
            update(Character)
            .where(Character.session_id == session.id)
            .values(status_effects=[], death_state="alive", death_failures=0, is_alive=True)
        )

        # Nowa kampania nie dziedziczy nazwanych odkryć z poprzedniej.
        await db.execute(
            delete(NamedLoreEntity).where(NamedLoreEntity.session_id == session.id)
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
            gm_narration=session.campaign_intro,
            next_turn_prompt="Co zamierzacie uczynić?",
            suggested_actions=list(narrative_profile.suggested_actions),
            image_prompt=narrative_profile.initial_image_prompt,
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

    world_pack = resolve_requested_world_pack(
        session,
        payload.world_pack_id,
        payload.world_pack_version,
        allow_new_campaign_reset=True,
    )
    session.world_pack_id = world_pack.id
    session.world_pack_version = world_pack.version

    narrative_profile = world_pack.narrative_profile
    scenario_type = payload.scenario_type or narrative_profile.scenario_options[0]
    session.title = narrative_profile.lobby_title_template.format(
        scenario_type=scenario_type
    )
    session.setting_theme = payload.tone or narrative_profile.setting_theme
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
    session.last_loot_character_id = None
    session.looted_location_ids = []
    session.crafting_available_until_turn = 0
    session.pending_naming_category = None
    session.pending_naming_prompt = None
    session.pending_naming_character_id = None
    session.pending_naming_character_name = None

    # Wyczyść postacie z poprzedniej wyprawy, aby drużyna mogła stworzyć świeże postacie pod nowy scenariusz
    for c in list(session.characters):
        await db.delete(c)

    await db.execute(
        delete(NamedLoreEntity).where(NamedLoreEntity.session_id == session.id)
    )

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
    turn1.next_turn_prompt = narrative_profile.lobby_prompt
    turn1.challenge_tier = "standard"
    turn1.suggested_actions = []
    turn1.image_prompt = narrative_profile.initial_image_prompt

    await replace_campaign_map(db, session)

    await db.commit()

    await ws_manager.broadcast_to_session(session.id, {
        "type": "LOBBY_STARTED",
        "title": session.title,
        "setting_theme": session.setting_theme,
        "status": "lobby"
    })

    return {"success": True, "status": "lobby"}

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
        scenario_type=payload.scenario_type or get_session_world_pack(session).narrative_profile.scenario_options[0],
        tone=payload.tone or session.setting_theme
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
    turn1.challenge_tier = "standard"
    turn1.suggested_actions = prologue_data.suggested_actions
    turn1.status = "waiting_for_actions"
    turn1.image_prompt = get_session_world_pack(session).narrative_profile.initial_image_prompt

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

    world_pack = get_session_world_pack(session)
    enemy_category = world_pack.enemy_profile.lore_category_id
    if category == enemy_category:
        await db.execute(
            update(NamedLoreEntity)
            .where(
                NamedLoreEntity.session_id == session.id,
                NamedLoreEntity.category == enemy_category,
                NamedLoreEntity.is_active.is_(True),
            )
            .values(is_active=False)
        )

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

    # Stabilne pola active_boss_* przechowują ogólnego głównego przeciwnika.
    if category == enemy_category:
        encounter = build_enemy_encounter(
            session.characters, description, world_pack
        )
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
            description=world_pack.narrative_profile.named_weapon_description_template.format(
                character_name=char_name
            ),
            item_type="weapon",
            target_stat=world_pack.narrative_profile.named_weapon_target_stat,
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

async def trigger_naming(
    payload: TriggerNamingRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    require_gm(request)

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
