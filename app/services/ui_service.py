from fastapi import Depends
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.database import get_db
from app.models import GameSession
from app.services.runtime import BASE_DIR
from app.worlds.registry import WORLD_PACK_REGISTRY


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

async def serve_ui(request: Request, db: AsyncSession = Depends(get_db)):
    # Match the room selected by the current Alpine shell before it runs.
    room_code = "kampania-1"
    session = (
        await db.execute(select(GameSession).where(GameSession.room_code == room_code))
    ).scalar_one_or_none()
    pack = WORLD_PACK_REGISTRY.get(
        session.world_pack_id if session else None,
        session.world_pack_version if session else None,
    )
    theme = pack.theme
    token_values = {token.id: token.value for token in theme.tokens}
    theme_style = " ".join(
        f"--ui-{token.id.replace('_', '-')}: {token.value};"
        for token in theme.tokens
    )
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "theme": theme,
            "theme_style": theme_style,
            "theme_background": token_values["background"],
            "world_key": pack.key,
        },
    )
