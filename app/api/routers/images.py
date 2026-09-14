from fastapi import APIRouter

from app.services import image_service


router = APIRouter()
router.add_api_route(
    "/api/generate-image",
    image_service.generate_turn_image,
    methods=["POST"],
)
