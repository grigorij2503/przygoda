from fastapi import HTTPException, status

from app.config import settings
from app.schemas import VerifyPasswordRequest


async def verify_password(payload: VerifyPasswordRequest):
    if payload.password == settings.ROOM_PASSWORD:
        return {"success": True, "message": "Autoryzacja pomyślna"}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowe hasło do pokoju gry")
