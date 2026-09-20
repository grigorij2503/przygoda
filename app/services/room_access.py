"""Short-lived signed room access for inventory transfers."""

import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, status
from starlette.requests import Request

from app.config import settings


ROOM_SESSION_COOKIE = "ttrpg_room_session"
ROOM_SESSION_TTL_SECONDS = 24 * 60 * 60


def create_room_session_token(expires_at: int) -> str:
    payload = f"room:{expires_at}"
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"{expires_at}.{signature}"


def require_room(request: Request) -> None:
    token = request.cookies.get(ROOM_SESSION_COOKIE, "")
    try:
        expires_raw, supplied_signature = token.split(".", 1)
        expires_at = int(expires_raw)
    except (TypeError, ValueError):
        expires_at = 0
        supplied_signature = ""
    expected_signature = create_room_session_token(expires_at).split(".", 1)[1]
    if expires_at <= int(time.time()) or not secrets.compare_digest(
        supplied_signature, expected_signature
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zaloguj się ponownie do pokoju, aby przekazać przedmiot.",
        )
