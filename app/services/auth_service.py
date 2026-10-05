import time
import secrets

from fastapi import Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.config import settings
from app.database import get_db
from app.models import GameSession, Turn
from app.schemas import CreateRoomRequest, VerifyPasswordRequest
from app.services.campaign_goal_service import reset_campaign_goal
from app.services.room_access import (
    ROOM_SESSION_COOKIE,
    ROOM_SESSION_TTL_SECONDS,
    create_room_session_token,
    hash_room_password,
    require_room,
    verify_room_password,
)
from app.worlds.registry import (
    WORLD_PACK_REGISTRY,
    WorldPackNotFoundError,
    get_default_world_pack,
)


ROOM_CREATION_MAX_ATTEMPTS = 5
ROOM_CREATION_WINDOW_SECONDS = 5 * 60
room_creation_attempts: dict[str, list[float]] = {}


def _set_room_access_cookie(
    response: Response,
    request: Request,
    room_code: str,
) -> None:
    response.set_cookie(
        key=ROOM_SESSION_COOKIE,
        value=create_room_session_token(
            int(time.time()) + ROOM_SESSION_TTL_SECONDS,
            room_code,
        ),
        max_age=ROOM_SESSION_TTL_SECONDS,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/",
    )


async def verify_password(
    payload: VerifyPasswordRequest,
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    session = (
        await db.execute(
            select(GameSession).where(GameSession.room_code == payload.room_code)
        )
    ).scalar_one_or_none()
    if not session or not verify_room_password(payload.password, session.room_password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowy kod pokoju lub hasło",
        )

    # Pierwsze poprawne logowanie przenosi starszą sesję z globalnego hasła
    # na niezależny skrót bez zmiany kampanii ani jej relacji.
    if not session.room_password_hash:
        session.room_password_hash = hash_room_password(payload.password)
        await db.commit()

    _set_room_access_cookie(response, request, session.room_code)
    return {
        "success": True,
        "message": "Autoryzacja pomyślna",
        "room_code": session.room_code,
        "title": session.title,
    }


async def room_access_status(room_code: str, request: Request, response: Response):
    normalized_room_code = room_code.strip().lower()
    require_room(request, normalized_room_code)
    _set_room_access_cookie(response, request, normalized_room_code)
    return {"authenticated": True, "room_code": normalized_room_code}


async def create_room(
    payload: CreateRoomRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if not settings.GM_PIN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PIN Mistrza Gry nie jest skonfigurowany",
        )
    client_key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    recent_attempts = [
        attempted_at
        for attempted_at in room_creation_attempts.get(client_key, [])
        if now - attempted_at < ROOM_CREATION_WINDOW_SECONDS
    ]
    room_creation_attempts[client_key] = recent_attempts
    if len(recent_attempts) >= ROOM_CREATION_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Zbyt wiele nieudanych prób. Spróbuj ponownie za kilka minut.",
            headers={"Retry-After": str(ROOM_CREATION_WINDOW_SECONDS)},
        )
    if not secrets.compare_digest(payload.gm_pin, settings.GM_PIN):
        room_creation_attempts[client_key].append(now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nieprawidłowy PIN Mistrza Gry",
        )
    room_creation_attempts.pop(client_key, None)
    existing = (
        await db.execute(
            select(GameSession.id).where(GameSession.room_code == payload.room_code)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pokój o tym kodzie już istnieje",
        )

    try:
        world = (
            WORLD_PACK_REGISTRY.get(payload.world_pack_id, payload.world_pack_version)
            if payload.world_pack_id is not None
            else get_default_world_pack()
        )
    except WorldPackNotFoundError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    profile = world.narrative_profile
    scenario_type = payload.scenario_type.strip() or profile.scenario_options[0]
    if scenario_type not in profile.scenario_options:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wybrany scenariusz nie należy do wskazanego świata",
        )
    setting_theme = payload.tone.strip() or profile.setting_theme
    session = GameSession(
        room_code=payload.room_code,
        room_password_hash=hash_room_password(payload.password),
        world_pack_id=world.id,
        world_pack_version=world.version,
        scenario_type=scenario_type,
        title=(
            payload.title.strip()
            or profile.lobby_title_template.format(scenario_type=scenario_type)
        ),
        setting_theme=setting_theme,
        campaign_intro="",
        current_turn_number=1,
        status="lobby",
    )
    reset_campaign_goal(session, current_clue=profile.lobby_prompt)
    db.add(session)
    await db.flush()
    db.add(Turn(
        session_id=session.id,
        turn_number=1,
        status="waiting_for_actions",
        gm_narration="",
        next_turn_prompt=profile.lobby_prompt,
        suggested_actions=list(profile.suggested_actions),
        image_prompt=profile.initial_image_prompt,
    ))
    await db.commit()
    return {
        "success": True,
        "room_code": session.room_code,
        "title": session.title,
    }


async def logout_room(response: Response):
    response.delete_cookie(key=ROOM_SESSION_COOKIE, path="/", samesite="strict")
    return {"success": True}
