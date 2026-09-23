import secrets
import time

from fastapi import Depends, HTTPException, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.config import settings
from app.database import get_db
from app.models import (
    Character,
    GameSession,
    InventoryItem,
    PlayerAction,
    ProxyActionDecision,
    ProxyActionVote,
    Turn,
)
from app.schemas import (
    AdminAdjustCoinsRequest,
    AdminGrantWearableRequest,
    AdminSetParticipationRequest,
    AdminUpdateCharacterStatsRequest,
    VerifyGmPinRequest,
)
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
from app.services.room_access import require_room


async def get_admin_status(request: Request):
    require_room(request)
    return {"authenticated": is_gm_authenticated(request)}


async def unlock_admin_tools(payload: VerifyGmPinRequest, response: Response, request: Request):
    require_room(request)
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
    require_room(request, payload.room_code)
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
    require_room(request, payload.room_code)
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


async def set_character_participation(
    character_id: int,
    payload: AdminSetParticipationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    require_room(request, payload.room_code)
    require_gm(request)
    stmt = (
        select(Character, GameSession)
        .join(GameSession)
        .where(
            Character.id == character_id,
            GameSession.room_code == payload.room_code,
        )
        .with_for_update()
    )
    row = (await db.execute(stmt)).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Postać nie istnieje w tym pokoju")
    character, session = row
    if session.is_turn_resolving:
        raise HTTPException(
            status_code=409,
            detail="Nie można zmienić udziału postaci podczas rozstrzygania tury",
        )
    if character.participation_status == payload.participation_status:
        return {
            "success": True,
            "character_id": character.id,
            "character_name": character.name,
            "participation_status": character.participation_status,
            "break_started_turn": character.break_started_turn,
        }

    if payload.participation_status == "on_break":
        current_turn = (
            await db.execute(
                select(Turn).where(
                    Turn.session_id == session.id,
                    Turn.turn_number == session.current_turn_number,
                )
            )
        ).scalar_one_or_none()
        if current_turn and current_turn.mechanics_resolved_at is not None:
            raise HTTPException(
                status_code=409,
                detail="Mechanika bieżącej tury została już rozliczona; najpierw dokończ narrację",
            )
        if current_turn is not None:
            decision_ids = list((await db.execute(
                select(ProxyActionDecision.id).where(
                    ProxyActionDecision.turn_id == current_turn.id,
                    ProxyActionDecision.target_character_id == character.id,
                )
            )).scalars())
            if decision_ids:
                await db.execute(
                    delete(ProxyActionVote).where(
                        ProxyActionVote.decision_id.in_(decision_ids)
                    )
                )
                await db.execute(
                    delete(ProxyActionDecision).where(
                        ProxyActionDecision.id.in_(decision_ids)
                    )
                )
            await db.execute(
                delete(PlayerAction).where(
                    PlayerAction.turn_id == current_turn.id,
                    PlayerAction.character_id == character.id,
                )
            )
        character.participation_status = "on_break"
        character.break_started_turn = session.current_turn_number
        character.is_ready = False
        if session.pending_naming_character_id == character.id:
            session.pending_naming_category = None
            session.pending_naming_prompt = None
            session.pending_naming_character_id = None
            session.pending_naming_character_name = None
            session.pending_naming_turn_number = None
            session.pending_naming_map_node_id = None
            session.pending_naming_question = None
    else:
        character.participation_status = "active"
        character.break_started_turn = None
        character.is_ready = False

    await db.commit()
    await ws_manager.broadcast_to_session(session.id, {
        "type": "CHARACTER_PARTICIPATION_UPDATED",
        "character_id": character.id,
        "character_name": character.name,
        "participation_status": character.participation_status,
        "break_started_turn": character.break_started_turn,
    })
    return {
        "success": True,
        "character_id": character.id,
        "character_name": character.name,
        "participation_status": character.participation_status,
        "break_started_turn": character.break_started_turn,
    }


async def grant_wearable_item(
    character_id: int,
    payload: AdminGrantWearableRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    require_room(request, payload.room_code)
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
