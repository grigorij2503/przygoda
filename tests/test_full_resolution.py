import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.main import app, resolve_turn_background
from app.database import get_db
from app.models import GameSession, Character, Turn

@pytest_asyncio.fixture(autouse=True)
async def setup_resolution_app():
    async with app.router.lifespan_context(app):
        yield

@pytest.mark.asyncio
async def test_full_turn_resolution_and_level_up():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Pobierz sesję
        sess_res = await ac.get("/api/session?room_code=kampania-1")
        assert sess_res.status_code == 200
        session_id = sess_res.json()["session_id"]

        # Stwórz unikalną postać
        char_res = await ac.post("/api/characters?room_code=kampania-1", json={
            "player_name": "GraczLevelUp",
            "name": "AragornTestowy",
            "character_class": "Wojownik",
            "strength": 2,
            "agility": 1,
            "intellect": 1,
            "charisma": 0
        })
        assert char_res.status_code == 200
        char_id = char_res.json()["character_id"]

        # Pobierz bieżącą turę
        async for db in get_db():
            s_stmt = select(GameSession).where(GameSession.id == session_id)
            session = (await db.execute(s_stmt)).scalar_one()
            t_stmt = select(Turn).where(Turn.session_id == session_id, Turn.turn_number == session.current_turn_number)
            current_turn = (await db.execute(t_stmt)).scalar_one()

            # Złóż akcję
            await ac.post("/api/actions", json={
                "character_id": char_id,
                "action_text": "Zasłaniam się tarczą i tnę mieczem wroga."
            })

            # Bezpośrednio wywołaj resolve_turn_background
            await resolve_turn_background(session_id, current_turn.id)
            break

        # Sprawdź stan sesji po rozstrzygnięciu tury
        updated_sess = await ac.get("/api/session?room_code=kampania-1")
        data = updated_sess.json()
        assert data["current_turn_number"] >= 2
        assert any(t["status"] == "completed" for t in data["turns"])
