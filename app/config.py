import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"
    IMAGEN_MODEL: str = "imagen-3.0-generate-002"
    ROOM_PASSWORD: str = "dragon2026"
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR}/ttrpg_game.db"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    SECRET_KEY: str = "ttrpg-dark-fantasy-secret-key-salt"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
