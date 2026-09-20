import time

from fastapi import HTTPException, Response, status
from starlette.requests import Request

from app.config import settings
from app.schemas import VerifyPasswordRequest
from app.services.room_access import (
    ROOM_SESSION_COOKIE,
    ROOM_SESSION_TTL_SECONDS,
    create_room_session_token,
)


async def verify_password(payload: VerifyPasswordRequest, response: Response, request: Request):
    if payload.password == settings.ROOM_PASSWORD:
        response.set_cookie(
            key=ROOM_SESSION_COOKIE,
            value=create_room_session_token(int(time.time()) + ROOM_SESSION_TTL_SECONDS),
            max_age=ROOM_SESSION_TTL_SECONDS,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="strict",
            path="/",
        )
        return {"success": True, "message": "Autoryzacja pomyślna"}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowe hasło do pokoju gry")


async def logout_room(response: Response):
    response.delete_cookie(key=ROOM_SESSION_COOKIE, path="/", samesite="strict")
    return {"success": True}
