"""Read-only, room-gated tactical hints for one character in the current scene."""

import asyncio
import hashlib
import html
import json
import time
from collections import OrderedDict

from fastapi import Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.combat import status_list
from app.database import get_db
from app.gemini_service import generate_tactical_hints_ai
from app.models import Character, GameSession, Turn
from app.schemas import TacticalHintsResponse
from app.services.room_access import require_room
from app.services.world_service import get_session_world_pack
from app.worlds.models import WorldPack


HINT_CACHE_LIMIT = 256
HINT_CACHE_TTL_SECONDS = 900
_hint_cache: OrderedDict[str, tuple[float, TacticalHintsResponse]] = OrderedDict()
_pending_hints: dict[str, asyncio.Task[TacticalHintsResponse]] = {}


def _public_scene_text(value: str | None) -> str:
    # Legacy prompts may contain shared suggestions. They are not scene facts.
    return html.unescape(value or "").split("Sugerowane ścieżki działania:", 1)[0].strip()


def _character_context(character: Character) -> dict:
    return {
        "character_id": character.id,
        "name": character.name,
        "character_class": character.character_class,
        "narrative_form": character.narrative_form or "neutral",
        "hp": character.current_hp,
        "max_hp": character.max_hp,
        "can_act": bool(character.is_alive and (character.death_state or "alive") == "alive"),
        "death_state": character.death_state or "alive",
        "status_effects": status_list(character.status_effects),
    }


async def _generate_cached_hints(
    key: str,
    context: dict,
    world_pack: WorldPack,
    character_id: int,
    turn_id: int,
) -> TacticalHintsResponse:
    try:
        actions, contextual = await generate_tactical_hints_ai(context, world_pack)
        result = TacticalHintsResponse(
            character_id=character_id,
            turn_id=turn_id,
            suggested_actions=actions,
            contextual=contextual,
        )
        ttl = HINT_CACHE_TTL_SECONDS if contextual else 60
        _hint_cache[key] = (time.monotonic() + ttl, result)
        _hint_cache.move_to_end(key)
        while len(_hint_cache) > HINT_CACHE_LIMIT:
            _hint_cache.popitem(last=False)
        return result
    finally:
        _pending_hints.pop(key, None)


async def get_tactical_hints(
    character_id: int,
    request: Request,
    response: Response,
    turn_id: int = Query(ge=1),
    db: AsyncSession = Depends(get_db),
) -> TacticalHintsResponse:
    require_room(request)
    response.headers["Cache-Control"] = "no-store"
    character = (await db.execute(
        select(Character)
        .where(Character.id == character_id)
        .options(
            selectinload(Character.inventory),
            selectinload(Character.session).selectinload(GameSession.characters),
        )
    )).scalar_one_or_none()
    if character is None:
        raise HTTPException(status_code=404, detail="Postać nie została znaleziona")
    session = character.session
    require_room(request, session.room_code)
    if session.status != "in_progress" or session.is_turn_resolving:
        raise HTTPException(status_code=409, detail="Podpowiedzi są dostępne w otwartej turze kampanii")
    if (
        not character.is_participating
        or not character.is_alive
        or (character.death_state or "alive") != "alive"
    ):
        raise HTTPException(status_code=409, detail="Ta postać nie może teraz deklarować akcji")

    turn = (await db.execute(
        select(Turn).where(
            Turn.id == turn_id,
            Turn.session_id == session.id,
            Turn.turn_number == session.current_turn_number,
        )
    )).scalar_one_or_none()
    if turn is None or turn.status != "waiting_for_actions":
        raise HTTPException(status_code=409, detail="Podpowiedzi dotyczą wyłącznie bieżącej, otwartej tury")

    previous_turn = (await db.execute(
        select(Turn)
        .where(
            Turn.session_id == session.id,
            Turn.turn_number < turn.turn_number,
            Turn.status == "completed",
        )
        .order_by(Turn.turn_number.desc())
        .limit(1)
    )).scalar_one_or_none()
    world_pack = get_session_world_pack(session)
    actor = _character_context(character)
    actor["attributes"] = {
        attribute.id: int(getattr(character, attribute.id, 0) or 0)
        for attribute in world_pack.attributes
    }
    actor["inventory"] = [
        {
            "name": item.name,
            "description": item.description,
            "type": item.item_type,
            "equipped": bool(item.is_equipped),
            "quantity": 1 if item.quantity is None else item.quantity,
        }
        for item in sorted(character.inventory, key=lambda item: item.id)
        if item.quantity is None or item.quantity > 0
    ]
    context = {
        "session_id": session.id,
        "room_code": session.room_code,
        "world_pack": world_pack.key,
        "campaign_title": session.title,
        "setting_theme": session.setting_theme,
        "published_campaign_intro": _public_scene_text(session.campaign_intro),
        "turn_id": turn.id,
        "turn_number": turn.turn_number,
        "previous_published_narration": _public_scene_text(previous_turn.gm_narration) if previous_turn else "",
        "current_published_narration": _public_scene_text(turn.gm_narration),
        "current_challenge": _public_scene_text(turn.next_turn_prompt),
        "active_enemy": (
            {"name": session.active_boss_name, "title": session.active_boss_title, "hp": session.active_boss_hp}
            if session.active_boss_name and (session.active_boss_hp or 0) > 0 else None
        ),
        "selected_character": actor,
        "party": [
            _character_context(member)
            for member in sorted(session.characters, key=lambda member: member.id)
            if member.is_participating and (member.death_state or "alive") != "dead"
        ],
    }
    key = hashlib.sha256(json.dumps(context, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    # All ORM values have been copied; release the read transaction before AI work.
    await db.rollback()

    cached = _hint_cache.get(key)
    if cached and cached[0] > time.monotonic():
        _hint_cache.move_to_end(key)
        return cached[1]
    if key not in _pending_hints:
        _pending_hints[key] = asyncio.create_task(
            _generate_cached_hints(key, context, world_pack, character_id, turn_id)
        )
    return await asyncio.shield(_pending_hints[key])
