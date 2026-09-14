from fastapi import APIRouter

from app.schemas import ActionInterpretationResponse
from app.services import turn_service


router = APIRouter()
router.add_api_route(
    "/api/actions/interpret",
    turn_service.interpret_action,
    methods=["POST"],
    response_model=ActionInterpretationResponse,
)
router.add_api_route(
    "/api/actions",
    turn_service.submit_action,
    methods=["POST"],
)
