"""Read stored tactical hints for the current character and turn; never call AI."""

from fastapi import Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Character, GameSession, Turn
from app.schemas import TacticalHintsResponse
from app.services.room_access import require_room
from app.tactical_hints import get_saved_tactical_hints


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
    actions, contextual = get_saved_tactical_hints(session, turn, character, list(session.characters))
    return TacticalHintsResponse(
        character_id=character_id,
        turn_id=turn_id,
        suggested_actions=actions,
        contextual=contextual,
    )
