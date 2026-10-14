from fastapi import APIRouter

from app.services import auth_service


router = APIRouter()
router.add_api_route(
    "/api/verify-password",
    auth_service.verify_password,
    methods=["POST"],
)
router.add_api_route(
    "/api/room-access",
    auth_service.room_access_status,
    methods=["GET"],
)
router.add_api_route(
    "/api/rooms",
    auth_service.create_room,
    methods=["POST"],
)
router.add_api_route(
    "/api/logout",
    auth_service.logout_room,
    methods=["POST"],
)
