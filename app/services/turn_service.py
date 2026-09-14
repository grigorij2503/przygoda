import asyncio
import secrets
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.combat import (
    action_dc,
    ensure_boss_encounter,
    infer_action_intent,
    infer_action_intent_details,
    resolve_boss_turn,
    resolve_status_turn,
    set_character_downed,
    status_roll_penalty,
)
from app.database import get_db
from app.dice import deduce_tested_attribute_details, resolve_dice_roll
from app.gemini_service import resolve_turn_with_gemini
from app.loot import resolve_inventory_mechanics, validate_special_action
from app.magic import get_magic_ability, get_magic_casting_stat, validate_magic_action
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
from app.services.runtime import (
    XP_LEVEL_THRESHOLDS,
    apply_map_narrative_update,
    build_map_narrator_context,
    logger,
    normalize_game_text,
    replace_campaign_map,
    validate_action_item_claim,
)
from app.websocket_manager import ws_manager


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

async def resolve_turn_endpoint(payload: ResolveTurnRequest = ResolveTurnRequest(), db: AsyncSession = Depends(get_db)):
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

    if session.is_turn_resolving:
        raise HTTPException(status_code=400, detail="Mistrz Gry właśnie rozpatruje tę turę. Poczekaj na zakończenie.")

    turn = next((t for t in session.turns if t.turn_number == session.current_turn_number), None)
    if not turn:
        raise HTTPException(status_code=404, detail="Brak aktywnej tury w sesji")

    if not turn.actions:
        raise HTTPException(status_code=400, detail="Żaden gracz nie złożył jeszcze akcji w tej turze")

    alive_characters = [character for character in session.characters if character.is_alive]
    submitted_ids = {action.character_id for action in turn.actions}
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
) -> dict:
    forced_intent = magic_ability["intent"] if magic_ability else explicit_intent
    intent_details = infer_action_intent_details(action_text, forced_intent)
    resolved_intent = str(intent_details["intent"])

    forced_stat = get_magic_casting_stat(character.character_class) if magic_ability else explicit_stat
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
    )
    return {
        "intent": resolved_intent,
        "tested_stat": str(stat_details["tested_stat"]),
        "intent_confidence": float(intent_details["confidence"]),
        "stat_confidence": float(stat_details["confidence"]),
        "reason": f"{intent_details['reason']}; {stat_details['reason']}",
    }


async def interpret_action(payload: InterpretActionRequest, db: AsyncSession = Depends(get_db)):
    c_stmt = (
        select(Character)
        .options(selectinload(Character.session), selectinload(Character.inventory))
        .where(Character.id == payload.character_id)
    )
    character = (await db.execute(c_stmt)).scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Postać nie istnieje")

    magic_ability = get_magic_ability(character.character_class, payload.selected_ability_id)
    if magic_ability and character.level < magic_ability["required_level"]:
        magic_ability = None
    return interpret_player_action(
        character,
        payload.action_text.strip(),
        magic_ability=magic_ability,
        explicit_intent=payload.intent,
        explicit_stat=payload.tested_stat,
        target_ref=payload.target_ref,
    )


async def submit_action(payload: SubmitActionRequest, db: AsyncSession = Depends(get_db)):
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
    if not character.is_alive:
        raise HTTPException(status_code=400, detail="Postać w agonii, stabilna lub martwa nie może składać akcji.")

    action_text = payload.action_text.strip()
    magic_ability, magic_action_error = validate_magic_action(
        character.character_class,
        character.level,
        action_text,
        payload.selected_ability_id,
    )
    if magic_action_error:
        raise HTTPException(status_code=400, detail=magic_action_error)
    action_intent = magic_ability["intent"] if magic_ability else payload.intent
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
    )
    resolved_intent = interpretation["intent"]
    resolved_stat = interpretation["tested_stat"]
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
        if not support_target or support_target.id == character.id:
            raise HTTPException(status_code=400, detail="Wsparcie musi wskazywać inną postać z drużyny.")
        if magic_ability and magic_ability["id"] == "resurrection" and support_target.death_state != "dead":
            raise HTTPException(status_code=400, detail="Wskrzeszenie wymaga wskazania poległego bohatera.")
        if support_target.death_state == "dead" and not (
            magic_ability and magic_ability["id"] == "resurrection"
        ):
            raise HTTPException(status_code=400, detail="Poległego bohatera może przywrócić tylko zdolność Wskrzeszenie.")
        action_target_ref = str(support_target.id)
    ignored_item_claims = (
        {"Tarcza"} if magic_ability and magic_ability["id"] == "spectral_shield" else set()
    )
    item_claim_error = validate_action_item_claim(
        action_text,
        character.inventory,
        ignored_labels=ignored_item_claims,
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
        existing_action.intent = resolved_intent
        existing_action.target_ref = action_target_ref
        existing_action.tested_stat = resolved_stat
        existing_action.submission_source = "player"
        existing_action.submitted_at = datetime.now(timezone.utc)
    else:
        new_action = PlayerAction(
            turn_id=turn.id,
            character_id=character.id,
            action_text=action_text,
            magic_ability_id=magic_ability["id"] if magic_ability else None,
            ability_id=magic_ability["id"] if magic_ability else None,
            intent=resolved_intent,
            target_ref=action_target_ref,
            tested_stat=resolved_stat,
            submission_source="player",
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
            ensure_boss_encounter(session, characters)
            map_stmt = select(CampaignMap).where(CampaignMap.session_id == session_id)
            campaign_map = (await db.execute(map_stmt)).scalar_one_or_none()
            if campaign_map is None:
                campaign_map = await replace_campaign_map(db, session)

            # 1. Mechanika tury jest zapisywana dokładnie raz. Retry ponawia wyłącznie narrację.
            actions_with_rolls = []
            if turn.mechanics_resolved_at is None:
                for action in turn.actions:
                    char = char_map.get(action.character_id)
                    if not char:
                        continue

                    action.intent = infer_action_intent(action.action_text, action.intent)
                    dc, tested_stat_override = action_dc(session, action)
                    action_ability_id = action.ability_id or action.magic_ability_id
                    if get_magic_ability(char.character_class, action_ability_id):
                        tested_stat_override = get_magic_casting_stat(char.character_class)
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
                inventory_resolution = resolve_inventory_mechanics(
                    session,
                    turn,
                    list(characters),
                    campaign_map,
                )
                turn.combat_events = [
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
                    "magic_ability": get_magic_ability(
                        char.character_class,
                        action.ability_id or action.magic_ability_id,
                    ),
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
                        NamedLoreEntity.category == "boss",
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

            # 3. Zastosowanie konsekwencji dla postaci
            level_ups = []
            boss_combat_event_types = {
                "player_attack", "boss_attack", "boss_defeated", "phase_change",
                "environment_success", "environment_failure", "defence", "support",
                "support_failed", "stabilized", "revived", "resurrection",
                "resurrection_failed", "death_failure", "character_died",
            }
            is_mechanical_combat = any(
                event.get("type") in boss_combat_event_types
                for event in (turn.combat_events or [])
                if isinstance(event, dict)
            )
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
                    narrative_delta = conseq.hp_delta
                    if getattr(char, "death_state", "alive") != "alive" and narrative_delta > 0:
                        narrative_delta = 0
                    char.current_hp = max(0, min(char.max_hp, char.current_hp + narrative_delta))
                    applied_hp_delta = char.current_hp - previous_hp
                    for act in turn.actions:
                        if act.character_id == char.id:
                            act.hp_delta = int(act.hp_delta or 0) + applied_hp_delta
                    if char.current_hp == 0:
                        set_character_downed(char)

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

                # Narrator może nadal rozliczyć fabularną utratę przedmiotu, ale nie
                # tworzy łupu ani rezultatów craftingu. Te zmiany zapisuje mechanika.
                items_to_consume = {}
                for removal_name in conseq.removed_item_names:
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
