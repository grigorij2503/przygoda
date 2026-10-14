"""Public catalog of validated campaign worlds."""

from fastapi import APIRouter

from app.services.world_service import get_world_catalog
from app.worlds.models import WorldCatalogResponse


router = APIRouter(prefix="/api/worlds", tags=["worlds"])


@router.get("", response_model=WorldCatalogResponse)
async def list_worlds() -> WorldCatalogResponse:
    return await get_world_catalog()
