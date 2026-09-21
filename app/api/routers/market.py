from fastapi import APIRouter

from app.services import market_service


router = APIRouter()
router.add_api_route("/api/market/transaction", market_service.transact, methods=["POST"])
router.add_api_route("/api/market/interact", market_service.interact, methods=["POST"])
router.add_api_route("/api/market/open", market_service.open_post_manually, methods=["POST"])
