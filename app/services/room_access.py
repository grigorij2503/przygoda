"""Signed, room-bound access and password helpers."""

import base64
import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, status
from starlette.requests import HTTPConnection, Request

from app.config import settings


ROOM_SESSION_COOKIE = "ttrpg_room_session"
# Keep trusted devices signed in without storing the room password in the browser.
# The cookie is renewed after every successful room-access check.
ROOM_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
PASSWORD_ITERATIONS = 310_000


def hash_room_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
    )


def verify_room_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return secrets.compare_digest(password, settings.ROOM_PASSWORD)
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_raw + "=" * (-len(salt_raw) % 4))
        expected = base64.urlsafe_b64decode(digest_raw + "=" * (-len(digest_raw) % 4))
        supplied = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, int(iterations_raw)
        )
    except (TypeError, ValueError):
        return False
    return secrets.compare_digest(supplied, expected)


def _encode_room_code(room_code: str) -> str:
    return base64.urlsafe_b64encode(room_code.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_room_code(encoded: str) -> str:
    return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")


def create_room_session_token(expires_at: int, room_code: str = "*") -> str:
    encoded_room = _encode_room_code(room_code)
    payload = f"v1:{encoded_room}:{expires_at}"
    signature = hmac.new(
        settings.SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"v1.{encoded_room}.{expires_at}.{signature}"


def get_authorized_room(connection: HTTPConnection) -> str | None:
    token = connection.cookies.get(ROOM_SESSION_COOKIE, "")
    try:
        version, encoded_room, expires_raw, supplied_signature = token.split(".", 3)
        if version != "v1":
            raise ValueError
        expires_at = int(expires_raw)
        room_code = _decode_room_code(encoded_room)
        payload = f"v1:{encoded_room}:{expires_at}"
        expected_signature = hmac.new(
            settings.SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
    except (TypeError, ValueError, UnicodeDecodeError):
        return None
    if expires_at <= int(time.time()) or not secrets.compare_digest(
        supplied_signature, expected_signature
    ):
        return None
    return room_code


def require_room(connection: Request | HTTPConnection, room_code: str | None = None) -> str:
    authorized_room = get_authorized_room(connection)
    if authorized_room is None or (
        room_code is not None
        and authorized_room != "*"
        and not secrets.compare_digest(authorized_room, room_code)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zaloguj się do właściwego pokoju, aby wykonać tę operację.",
        )
    return authorized_room
