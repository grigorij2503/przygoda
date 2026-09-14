"""FastAPI application composition.

Domain behavior lives in ``app.services`` and public endpoints are registered by
``app.api.routers``. Selected helpers remain re-exported for backwards-compatible
imports used by the test suite and integrations.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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
    worlds,
)
from app.config import UPLOADS_DIR
from app.services.runtime import BASE_DIR, lifespan, validate_action_item_claim
from app.services.turn_service import resolve_turn_background


app = FastAPI(
    title="Gemini TTRPG Master",
    description="Wieloosobowy turowy RPG prowadzony przez Gemini AI z deterministycznymi rzutami kością",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")

for router in (
    ui.router,
    auth.router,
    push.router,
    admin.router,
    sessions.router,
    characters.router,
    turns.router,
    actions.router,
    images.router,
    chat.router,
    worlds.router,
):
    app.include_router(router)


__all__ = ["app", "resolve_turn_background", "validate_action_item_claim"]
