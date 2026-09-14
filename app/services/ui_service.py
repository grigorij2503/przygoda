from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app.services.runtime import BASE_DIR


templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


async def serve_manifest():
    manifest_path = BASE_DIR / "app" / "static" / "manifest.json"
    return FileResponse(
        manifest_path,
        media_type="application/manifest+json",
        headers={"Cache-Control": "public, max-age=3600"}
    )

async def serve_service_worker():
    sw_path = BASE_DIR / "app" / "static" / "sw.js"
    return FileResponse(
        sw_path,
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Service-Worker-Allowed": "/"
        }
    )

async def serve_favicon():
    fav_path = BASE_DIR / "app" / "static" / "icons" / "favicon.png"
    return FileResponse(fav_path, media_type="image/png")

async def serve_ui(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")
