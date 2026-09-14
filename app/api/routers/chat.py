from fastapi import APIRouter

from app.services import chat_service


router = APIRouter()
router.add_api_websocket_route(
    "/ws/{session_id}/{character_id}",
    chat_service.websocket_endpoint,
)
