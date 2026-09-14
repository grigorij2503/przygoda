from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.gemini_service import generate_scene_image_ai
from app.models import GameSession, Turn
from app.schemas import GenerateImageRequest
from app.services.runtime import image_generation_day_bounds
from app.websocket_manager import ws_manager


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

    reservation_time = datetime.now(timezone.utc)
    image_day_start, next_image_day_start = image_generation_day_bounds(reservation_time)
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
        next_available = next_image_day_start
        retry_after = max(
            1,
            int((next_available - reservation_time).total_seconds()) + 1,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": "W tej kampanii można wygenerować tylko jedną ilustrację dziennie.",
                "next_available_at": next_available.isoformat(),
            },
            headers={"Retry-After": str(retry_after)},
        )

    prompt = turn.image_prompt or "Dark fantasy painting of dungeon adventurers"
    turn.is_generating_image = True
    await db.commit()
    reserved_until = next_image_day_start

    # Powiadom o rozpoczęciu generowania obrazu
    await ws_manager.broadcast_to_session(turn.session_id, {
        "type": "IMAGE_GENERATING",
        "turn_id": turn.id,
        "next_available_at": reserved_until.isoformat(),
    })

    # Wygeneruj obraz asynchronicznie
    try:
        image_url = await generate_scene_image_ai(prompt, turn.id)
        turn.image_url = image_url
        turn.is_generating_image = False
        await db.commit()
        next_available = next_image_day_start

        # Powiadom graczy, że obraz jest gotowy
        await ws_manager.broadcast_to_session(turn.session_id, {
            "type": "IMAGE_READY",
            "turn_id": turn.id,
            "image_url": image_url,
            "next_available_at": next_available.isoformat(),
        })
        return {
            "success": True,
            "image_url": image_url,
            "next_available_at": next_available.isoformat(),
        }
    except Exception as e:
        turn.is_generating_image = False
        await db.execute(
            update(GameSession)
            .where(
                GameSession.id == turn.session_id,
                GameSession.last_image_generated_at == reservation_time,
            )
            .values(last_image_generated_at=None)
        )
        await db.commit()
        await ws_manager.broadcast_to_session(turn.session_id, {
            "type": "IMAGE_GENERATION_FAILED",
            "turn_id": turn.id,
        })
        raise HTTPException(status_code=500, detail=f"Błąd generowania obrazu: {e}")
