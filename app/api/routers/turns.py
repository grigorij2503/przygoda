from fastapi import APIRouter

from app.services import proxy_service, turn_service


router = APIRouter()
router.add_api_route(
    "/api/session/retry-turn",
    turn_service.retry_turn,
    methods=["POST"],
)
router.add_api_route(
    "/api/session/resolve-turn",
    turn_service.resolve_turn_endpoint,
    methods=["POST"],
)
router.add_api_route(
    "/api/proxy-actions/{target_character_id}/votes",
    proxy_service.vote_for_proxy_action,
    methods=["POST"],
)
