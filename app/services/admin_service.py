import secrets
import time

from fastapi import Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.config import settings
from app.database import get_db
from app.models import Character, GameSession, InventoryItem
from app.schemas import AdminAdjustCoinsRequest, AdminGrantWearableRequest, AdminUpdateCharacterStatsRequest, VerifyGmPinRequest
from app.services.runtime import (
    GM_SESSION_COOKIE,
    GM_SESSION_TTL_SECONDS,
    GM_UNLOCK_MAX_ATTEMPTS,
    GM_UNLOCK_WINDOW_SECONDS,
    create_gm_session_token,
    gm_unlock_attempts,
    is_gm_authenticated,
    logger,
    require_gm,
)
from app.websocket_manager import ws_manager


async def get_admin_status(request: Request):
    return {"authenticated": is_gm_authenticated(request)}


async def unlock_admin_tools(payload: VerifyGmPinRequest, response: Response, request: Request):
    if not settings.GM_PIN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PIN Mistrza Gry nie jest skonfigurowany. Ustaw GM_PIN w pliku .env.",
        )

    client_key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    recent_attempts = [
        attempted_at
        for attempted_at in gm_unlock_attempts.get(client_key, [])
        if now - attempted_at < GM_UNLOCK_WINDOW_SECONDS
    ]
    gm_unlock_attempts[client_key] = recent_attempts
    if len(recent_attempts) >= GM_UNLOCK_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Zbyt wiele nieudanych prób. Spróbuj ponownie za kilka minut.",
            headers={"Retry-After": str(GM_UNLOCK_WINDOW_SECONDS)},
        )
    if not secrets.compare_digest(payload.pin, settings.GM_PIN):
        gm_unlock_attempts[client_key].append(now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowy PIN Mistrza Gry",
        )

    gm_unlock_attempts.pop(client_key, None)
    expires_at = int(time.time()) + GM_SESSION_TTL_SECONDS
    response.set_cookie(
        key=GM_SESSION_COOKIE,
        value=create_gm_session_token(expires_at),
        max_age=GM_SESSION_TTL_SECONDS,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return {"success": True, "expires_in": GM_SESSION_TTL_SECONDS}


async def lock_admin_tools(response: Response):
    response.delete_cookie(key=GM_SESSION_COOKIE, path="/", samesite="strict")
    return {"success": True}


async def update_character_base_stats(
    character_id: int,
    payload: AdminUpdateCharacterStatsRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    require_gm(request)
    stmt = (
        select(Character)
        .join(GameSession)
        .where(
            Character.id == character_id,
            GameSession.room_code == payload.room_code,
        )
    )
    character = (await db.execute(stmt)).scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Postać nie istnieje w tym pokoju")

    previous_stats = {
        "strength": character.strength,
        "agility": character.agility,
        "intellect": character.intellect,
        "charisma": character.charisma,
        "perception": character.perception,
    }
    updated_stats = {
        "strength": payload.strength,
        "agility": payload.agility,
        "intellect": payload.intellect,
        "charisma": payload.charisma,
        "perception": (
            payload.perception if payload.perception is not None else character.perception
        ),
    }
    for stat_name, stat_value in updated_stats.items():
        setattr(character, stat_name, stat_value)

    await db.commit()
    logger.warning(
        "MG zmienił bazowe atrybuty postaci %s (ID %s): %s -> %s",
        character.name,
        character.id,
        previous_stats,
        updated_stats,
    )
    await ws_manager.broadcast_to_session(character.session_id, {
        "type": "CHARACTER_STATS_UPDATED",
        "character_id": character.id,
        "character_name": character.name,
        "stats": updated_stats,
    })
    return {
        "success": True,
        "character_id": character.id,
        "character_name": character.name,
        "stats": updated_stats,
        "unspent_stat_points": character.unspent_stat_points or 0,
    }


async def adjust_character_coins(
    character_id: int,
    payload: AdminAdjustCoinsRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    require_gm(request)
    if payload.amount == 0:
        raise HTTPException(status_code=400, detail="Podaj zmianę różną od zera")
    character = (
        await db.execute(
            select(Character)
            .join(GameSession)
            .where(
                Character.id == character_id,
                GameSession.room_code == payload.room_code,
            )
        )
    ).scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Postać nie istnieje w tym pokoju")
    result = await db.execute(
        update(Character)
        .where(Character.id == character.id, Character.coins + payload.amount >= 0)
        .values(coins=Character.coins + payload.amount)
    )
    if result.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Saldo nie może być ujemne")
    await db.commit()
    await db.refresh(character)
    await ws_manager.broadcast_to_session(character.session_id, {
        "type": "CHARACTER_COINS_UPDATED",
        "character_id": character.id,
        "character_name": character.name,
        "coins": character.coins,
    })
    return {
        "success": True,
        "character_id": character.id,
        "character_name": character.name,
        "coins": character.coins,
    }


async def grant_wearable_item(
    character_id: int,
    payload: AdminGrantWearableRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    require_gm(request)
    character = (
        await db.execute(
            select(Character)
            .join(GameSession)
            .where(
                Character.id == character_id,
                GameSession.room_code == payload.room_code,
            )
        )
    ).scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail="Postać nie istnieje w tym pokoju")
    if payload.target_stat == "none" and payload.stat_bonus:
        raise HTTPException(status_code=400, detail="Wybierz cechę dla premii")
    item_name = payload.name.strip()
    if len(item_name) < 2:
        raise HTTPException(status_code=400, detail="Nazwa przedmiotu jest za krótka")
    item = InventoryItem(
        character_id=character.id,
        name=item_name,
        description=payload.description.strip(),
        item_type=payload.item_type,
        target_stat=payload.target_stat,
        stat_bonus=payload.stat_bonus,
        damage_power=0,
        hands_required=1,
        is_equipped=False,
        quantity=1,
    )
    db.add(item)
    await db.commit()
    await ws_manager.broadcast_to_session(character.session_id, {
        "type": "WEARABLE_GRANTED",
        "character_id": character.id,
        "character_name": character.name,
        "item_name": item.name,
    })
    return {"success": True, "character_name": character.name, "item_name": item.name}
