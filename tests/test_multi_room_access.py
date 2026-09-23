"""Room-bound authentication and parallel campaign isolation."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import Character, GameSession, Turn


@pytest.mark.asyncio
async def test_parallel_rooms_have_independent_credentials_and_state(monkeypatch):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_db():
        async with factory() as db:
            yield db

    monkeypatch.setattr(settings, "GM_PIN", "2468")
    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            scenario = "Krasnoludzka Twierdza opanowana przez demony ognia"
            for room_code, password in (("piatkowa-gra", "pierwsze-haslo"), ("sobotnia-gra", "drugie-haslo")):
                created = await client.post("/api/rooms", json={
                    "room_code": room_code,
                    "password": password,
                    "title": room_code,
                    "gm_pin": "2468",
                    "world_pack_id": "dark_fantasy",
                    "world_pack_version": 1,
                    "scenario_type": scenario,
                    "tone": "Mroczna wyprawa testowa",
                })
                assert created.status_code == 200

            logged_in = await client.post("/api/verify-password", json={
                "room_code": "piatkowa-gra", "password": "pierwsze-haslo",
            })
            assert logged_in.status_code == 200
            first_session_response = await client.get("/api/session?room_code=piatkowa-gra")
            assert first_session_response.status_code == 200
            first_session = first_session_response.json()
            assert first_session["world_pack_id"] == "dark_fantasy"
            assert first_session["world_pack_version"] == 1
            assert first_session["scenario_type"] == scenario
            assert first_session["setting_theme"] == "Mroczna wyprawa testowa"
            assert (await client.get("/api/session?room_code=sobotnia-gra")).status_code == 403

            logged_in = await client.post("/api/verify-password", json={
                "room_code": "sobotnia-gra", "password": "drugie-haslo",
            })
            assert logged_in.status_code == 200
            assert (await client.get("/api/session?room_code=sobotnia-gra")).status_code == 200
            assert (await client.get("/api/session?room_code=piatkowa-gra")).status_code == 403

        async with factory() as db:
            rooms = (await db.execute(select(GameSession))).scalars().all()
            assert {room.room_code for room in rooms} == {"piatkowa-gra", "sobotnia-gra"}
            assert all(room.room_password_hash for room in rooms)
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_legacy_campaign_is_kept_when_password_is_migrated():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        session = GameSession(
            room_code="kampania-1",
            title="Zachowana rozgrywka",
            campaign_intro="Dotychczasowy zapis.",
            current_turn_number=7,
        )
        db.add(session)
        await db.flush()
        db.add_all([
            Character(session_id=session.id, player_name="Gracz", name="Ocalały"),
            Turn(session_id=session.id, turn_number=7, status="waiting_for_actions"),
        ])
        await db.commit()

    async def override_db():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/verify-password", json={
                "room_code": "kampania-1", "password": settings.ROOM_PASSWORD,
            })
            assert response.status_code == 200

        async with factory() as db:
            session = (
                await db.execute(select(GameSession).where(GameSession.room_code == "kampania-1"))
            ).scalar_one()
            characters = (
                await db.execute(select(Character).where(Character.session_id == session.id))
            ).scalars().all()
            assert session.title == "Zachowana rozgrywka"
            assert session.current_turn_number == 7
            assert session.room_password_hash
            assert [character.name for character in characters] == ["Ocalały"]
            assert characters[0].narrative_form == "neutral"
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()
