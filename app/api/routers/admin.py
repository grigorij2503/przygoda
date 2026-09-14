from fastapi import APIRouter

from app.services import admin_service


router = APIRouter()
router.add_api_route(
    "/api/admin/status",
    admin_service.get_admin_status,
    methods=["GET"],
)
router.add_api_route(
    "/api/admin/unlock",
    admin_service.unlock_admin_tools,
    methods=["POST"],
)
router.add_api_route(
    "/api/admin/lock",
    admin_service.lock_admin_tools,
    methods=["POST"],
)
router.add_api_route(
    "/api/admin/characters/{character_id}/stats",
    admin_service.update_character_base_stats,
    methods=["PUT"],
)
