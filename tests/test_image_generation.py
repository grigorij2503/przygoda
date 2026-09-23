import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.main import app
from app.models import GameSession, Turn
from app.services import image_service


@pytest.mark.asyncio
async def test_image_failure_returns_json_and_releases_daily_limit(
    isolated_dark_fantasy_db,
    monkeypatch,
):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        login = await client.post(
            "/api/verify-password",
            json={
                "room_code": "kampania-1",
                "password": settings.ROOM_PASSWORD,
            },
        )
        assert login.status_code == 200

        async for db in get_db():
            turn = (
                await db.execute(
                    select(Turn)
                    .join(GameSession)
                    .where(GameSession.room_code == "kampania-1")
                )
            ).scalars().first()
            turn_id = turn.id
            break

        async def broken_broadcast(*_args, **_kwargs):
            raise RuntimeError("socket test failure")

        monkeypatch.setattr(
            image_service.ws_manager,
            "broadcast_to_session",
            broken_broadcast,
        )
        failed = await client.post(
            "/api/generate-image",
            json={"turn_id": turn_id},
        )

        assert failed.status_code == 500
        assert failed.headers["content-type"].startswith("application/json")
        assert "spróbuj ponownie" in failed.json()["detail"]

        async for db in get_db():
            session = (
                await db.execute(
                    select(GameSession).where(GameSession.room_code == "kampania-1")
                )
            ).scalar_one()
            refreshed_turn = await db.get(Turn, turn_id)
            assert session.last_image_generated_at is None
            assert refreshed_turn.is_generating_image is False
            break

        async def successful_broadcast(*_args, **_kwargs):
            return None

        async def generated_image(*_args, **_kwargs):
            return "/uploads/test-image.svg"

        monkeypatch.setattr(
            image_service.ws_manager,
            "broadcast_to_session",
            successful_broadcast,
        )
        monkeypatch.setattr(
            image_service,
            "generate_scene_image_ai",
            generated_image,
        )
        retried = await client.post(
            "/api/generate-image",
            json={"turn_id": turn_id},
        )

        assert retried.status_code == 200
        assert retried.json()["image_url"] == "/uploads/test-image.svg"
