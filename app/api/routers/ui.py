from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.services import ui_service


router = APIRouter()
router.add_api_route(
    "/manifest.json",
    ui_service.serve_manifest,
    methods=["GET"],
    include_in_schema=False,
)
router.add_api_route(
    "/sw.js",
    ui_service.serve_service_worker,
    methods=["GET"],
    include_in_schema=False,
)
router.add_api_route(
    "/favicon.ico",
    ui_service.serve_favicon,
    methods=["GET"],
    include_in_schema=False,
)
router.add_api_route(
    "/",
    ui_service.serve_ui,
    methods=["GET"],
    response_class=HTMLResponse,
)
