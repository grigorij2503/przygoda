"""Domain routers registered by :mod:`app.main`."""

from app.api.routers import (
    actions,
    admin,
    auth,
    characters,
    chat,
    images,
    push,
    sessions,
    turns,
    ui,
)

__all__ = [
    "actions",
    "admin",
    "auth",
    "characters",
    "chat",
    "images",
    "push",
    "sessions",
    "turns",
    "ui",
]
