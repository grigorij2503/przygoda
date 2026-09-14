from fastapi import APIRouter

from app.services import character_service


router = APIRouter()
router.add_api_route(
    "/api/characters/{character_id}/toggle-ready",
    character_service.toggle_character_ready,
    methods=["POST"],
)
router.add_api_route(
    "/api/characters",
    character_service.create_character,
    methods=["POST"],
)
router.add_api_route(
    "/api/characters/{char_id}/spend-stat-point",
    character_service.spend_stat_point,
    methods=["POST"],
)
router.add_api_route(
    "/api/characters/{char_id}",
    character_service.delete_character,
    methods=["DELETE"],
)
router.add_api_route(
    "/api/characters/{char_id}/personal-note",
    character_service.get_personal_note,
    methods=["GET"],
)
router.add_api_route(
    "/api/characters/{char_id}/personal-note",
    character_service.update_personal_note,
    methods=["PUT"],
)
router.add_api_route(
    "/api/characters/{char_id}/inventory/{item_id}/toggle-equip",
    character_service.toggle_equip_item,
    methods=["POST"],
)
router.add_api_route(
    "/api/characters/{char_id}/inventory/{item_id}/use",
    character_service.use_consumable_item,
    methods=["POST"],
)
