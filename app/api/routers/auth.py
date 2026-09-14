from fastapi import APIRouter

from app.services import auth_service


router = APIRouter()
router.add_api_route(
    "/api/verify-password",
    auth_service.verify_password,
    methods=["POST"],
)
