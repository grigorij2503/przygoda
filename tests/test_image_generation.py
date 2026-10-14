from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.database import get_db
from app.main import app
from app.models import GameSession, Turn
from app.services import image_service
from app import gemini_service


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
            session = (
                await db.execute(
                    select(GameSession).where(GameSession.room_code == "kampania-1")
                )
            ).scalar_one()
            turn = (
                await db.execute(
                    select(Turn)
                    .join(GameSession)
                    .where(GameSession.room_code == "kampania-1")
                )
            ).scalars().first()
            # SQLite odczytuje DateTime bez tzinfo. Historyczny znacznik nie może
            # wywołać porównania naive/aware w synchronizatorze ORM.
            session.last_image_generated_at = datetime.now() - timedelta(days=2)
            await db.commit()
            turn_id = turn.id
            break

        async def successful_broadcast(*_args, **_kwargs):
            return None

        async def broken_generation(*_args, **_kwargs):
            raise RuntimeError("image API test failure")

        monkeypatch.setattr(
            image_service.ws_manager,
            "broadcast_to_session",
            successful_broadcast,
        )
        monkeypatch.setattr(
            image_service,
            "generate_scene_image_ai",
            broken_generation,
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

        async def generated_image(*_args, **_kwargs):
            return "/uploads/test-image.svg"

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


@pytest.mark.asyncio
async def test_gemini_image_request_requires_image_modality(tmp_path, monkeypatch):
    captured = {}

    class FakeModels:
        async def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                parts=[
                    SimpleNamespace(
                        inline_data=SimpleNamespace(
                            data=b"generated-image-bytes",
                            mime_type="image/png",
                        )
                    )
                ],
                candidates=[],
            )

    fake_client = SimpleNamespace(
        aio=SimpleNamespace(models=FakeModels()),
    )
    monkeypatch.setattr(gemini_service, "get_genai_client", lambda: fake_client)
    monkeypatch.setattr(gemini_service, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(gemini_service.settings, "IMAGEN_MODEL", "gemini-2.5-flash-image")
    monkeypatch.setattr(gemini_service.time, "time", lambda: 1234567890)

    image_url = await gemini_service.generate_scene_image_ai("A scene", 65)

    assert image_url == "/uploads/turn_65_1234567890.png"
    assert (tmp_path / "turn_65_1234567890.png").read_bytes() == b"generated-image-bytes"
    assert captured["config"].response_modalities == ["IMAGE"]
    assert captured["config"].image_config.aspect_ratio == "16:9"


@pytest.mark.asyncio
async def test_matching_fallback_svg_can_be_replaced_without_waiting_a_day(
    isolated_dark_fantasy_db,
    monkeypatch,
):
    fallback_epoch = int(datetime.now().timestamp())
    async for db in get_db():
        session = (
            await db.execute(
                select(GameSession).where(GameSession.room_code == "kampania-1")
            )
        ).scalar_one()
        turn = (
            await db.execute(select(Turn).where(Turn.session_id == session.id))
        ).scalars().first()
        session.last_image_generated_at = datetime.fromtimestamp(
            fallback_epoch,
            timezone.utc,
        ).replace(tzinfo=None)
        turn.image_url = f"/uploads/turn_{turn.id}_{fallback_epoch}.svg"
        turn_id = turn.id
        await db.commit()
        break

    async def successful_broadcast(*_args, **_kwargs):
        return None

    async def generated_image(*_args, **_kwargs):
        return "/uploads/replacement.png"

    monkeypatch.setattr(image_service.settings, "GEMINI_API_KEY", "test-key")
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
        response = await client.post(
            "/api/generate-image",
            json={"turn_id": turn_id},
        )

    assert response.status_code == 200
    assert response.json()["image_url"] == "/uploads/replacement.png"
