from datetime import datetime, timezone
import logging

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.gemini_service import generate_scene_image_ai
from app.models import GameSession, Turn
from app.schemas import GenerateImageRequest
from app.services.runtime import image_generation_day_bounds
from app.services.world_service import get_session_world_pack
from app.services.room_access import require_room
from app.websocket_manager import ws_manager


logger = logging.getLogger(__name__)


async def _release_image_reservation(
    db: AsyncSession,
    *,
    session_id: int,
    turn_id: int,
    reservation_time: datetime,
) -> None:
    """Best-effort cleanup after an image request fails."""
    try:
        await db.rollback()
        await db.execute(
            update(Turn)
            .where(Turn.id == turn_id, Turn.image_url.is_(None))
            .values(is_generating_image=False)
        )
        await db.execute(
            update(GameSession)
            .where(
                GameSession.id == session_id,
                GameSession.last_image_generated_at == reservation_time,
            )
            .values(last_image_generated_at=None)
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception(
            "Nie udało się zwolnić rezerwacji ilustracji dla tury %s",
            turn_id,
        )


async def generate_turn_image(
    payload: GenerateImageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    reservation_time: datetime | None = None
    reserved_session_id: int | None = None
    reserved_turn_id: int | None = None
    try:
        stmt = select(Turn).where(Turn.id == payload.turn_id)
        res = await db.execute(stmt)
        turn = res.scalar_one_or_none()
        if not turn:
            raise HTTPException(status_code=404, detail="Tura nie istnieje")
        session = (
            await db.execute(select(GameSession).where(GameSession.id == turn.session_id))
        ).scalar_one()
        require_room(request, session.room_code)

        if turn.image_url:
            return {"success": True, "image_url": turn.image_url}

        if turn.is_generating_image:
            return {
                "success": True,
                "pending": True,
                "message": "Generowanie już trwa",
            }

        world_pack = get_session_world_pack(session)
        narrative_profile = world_pack.narrative_profile

        reservation_time = datetime.now(timezone.utc)
        image_day_start, next_image_day_start = image_generation_day_bounds(
            reservation_time
        )
        reservation = await db.execute(
            update(GameSession)
            .where(
                GameSession.id == turn.session_id,
                (
                    GameSession.last_image_generated_at.is_(None)
                    | (GameSession.last_image_generated_at < image_day_start)
                ),
            )
            .values(last_image_generated_at=reservation_time)
        )
        if reservation.rowcount != 1:
            retry_after = max(
                1,
                int((next_image_day_start - reservation_time).total_seconds()) + 1,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": "W tej kampanii można wygenerować tylko jedną ilustrację dziennie.",
                    "next_available_at": next_image_day_start.isoformat(),
                },
                headers={"Retry-After": str(retry_after)},
            )

        prompt = (
            f"{narrative_profile.image_art_direction}\n"
            f"{turn.image_prompt or narrative_profile.initial_image_prompt}"
        )
        turn.is_generating_image = True
        await db.commit()
        reserved_session_id = turn.session_id
        reserved_turn_id = turn.id

        await ws_manager.broadcast_to_session(turn.session_id, {
            "type": "IMAGE_GENERATING",
            "turn_id": turn.id,
            "next_available_at": next_image_day_start.isoformat(),
        })

        image_url = await generate_scene_image_ai(prompt, turn.id, world_pack=world_pack)
        turn.image_url = image_url
        turn.is_generating_image = False
        await db.commit()

        await ws_manager.broadcast_to_session(turn.session_id, {
            "type": "IMAGE_READY",
            "turn_id": turn.id,
            "image_url": image_url,
            "next_available_at": next_image_day_start.isoformat(),
        })
        return {
            "success": True,
            "image_url": image_url,
            "next_available_at": next_image_day_start.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as error:
        if (
            reservation_time is not None
            and reserved_session_id is not None
            and reserved_turn_id is not None
        ):
            await _release_image_reservation(
                db,
                session_id=reserved_session_id,
                turn_id=reserved_turn_id,
                reservation_time=reservation_time,
            )
            try:
                await ws_manager.broadcast_to_session(reserved_session_id, {
                    "type": "IMAGE_GENERATION_FAILED",
                    "turn_id": reserved_turn_id,
                })
            except Exception:
                logger.exception(
                    "Nie udało się wysłać informacji o błędzie ilustracji dla tury %s",
                    reserved_turn_id,
                )
        logger.exception("Generowanie ilustracji dla tury %s nie powiodło się", payload.turn_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Nie udało się wygenerować ilustracji. "
                "Limit nie został wykorzystany; spróbuj ponownie."
            ),
        ) from error
