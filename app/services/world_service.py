"""Read-only world catalog service."""

from fastapi import HTTPException

from app.models import GameSession
from app.worlds.models import WorldCatalogResponse, WorldPack
from app.worlds.registry import WORLD_PACK_REGISTRY, WorldPackNotFoundError


async def get_world_catalog() -> WorldCatalogResponse:
    return WORLD_PACK_REGISTRY.catalog()


def get_session_world_pack(session: GameSession) -> WorldPack:
    return WORLD_PACK_REGISTRY.get(
        getattr(session, "world_pack_id", None),
        getattr(session, "world_pack_version", None),
    )


def resolve_requested_world_pack(
    session: GameSession,
    world_pack_id: str | None,
    world_pack_version: int | None,
) -> WorldPack:
    current_pack = get_session_world_pack(session)
    if world_pack_id is None and world_pack_version is None:
        return current_pack
    requested_key = f"{world_pack_id}@{world_pack_version}"
    if requested_key != current_pack.key and (
        (getattr(session, "status", "in_progress") or "in_progress") != "lobby"
        or bool(getattr(session, "characters", []))
        or int(getattr(session, "current_turn_number", 1) or 1) > 1
    ):
        raise HTTPException(
            status_code=409,
            detail="Nie można zmienić świata aktywnej kampanii. Utwórz nową pustą kampanię.",
        )
    try:
        return WORLD_PACK_REGISTRY.get(world_pack_id, world_pack_version)
    except WorldPackNotFoundError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
