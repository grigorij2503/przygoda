from fastapi import APIRouter

from app.services import push_subscription_service


router = APIRouter()
router.add_api_route(
    "/api/push/config",
    push_subscription_service.get_push_config,
    methods=["GET"],
)
router.add_api_route(
    "/api/push/subscriptions",
    push_subscription_service.save_push_subscription,
    methods=["POST"],
)
router.add_api_route(
    "/api/push/subscriptions",
    push_subscription_service.delete_push_subscription,
    methods=["DELETE"],
)
