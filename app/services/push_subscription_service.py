from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.config import settings
from app.database import get_db
from app.models import Character, GameSession, WebPushSubscription
from app.push_service import is_web_push_configured
from app.schemas import DeletePushSubscriptionRequest, SavePushSubscriptionRequest


async def get_push_config():
    configured = is_web_push_configured()
    return {
        "configured": configured,
        "public_key": settings.VAPID_PUBLIC_KEY if configured else "",
    }


async def save_push_subscription(
    payload: SavePushSubscriptionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if payload.password != settings.ROOM_PASSWORD:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowe hasło do pokoju gry")
    if not is_web_push_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Web Push nie jest skonfigurowany")

    endpoint = payload.subscription.endpoint.strip()
    endpoint_url = urlsplit(endpoint)
    if endpoint_url.scheme != "https" or not endpoint_url.netloc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Nieprawidłowy endpoint Web Push")

    game_session = (
        await db.execute(select(GameSession).where(GameSession.room_code == payload.room_code))
    ).scalar_one_or_none()
    if not game_session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesja nie została znaleziona")

    character = (
        await db.execute(
            select(Character).where(
                Character.id == payload.character_id,
                Character.session_id == game_session.id,
            )
        )
    ).scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Postać nie została znaleziona")

    subscription = (
        await db.execute(
            select(WebPushSubscription).where(WebPushSubscription.endpoint == endpoint)
        )
    ).scalar_one_or_none()
    if subscription is None:
        subscription = WebPushSubscription(endpoint=endpoint)
        db.add(subscription)

    subscription.session_id = game_session.id
    subscription.character_id = character.id
    subscription.p256dh = payload.subscription.keys.p256dh
    subscription.auth = payload.subscription.keys.auth
    subscription.user_agent = (request.headers.get("user-agent") or "")[:500]
    subscription.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"success": True}


async def delete_push_subscription(
    payload: DeletePushSubscriptionRequest,
    db: AsyncSession = Depends(get_db),
):
    if payload.password != settings.ROOM_PASSWORD:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowe hasło do pokoju gry")

    result = await db.execute(
        delete(WebPushSubscription).where(
            WebPushSubscription.endpoint == payload.endpoint.strip()
        )
    )
    await db.commit()
    return {"success": True, "deleted": bool(result.rowcount)}
