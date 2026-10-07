import asyncio
import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.action_dialogue import preserve_action_dialogue
from app.combat import (
    action_dc,
    ensure_enemy_encounter,
    infer_action_intent,
    infer_action_intent_details,
    resolve_boss_turn,
    resolve_status_turn,
    status_roll_penalty,
)
from app.database import get_db
from app.dice import (
    calculate_item_modifier_details,
    deduce_tested_attribute_details,
    resolve_dice_roll,
)
from app.gemini_service import resolve_turn_with_gemini
from app.loot import (
    reconcile_loot_narration,
    resolve_inventory_mechanics,
    strip_loot_claims,
    validate_special_action,
)
from app.magic import get_ability, validate_ability_action
from app.models import (
    CampaignMap,
    Character,
    GameSession,
    NamedLoreEntity,
    PlayerAction,
    Turn,
)
from app.push_service import schedule_web_push
from app.schemas import InterpretActionRequest, ResolveTurnRequest, SubmitActionRequest
from app.services.campaign_goal_service import advance_campaign_goal
from app.services.runtime import (
    XP_LEVEL_THRESHOLDS,
    apply_map_narrative_update,
    build_map_narrator_context,
    logger,
    normalize_game_text,
    replace_campaign_map,
    suggest_map_destination,
    validate_action_item_claim,
)
from app.services.market_service import close_market_visit
from app.services.world_service import get_session_world_pack
from app.services.room_access import require_room
from app.targeting import infer_character_attack_target
from app.websocket_manager import ws_manager
from app.worlds.models import WorldPack


OUTCOME_XP = {
    "critical_success": 120,
    "success": 80,
    "partial_success": 60,
    "failure": 50,
    "critical_failure": 40,
}


def xp_for_outcome(outcome_tier: str | None) -> int:
    """XP jest wynikiem zapisanej mechaniki, a nie swobodnej decyzji narratora."""
    return OUTCOME_XP.get(outcome_tier or "failure", OUTCOME_XP["failure"])


async def retry_turn(
    request: Request,
    room_code: str = "kampania-1",
    db: AsyncSession = Depends(get_db),
):
    require_room(request, room_code)
    s_stmt = (
        select(GameSession)
        .where(GameSession.room_code == room_code)
        .options(selectinload(GameSession.turns))
    )
    session = (await db.execute(s_stmt)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesja nie istnieje")
    if session.status == "completed":
        raise HTTPException(status_code=409, detail="Kampania została zakończona")
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

async def resolve_turn_endpoint(
    request: Request,
    payload: ResolveTurnRequest = ResolveTurnRequest(),
    db: AsyncSession = Depends(get_db),
):
    require_room(request, payload.room_code)
    s_stmt = (
        select(GameSession)
        .where(GameSession.room_code == payload.room_code)
        .options(
            selectinload(GameSession.characters),
            selectinload(GameSession.turns).selectinload(Turn.actions),
        )
    )
    session = (await db.execute(s_stmt)).scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Sesja nie istnieje")
    if session.status == "completed":
        raise HTTPException(status_code=409, detail="Kampania została zakończona")

    if session.is_turn_resolving:
        raise HTTPException(status_code=400, detail="Mistrz Gry właśnie rozpatruje tę turę. Poczekaj na zakończenie.")

    turn = next((t for t in session.turns if t.turn_number == session.current_turn_number), None)
    if not turn:
        raise HTTPException(status_code=404, detail="Brak aktywnej tury w sesji")

    alive_characters = [
        character for character in session.characters
        if character.is_alive and character.is_participating
    ]
    if not alive_characters:
        raise HTTPException(status_code=400, detail="Brak aktywnych, żyjących postaci w tej turze")
    submitted_ids = {action.character_id for action in turn.actions}
    active_character_ids = {character.id for character in alive_characters}
    if not (submitted_ids & active_character_ids):
        raise HTTPException(status_code=400, detail="Żaden aktywny gracz nie złożył jeszcze akcji w tej turze")
    missing_characters = [character.name for character in alive_characters if character.id not in submitted_ids]
    if missing_characters:
        raise HTTPException(
            status_code=400,
            detail=f"Brak akcji dla: {', '.join(missing_characters)}. Poczekaj na graczy albo wybierz akcję zastępczą.",
        )

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

def interpret_player_action(
    character: Character,
    action_text: str,
    magic_ability: dict | None = None,
    explicit_intent: str | None = None,
    explicit_stat: str | None = None,
    target_ref: str | None = None,
    world_pack: WorldPack | None = None,
) -> dict:
    forced_intent = magic_ability["intent"] if magic_ability else explicit_intent
    intent_details = infer_action_intent_details(action_text, forced_intent)
    resolved_intent = str(intent_details["intent"])

    forced_stat = magic_ability["tested_stat"] if magic_ability else explicit_stat
    if not magic_ability and resolved_intent == "interact" and target_ref:
        feature = next(
            (
                item for item in (character.session.active_boss_features or [])
                if isinstance(item, dict)
                and str(item.get("id")) == str(target_ref)
                and item.get("state") == "active"
            ),
            None,
        )
        if feature and feature.get("required_stat"):
            forced_stat = str(feature["required_stat"])

    stat_details = deduce_tested_attribute_details(
        action_text,
        character,
        resolved_intent,
        forced_stat,
        world_pack,
    )
    return {
        "intent": resolved_intent,
        "tested_stat": str(stat_details["tested_stat"]),
        "intent_confidence": float(intent_details["confidence"]),
        "stat_confidence": float(stat_details["confidence"]),
        "reason": f"{intent_details['reason']}; {stat_details['reason']}",
    }


async def interpret_action(
    payload: InterpretActionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    c_stmt = (
        select(Character)
        .options(selectinload(Character.session), selectinload(Character.inventory))
        .where(Character.id == payload.character_id)
    )
    character = (await db.execute(c_stmt)).scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Postać nie istnieje")
    require_room(request, character.session.room_code)
    if not character.is_participating:
        raise HTTPException(status_code=409, detail="Postać jest na przerwie i nie bierze udziału w turze")

    world_pack = get_session_world_pack(character.session)
    ability, ability_error = validate_ability_action(
        world_pack,
        character.class_id,
        character.level,
        payload.action_text.strip(),
        payload.selected_ability_id,
    )
    if ability_error:
        raise HTTPException(status_code=400, detail=ability_error)
    if payload.named_attack_id:
        await require_learned_attack(db, character, payload.named_attack_id)
    interpretation = interpret_player_action(
        character,
        payload.action_text.strip(),
        magic_ability=ability,
        explicit_intent="attack" if payload.named_attack_id else payload.intent,
        explicit_stat=payload.tested_stat,
        target_ref=payload.target_ref,
        world_pack=world_pack,
    )
    if interpretation["intent"] == "attack":
        party = (await db.execute(select(Character).where(
            Character.session_id == character.session_id
        ))).scalars().all()
        target, target_error = infer_character_attack_target(
            payload.action_text.strip(), character, list(party)
        )
        interpretation["target_name"] = target.name if target else None
        interpretation["target_error"] = target_error
    return interpretation


async def require_learned_attack(
    db: AsyncSession, character: Character, named_attack_id: int,
) -> NamedLoreEntity:
    attack = (await db.execute(select(NamedLoreEntity).where(
        NamedLoreEntity.id == named_attack_id,
        NamedLoreEntity.session_id == character.session_id,
        NamedLoreEntity.named_by_character_id == character.id,
        NamedLoreEntity.category == "attack",
        NamedLoreEntity.is_active.is_(True),
    ))).scalar_one_or_none()
    if not attack:
        raise HTTPException(status_code=400, detail="Ta postać nie zna wybranego ataku")
    return attack


async def submit_action(
    payload: SubmitActionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Pobierz postać z sesją
    c_stmt = (
        select(Character)
        .options(
            selectinload(Character.session).selectinload(GameSession.campaign_map),
            selectinload(Character.inventory),
        )
        .where(Character.id == payload.character_id)
    )
    c_res = await db.execute(c_stmt)
    character = c_res.scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Postać nie istnieje")
    require_room(request, character.session.room_code)
    if not character.is_alive:
        raise HTTPException(status_code=400, detail="Postać w agonii, stabilna lub martwa nie może składać akcji.")
    if not character.is_participating:
        raise HTTPException(status_code=409, detail="Postać jest na przerwie i nie może składać akcji")
    if character.session.status == "completed":
        raise HTTPException(status_code=409, detail="Kampania została zakończona")

    action_text = payload.action_text.strip()
    world_pack = get_session_world_pack(character.session)
    magic_ability, magic_action_error = validate_ability_action(
        world_pack,
        character.class_id,
        character.level,
        action_text,
        payload.selected_ability_id,
    )
    if magic_action_error:
        raise HTTPException(status_code=400, detail=magic_action_error)
    if payload.named_attack_id:
        await require_learned_attack(db, character, payload.named_attack_id)
        if not (character.session.active_boss_hp and character.session.active_boss_hp > 0):
            raise HTTPException(status_code=400, detail="Odkryty atak można wybrać podczas walki")
    action_intent = (
        magic_ability["intent"] if magic_ability else
        "attack" if payload.named_attack_id else payload.intent
    )
    action_target_ref = (
        payload.target_ref
        if magic_ability and magic_ability["intent"] == "support"
        else magic_ability["target_ref"] if magic_ability
        else payload.target_ref
    )
    interpretation = interpret_player_action(
        character,
        action_text,
        magic_ability=magic_ability,
        explicit_intent=action_intent,
        explicit_stat=payload.tested_stat,
        target_ref=action_target_ref,
        world_pack=world_pack,
    )
    resolved_intent = interpretation["intent"]
    if payload.named_attack_id and resolved_intent != "attack":
        raise HTTPException(status_code=400, detail="Odkryta technika wymaga ataku")
    resolved_stat = interpretation["tested_stat"]
    if resolved_intent == "attack":
        party = (await db.execute(select(Character).where(
            Character.session_id == character.session_id
        ))).scalars().all()
        attack_target, target_error = infer_character_attack_target(
            action_text, character, list(party)
        )
        if target_error:
            raise HTTPException(status_code=400, detail=target_error)
        if attack_target and payload.named_attack_id:
            raise HTTPException(status_code=400, detail="Odkryta technika dotyczy głównego przeciwnika, nie postaci z drużyny.")
        action_target_ref = (
            str(attack_target.id) if attack_target else
            magic_ability["target_ref"] if magic_ability else None
        )
    if resolved_intent == "support":
        try:
            support_target_id = int(action_target_ref or "")
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Wybierz konkretnego sojusznika jako cel wsparcia.")
        target_stmt = select(Character).where(
            Character.id == support_target_id,
            Character.session_id == character.session_id,
        )
        support_target = (await db.execute(target_stmt)).scalar_one_or_none()
        if not support_target:
            raise HTTPException(status_code=400, detail="Wskaż postać z drużyny.")
        if not support_target.is_participating:
            raise HTTPException(status_code=400, detail="Postać na przerwie nie może być celem wsparcia.")
        is_revive = bool(magic_ability and magic_ability["mechanic_key"] == "revive")
        if is_revive and support_target.death_state != "dead":
            raise HTTPException(status_code=400, detail="Ta zdolność wymaga wskazania poległego bohatera.")
        if support_target.death_state == "dead" and not (
            is_revive
        ):
            raise HTTPException(status_code=400, detail="Poległego bohatera może przywrócić tylko zdolność o efekcie wskrzeszenia.")
        action_target_ref = str(support_target.id)
    ignored_item_claim = (
        magic_ability.get("mechanic_params", {}).get("ignore_item_claim")
        if magic_ability else None
    )
    ignored_item_claims = {str(ignored_item_claim)} if ignored_item_claim else set()
    item_claim_error = validate_action_item_claim(
        action_text,
        character.inventory,
        ignored_labels=ignored_item_claims,
        world_pack=world_pack,
    )
    if item_claim_error:
        raise HTTPException(status_code=400, detail=item_claim_error)

    session = character.session
    special_action_error = validate_special_action(
        action_text=action_text,
        inventory=character.inventory,
        session=session,
        current_turn_number=session.current_turn_number,
        inferred_intent=resolved_intent,
        uses_magic=bool(magic_ability),
        campaign_map=session.campaign_map,
        world_pack=world_pack,
        craft_item_ids=payload.craft_item_ids,
    )
    if special_action_error:
        raise HTTPException(status_code=400, detail=special_action_error)
    if session.is_turn_resolving:
        raise HTTPException(status_code=400, detail="Mistrz Gry właśnie rozpatruje tę turę. Poczekaj na zakończenie.")

    # Pobierz aktywną turę
    t_stmt = (
        select(Turn)
        .options(
            selectinload(Turn.actions).selectinload(PlayerAction.character),
            selectinload(Turn.proxy_decisions),
        )
        .where(Turn.session_id == session.id, Turn.turn_number == session.current_turn_number)
        .with_for_update()
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
    await db.refresh(character, attribute_names=["participation_status"])
    if not character.is_participating:
        raise HTTPException(status_code=409, detail="Postać została wysłana na przerwę")

    # Sprawdź czy gracz już złożył akcję w tej turze
    act_stmt = select(PlayerAction).where(PlayerAction.turn_id == turn.id)
    act_res = await db.execute(act_stmt)
    all_turn_actions = act_res.scalars().all()

    existing_action = next((a for a in all_turn_actions if a.character_id == character.id), None)
    proxy_was_overridden = bool(existing_action and existing_action.submission_source == "party_vote")
    if existing_action:
        existing_action.action_text = action_text
        existing_action.magic_ability_id = magic_ability["id"] if magic_ability else None
        existing_action.ability_id = magic_ability["id"] if magic_ability else None
        existing_action.named_attack_id = payload.named_attack_id
        existing_action.intent = resolved_intent
        existing_action.target_ref = action_target_ref
        existing_action.tested_stat = resolved_stat
        existing_action.submission_source = "player"
        existing_action.craft_item_ids = payload.craft_item_ids
        existing_action.submitted_at = datetime.now(timezone.utc)
    else:
        new_action = PlayerAction(
            turn_id=turn.id,
            character_id=character.id,
            action_text=action_text,
            magic_ability_id=magic_ability["id"] if magic_ability else None,
            ability_id=magic_ability["id"] if magic_ability else None,
            named_attack_id=payload.named_attack_id,
            intent=resolved_intent,
            target_ref=action_target_ref,
            tested_stat=resolved_stat,
            submission_source="player",
            craft_item_ids=payload.craft_item_ids,
        )
        db.add(new_action)
    if proxy_was_overridden:
        decision = next(
            (item for item in turn.proxy_decisions if item.target_character_id == character.id),
            None,
        )
        if decision:
            decision.status = "overridden"
            decision.finalized_at = datetime.now(timezone.utc)
    await db.commit()

    # Pobierz aktualne akcje dla tej tury bezpośrednio z bazy
    updated_act_stmt = select(PlayerAction).where(PlayerAction.turn_id == turn.id)
    current_actions = (await db.execute(updated_act_stmt)).scalars().all()
    submitted_ids = {a.character_id for a in current_actions}

    # Pobierz wszystkie żywe postacie w tej sesji
    all_chars_stmt = (
        select(Character)
        .where(
            Character.session_id == session.id,
            Character.is_alive == True,
            Character.participation_status == "active",
        )
    )
    all_chars = (await db.execute(all_chars_stmt)).scalars().all()

    total_alive_players = len(all_chars)
    ready_count = len(submitted_ids & {character.id for character in all_chars})

    # Powiadom graczy o złożeniu akcji
    await ws_manager.broadcast_to_session(session.id, {
        "type": "PLAYER_ACTION_SUBMITTED",
        "character_id": character.id,
        "character_name": character.name,
        "ready_count": ready_count,
        "total_players": total_alive_players,
    })
    if proxy_was_overridden:
        await ws_manager.broadcast_to_session(session.id, {
            "type": "PROXY_ACTION_OVERRIDDEN",
            "character_id": character.id,
            "character_name": character.name,
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
            participating_characters = [
                character for character in characters if character.is_participating
            ]
            lore_stmt = select(NamedLoreEntity).where(NamedLoreEntity.session_id == session_id)
            lore_entities = (await db.execute(lore_stmt)).scalars().all()
            learned_attacks = {
                lore.id: lore for lore in lore_entities
                if lore.category == "attack" and lore.is_active
            }
            for action in turn.actions:
                learned = learned_attacks.get(action.named_attack_id)
                if learned is None or learned.named_by_character_id != action.character_id:
                    action.named_attack_id = None
            world_pack = get_session_world_pack(session)
            ensure_enemy_encounter(session, characters, world_pack)
            map_stmt = select(CampaignMap).where(CampaignMap.session_id == session_id)
            campaign_map = (await db.execute(map_stmt)).scalar_one_or_none()
            if campaign_map is None:
                campaign_map = await replace_campaign_map(db, session)

            # 1. Mechanika tury jest zapisywana dokładnie raz. Retry ponawia wyłącznie narrację.
            actions_with_rolls = []
            if turn.mechanics_resolved_at is None:
                roll_context_events = []
                living_characters = [
                    character for character in participating_characters if character.is_alive
                ]
                average_level = (
                    sum(character.level for character in living_characters) / len(living_characters)
                    if living_characters else 1
                )
                for action in turn.actions:
                    char = char_map.get(action.character_id)
                    if not char or not char.is_participating:
                        continue

                    action.intent = infer_action_intent(action.action_text, action.intent)
                    if action.intent == "attack" and not action.target_ref:
                        target, _ = infer_character_attack_target(
                            action.action_text, char, list(characters)
                        )
                        if target:
                            action.target_ref = str(target.id)
                    dc, tested_stat_override = action_dc(
                        session, action,
                        challenge_tier=turn.challenge_tier,
                        average_level=average_level,
                    )
                    if action.intent == "attack" and str(action.target_ref or "").isdigit():
                        target = char_map.get(int(action.target_ref))
                        if target and target.id != char.id:
                            dc = max(10, 12 + int(target.agility or 0))
                    action_ability_id = action.ability_id or action.magic_ability_id
                    action_ability = get_ability(world_pack, char.class_id, action_ability_id)
                    if action_ability:
                        tested_stat_override = action_ability["tested_stat"]
                    elif tested_stat_override is None:
                        tested_stat_override = action.tested_stat
                    roll_penalty = status_roll_penalty(char)
                    tested_stat, d20_raw, stat_mod, item_mod, total, outcome_tier = resolve_dice_roll(
                        action.action_text,
                        char,
                        dc=dc,
                        tested_stat_override=tested_stat_override,
                        roll_modifier=roll_penalty,
                        intent=action.intent,
                    )
                    action.tested_stat = tested_stat
                    action.dice_roll_raw = d20_raw
                    action.stat_modifier = stat_mod
                    action.item_modifier = item_mod
                    action.status_modifier = roll_penalty
                    action.dice_total = total
                    action.dc = dc
                    action.outcome_tier = outcome_tier
                    _, item_sources = calculate_item_modifier_details(
                        char,
                        tested_stat,
                        action_text=action.action_text,
                        intent=action.intent,
                    )
                    roll_context_events.append({
                        "type": "roll_context",
                        "character_id": char.id,
                        "actor": char.name,
                        "tested_stat": tested_stat,
                        "item_bonus": item_mod,
                        "item_sources": item_sources,
                        "status_modifier": roll_penalty,
                    })

                if session.active_boss_name and session.active_boss_hp and session.active_boss_hp > 0:
                    turn.combat_events = resolve_boss_turn(
                        session,
                        list(participating_characters),
                        list(turn.actions),
                        world_pack=world_pack,
                    )
                else:
                    turn.combat_events = resolve_status_turn(
                        list(participating_characters),
                        list(turn.actions),
                        world_pack=world_pack,
                    )
                inventory_resolution = resolve_inventory_mechanics(
                    session,
                    turn,
                    list(participating_characters),
                    campaign_map,
                    world_pack=world_pack,
                )
                turn.combat_events = [
                    *roll_context_events,
                    *(turn.combat_events or []),
                    *inventory_resolution.events,
                ]
                for new_item in inventory_resolution.new_items:
                    owner = char_map.get(new_item.character_id)
                    if owner and new_item not in owner.inventory:
                        owner.inventory.append(new_item)
                    db.add(new_item)
                for consumed_item in inventory_resolution.consumed_items:
                    owner = char_map.get(consumed_item.character_id)
                    if owner and consumed_item in owner.inventory:
                        owner.inventory.remove(consumed_item)
                    await db.delete(consumed_item)
                for event in inventory_resolution.events:
                    if event.get("type") == "merchant_arrived" and not any(
                        lore.category == "npc" and lore.custom_name == event["name"]
                        for lore in lore_entities
                    ):
                        db.add(NamedLoreEntity(
                            session_id=session.id,
                            category="npc",
                            original_description=event["greeting"],
                            custom_name=event["name"],
                            discovered_turn_number=turn.turn_number,
                            map_node_id=campaign_map.current_node_id if campaign_map else None,
                            npc_disposition="reserved",
                            npc_goal="Handluje podczas postoju drużyny.",
                        ))
                turn.mechanics_resolved_at = datetime.now(timezone.utc)
                await db.commit()

            roll_context_by_character_id = {
                int(event["character_id"]): event
                for event in (turn.combat_events or [])
                if (
                    isinstance(event, dict)
                    and event.get("type") == "roll_context"
                    and str(event.get("character_id") or "").isdigit()
                )
            }
            for action in turn.actions:
                char = char_map.get(action.character_id)
                if not char or not char.is_participating:
                    continue
                party_target = (
                    char_map.get(int(action.target_ref))
                    if action.intent == "attack" and str(action.target_ref or "").isdigit()
                    else None
                )
                roll_context = roll_context_by_character_id.get(char.id)
                if roll_context is not None:
                    item_sources = list(roll_context.get("item_sources") or [])
                else:
                    _, item_sources = calculate_item_modifier_details(
                        char,
                        action.tested_stat or "strength",
                        action_text=action.action_text,
                        intent=action.intent,
                    )
                actions_with_rolls.append({
                    "character_id": char.id,
                    "character_name": char.name,
                    "action_text": action.action_text,
                    "ability": get_ability(
                        world_pack,
                        char.class_id,
                        action.ability_id or action.magic_ability_id,
                    ),
                    "named_attack": (
                        learned_attacks[action.named_attack_id].custom_name
                        if action.named_attack_id in learned_attacks else None
                    ),
                    "magic_ability": get_ability(
                        world_pack,
                        char.class_id,
                        action.ability_id or action.magic_ability_id,
                    ),
                    "intent": action.intent,
                    "target_ref": action.target_ref,
                    "tested_stat": action.tested_stat,
                    "dice_roll_raw": action.dice_roll_raw,
                    "stat_modifier": action.stat_modifier,
                    "item_modifier": action.item_modifier,
                    "item_modifier_sources": item_sources,
                    "status_modifier": action.status_modifier or 0,
                    "dice_total": action.dice_total,
                    "dc": action.dc,
                    "outcome_tier": action.outcome_tier,
                    "boss_damage": 0 if party_target else int(action.damage_dealt or 0),
                    "character_damage": int(action.damage_dealt or 0) if party_target else 0,
                    "character_target_name": party_target.name if party_target else None,
                    "hp_delta": action.hp_delta or 0,
                    "xp_awarded": xp_for_outcome(action.outcome_tier),
                })

            map_context = build_map_narrator_context(campaign_map)
            suggested_map_destination = suggest_map_destination(campaign_map, actions_with_rolls)
            map_context["suggested_destination_node_id"] = suggested_map_destination

            # 2. Wywołanie Gemini API
            gemini_result = await resolve_turn_with_gemini(
                session=session,
                turn=turn,
                actions_with_rolls=actions_with_rolls,
                characters=participating_characters,
                lore_entities=lore_entities,
                map_context=map_context,
            )
            gemini_result.gm_story_narration = reconcile_loot_narration(
                gemini_result.gm_story_narration,
                list(turn.combat_events or []),
                world_pack,
            )
            gemini_result.gm_story_narration = preserve_action_dialogue(
                gemini_result.gm_story_narration, actions_with_rolls, participating_characters,
            )
            for event in (turn.combat_events or []):
                if isinstance(event, dict) and event.get("type") == "merchant_arrived":
                    gemini_result.gm_story_narration += "\n\n" + event["greeting"]
            for consequence in gemini_result.player_consequences:
                mechanical_action = next(
                    (
                        action for action in turn.actions
                        if action.character_id == consequence.character_id
                    ),
                    None,
                )
                if mechanical_action:
                    # Model opisuje wynik, lecz nie może zmienić mechanicznego
                    # bilansu HP, XP ani ekwipunku ustalonego przez serwer.
                    consequence.hp_delta = int(mechanical_action.hp_delta or 0)
                    consequence.xp_gained = xp_for_outcome(
                        mechanical_action.outcome_tier
                    )
                    consequence.new_items = []
                    consequence.removed_item_names = []
                consequence.individual_summary = (
                    strip_loot_claims(
                        consequence.individual_summary,
                        world_pack,
                        list(turn.combat_events or []),
                    )
                    or "Wynik akcji zapisano w rozstrzygnięciu tury."
                )
                consequence.individual_summary = preserve_action_dialogue(
                    consequence.individual_summary,
                    [
                        action for action in actions_with_rolls
                        if action["character_id"] == consequence.character_id
                    ],
                    participating_characters,
                )

            boss_defeated_this_turn = any(
                isinstance(event, dict) and event.get("type") == "boss_defeated"
                for event in (turn.combat_events or [])
            )
            stale_defeated_boss = bool(
                session.active_boss_name
                and session.active_boss_hp is not None
                and session.active_boss_hp <= 0
                and not boss_defeated_this_turn
            )
            if boss_defeated_this_turn or stale_defeated_boss:
                await db.execute(
                    update(NamedLoreEntity)
                    .where(
                        NamedLoreEntity.session_id == session.id,
                        NamedLoreEntity.category == world_pack.enemy_profile.lore_category_id,
                        NamedLoreEntity.is_active.is_(True),
                    )
                    .values(is_active=False)
                )
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

            # 3. Zastosowanie konsekwencji dla postaci. Narrator opisuje, ale
            # mechanika jest jedynym źródłem zmian HP, XP i ekwipunku.
            level_ups = []
            consequence_by_character = {
                consequence.character_id: consequence
                for consequence in gemini_result.player_consequences
            }
            for act in turn.actions:
                char = char_map.get(act.character_id)
                if not char or not char.is_participating:
                    continue
                conseq = consequence_by_character.get(char.id)
                summary = (
                    conseq.individual_summary
                    if conseq else
                    "Mechaniczny wynik akcji został zapisany; narrator nie zwrócił osobnego podsumowania."
                )
                awarded_xp = xp_for_outcome(act.outcome_tier)

                # Przypisanie indywidualnego podsumowania do rekordu akcji
                act.gm_individual_summary = summary
                act.xp_gained = awarded_xp

                # XP i Awans (Level Up)
                char.xp += awarded_xp
                levels_gained = 0
                # Obsłuż również kilka awansów naraz przy dużej nagrodzie XP.
                while (
                    char.level + 1 in XP_LEVEL_THRESHOLDS
                    and char.xp >= XP_LEVEL_THRESHOLDS[char.level + 1]
                ):
                    char.level += 1
                    char.max_hp += 5
                    if getattr(char, "death_state", "alive") == "alive":
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

            # Zapisz turę
            turn.gm_narration = gemini_result.gm_story_narration
            turn.next_turn_prompt = gemini_result.next_turn_prompt
            turn.suggested_actions = gemini_result.suggested_actions
            turn.image_prompt = gemini_result.scene_image_prompt
            turn.status = "completed"
            previous_node_id = campaign_map.current_node_id
            market_state = dict(session.market_state or {})
            market_closes_on_departure = bool(
                market_state
                and not market_state.get("closed")
                and market_state.get("location_node_id") == previous_node_id
                and int(session.current_turn_number or 0)
                <= int(market_state.get("expires_turn") or 0)
            )
            apply_map_narrative_update(
                campaign_map,
                gemini_result.map_update,
                turn.turn_number,
                fallback_destination_node_id=suggested_map_destination,
            )
            if (
                market_closes_on_departure
                and campaign_map.current_node_id != previous_node_id
            ):
                close_market_visit(session)

            opportunity = gemini_result.naming_opportunity
            living = [
                character for character in participating_characters if character.is_alive
            ]
            if opportunity and not session.pending_naming_category and living:
                category = opportunity.category
                evidence = opportunity.scene_evidence.strip()
                normalized_story = " ".join(
                    gemini_result.gm_story_narration.casefold().split()
                )
                scene_confirmed = (
                    len(evidence) >= 12
                    and " ".join(evidence.casefold().split()) in normalized_story
                )
                eligible = living
                if category == "attack":
                    last_attack_turn = max(
                        (lore.discovered_turn_number or 0 for lore in lore_entities
                         if lore.category == "attack"), default=0,
                    )
                    eligible = [
                        character for character in living
                        if any(action.character_id == character.id
                               and action.intent == "attack"
                               and action.outcome_tier in {"success", "critical_success"}
                               for action in turn.actions)
                    ]
                    if opportunity.origin_character_id is not None:
                        eligible = [
                            character for character in eligible
                            if character.id == opportunity.origin_character_id
                        ]
                    elif eligible:
                        best_action = max(
                            (action for action in turn.actions
                             if action.character_id in {character.id for character in eligible}),
                            key=lambda action: action.damage_dealt or 0,
                        )
                        eligible = [
                            character for character in eligible
                            if character.id == best_action.character_id
                        ]
                    scene_confirmed = (
                        scene_confirmed and turn.turn_number >= 8
                        and turn.turn_number - last_attack_turn >= 8
                        and bool(eligible)
                    )
                elif category == "npc":
                    scene_confirmed = scene_confirmed and not any(
                        lore.category == "npc"
                        and normalize_game_text(lore.original_description)
                        == normalize_game_text(opportunity.description)
                        for lore in lore_entities
                    )
                elif category == "weapon":
                    awarded_names = {
                        event.get("actor") for event in (turn.combat_events or [])
                        if isinstance(event, dict) and event.get("type") == "item_found"
                    }
                    eligible = [character for character in living if character.name in awarded_names]
                    scene_confirmed = bool(eligible)
                else:
                    scene_confirmed = True
                if scene_confirmed and eligible:
                    chosen_char = secrets.choice(eligible)
                    session.pending_naming_category = category
                    session.pending_naming_prompt = opportunity.description
                    session.pending_naming_character_id = chosen_char.id
                    session.pending_naming_character_name = chosen_char.name
                    session.pending_naming_turn_number = turn.turn_number
                    session.pending_naming_map_node_id = campaign_map.current_node_id
                    session.pending_naming_question = opportunity.prompt_for_player
                    await ws_manager.broadcast_to_session(session.id, {
                        "type": "NAMING_REQUESTED",
                        "category": category,
                        "description": opportunity.description,
                        "prompt": opportunity.prompt_for_player,
                        "character_id": chosen_char.id,
                        "character_name": chosen_char.name,
                    })

            # 4. Otwórz nową turę
            new_turn_number = session.current_turn_number + 1
            session.current_turn_number = new_turn_number
            session.is_turn_resolving = False
            advance_campaign_goal(
                session,
                current_clue=gemini_result.next_turn_prompt,
                near_resolution=(
                    campaign_map.current_node_id
                    == (campaign_map.layout or {}).get("final_node_id")
                ),
            )

            next_turn = Turn(
                session_id=session.id,
                turn_number=new_turn_number,
                status="waiting_for_actions",
                gm_narration="",
                next_turn_prompt=gemini_result.next_turn_prompt,
                challenge_tier=gemini_result.next_challenge_tier,
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
            schedule_web_push(
                session.id,
                title="⚔️ Mistrz Gry wydał werdykt",
                body=f"Tura #{turn.turn_number} została zakończona. Czeka na Ciebie dalszy ciąg przygody.",
                tag=f"turn-{session.id}-{turn.turn_number}",
            )
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
