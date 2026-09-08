import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.main import app
from app.database import get_db
from app.models import GameSession, Character, Turn

@pytest_asyncio.fixture(autouse=True)
async def setup_app_lifespan():
    async with app.router.lifespan_context(app):
        async for db in get_db():
            s_res = await db.execute(select(GameSession).where(GameSession.room_code == "kampania-1"))
            sess = s_res.scalar_one_or_none()
            if sess:
                sess.is_turn_resolving = False
                sess.current_turn_number = 1
                sess.status = "in_progress"
                # Wyczyść ewentualne postacie testowe z poprzednich uruchomień
                c_res = await db.execute(select(Character).where(Character.name == "BohaterTestowy"))
                for c in c_res.scalars().all():
                    await db.delete(c)
                # Upewnij się, że tura 1 jest w stanie waiting_for_actions
                t_res = await db.execute(select(Turn).where(Turn.session_id == sess.id, Turn.turn_number == 1))
                turn1 = t_res.scalar_one_or_none()
                if not turn1:
                    turn1 = Turn(
                        session_id=sess.id,
                        turn_number=1,
                        status="waiting_for_actions",
                        gm_narration=sess.campaign_intro or "Wyprawa rozpoczęta",
                        next_turn_prompt="Szkielety unoszą zardzewiałe miecze, a w ich pustych oczodołach płonie błękitny ogień. Co robicie?",
                        suggested_actions=[]
                    )
                    db.add(turn1)
                else:
                    turn1.status = "waiting_for_actions"
                await db.commit()
            break
        yield

@pytest.mark.asyncio
async def test_api_health_and_session():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Test strony głównej HTML
        home_res = await ac.get("/")
        assert home_res.status_code == 200
        assert "BRAMA PRZYGODY" in home_res.text

        # Test weryfikacji hasła
        pw_res = await ac.post("/api/verify-password", json={"password": "dragon2026"})
        assert pw_res.status_code == 200
        assert pw_res.json()["success"] is True

        # Test nieprawidłowego hasła
        bad_pw_res = await ac.post("/api/verify-password", json={"password": "zle_haslo"})
        assert bad_pw_res.status_code == 401

        # Test pobrania aktywnej sesji
        sess_res = await ac.get("/api/session?room_code=kampania-1")
        assert sess_res.status_code == 200
        data = sess_res.json()
        assert data["room_code"] == "kampania-1"
        assert "characters" in data
        assert "turns" in data
        assert len(data["turns"]) >= 1

@pytest.mark.asyncio
async def test_character_creation_and_action():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Stwórz postać
        char_payload = {
            "player_name": "TestGracz",
            "name": "BohaterTestowy",
            "character_class": "Wojownik",
            "strength": 2,
            "agility": 1,
            "intellect": 1,
            "charisma": 0
        }
        create_res = await ac.post("/api/characters?room_code=kampania-1", json=char_payload)
        assert create_res.status_code == 200
        char_id = create_res.json()["character_id"]
        assert char_id > 0

        # Sprawdź czy postać ma startowy ekwipunek
        sess_res = await ac.get("/api/session?room_code=kampania-1")
        chars = sess_res.json()["characters"]
        my_char = next(c for c in chars if c["id"] == char_id)
        assert len(my_char["inventory"]) >= 2
        assert any("Krasnoludzki Miecz" in it["name"] for it in my_char["inventory"])

        # Złóż akcję dla tej postaci
        act_res = await ac.post("/api/actions", json={
            "character_id": char_id,
            "action_text": "Atakuję wrogiego goblina mieczem z całej siły!"
        })
        assert act_res.status_code == 200
        act_data = act_res.json()
        assert act_data["success"] is True
        assert act_data["ready_count"] >= 1
