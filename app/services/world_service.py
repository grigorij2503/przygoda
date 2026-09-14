"""Read-only world catalog service."""

from app.worlds.models import WorldCatalogResponse
from app.worlds.registry import WORLD_PACK_REGISTRY


async def get_world_catalog() -> WorldCatalogResponse:
    return WORLD_PACK_REGISTRY.catalog()
