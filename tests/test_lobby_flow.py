import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.main import app
from app.config import settings
from app.database import get_db
from app.models import GameSession, Character, Turn

@pytest_asyncio.fixture(autouse=True)
async def setup_app_lifespan():
    async with app.router.lifespan_context(app):
        yield


@pytest.mark.asyncio
async def test_scenario_reset_requires_gm_unlock():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/session/setup-scenario", json={
            "room_code": "kampania-1",
            "scenario_type": "Krypta Pradawnego Króla Lichów",
        })
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_manual_naming_requires_gm_unlock():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/api/session/trigger-naming", json={
            "session_id": 1,
            "category": "boss",
            "description": "Testowy przeciwnik",
        })
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_lobby_and_ready_check_flow(monkeypatch):
    monkeypatch.setattr(settings, "GM_PIN", "test-gm-pin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        unlock_res = await ac.post("/api/admin/unlock", json={"pin": "test-gm-pin"})
        assert unlock_res.status_code == 200

        # 1. Inicjalizacja Lobby dla nowego scenariusza
        setup_res = await ac.post("/api/session/setup-scenario", json={
            "room_code": "kampania-1",
            "scenario_type": "Krasnoludzka Twierdza opanowana przez demony ognia",
            "tone": "Grimdark Fantasy"
        })
        assert setup_res.status_code == 200
        assert setup_res.json()["status"] == "lobby"

        # 2. Sprawdzenie stanu sesji przez GET /api/session
        sess_res = await ac.get("/api/session?room_code=kampania-1")
        assert sess_res.status_code == 200
        data = sess_res.json()
        assert data["status"] == "lobby"
        assert "Wyprawa: Krasnoludzka Twierdza" in data["title"]

        # 3. Utwórz postać w lobby
        char_res = await ac.post("/api/characters?room_code=kampania-1", json={
            "player_name": "LobbyTester",
            "name": "ThorgalLobby",
            "character_class": "Wojownik",
            "strength": 2,
            "agility": 1,
            "intellect": 1,
            "charisma": 0
        })
        assert char_res.status_code == 200
        char_id = char_res.json()["character_id"]

        # 4. Sprawdzenie czy postać ma is_ready == False
        sess_res = await ac.get("/api/session?room_code=kampania-1")
        chars = sess_res.json()["characters"]
        my_char = next(c for c in chars if c["id"] == char_id)
        assert my_char["is_ready"] is False

        # 5. Próba startu bez gotowości powinna zwrócić błąd 400
        start_fail = await ac.post("/api/session/start-prologue", json={
            "room_code": "kampania-1",
            "scenario_type": "Krasnoludzka Twierdza opanowana przez demony ognia"
        })
        assert start_fail.status_code == 400
        assert "Nie wszyscy gracze są gotowi" in start_fail.json()["detail"]

        # 6. Oznaczenie postaci jako gotowa (Ready Check)
        toggle_res = await ac.post(f"/api/characters/{char_id}/toggle-ready")
        assert toggle_res.status_code == 200
        assert toggle_res.json()["is_ready"] is True

        # 7. Teraz start przygody powinien się powieść
        start_ok = await ac.post("/api/session/start-prologue", json={
            "room_code": "kampania-1",
            "scenario_type": "Krasnoludzka Twierdza opanowana przez demony ognia",
            "tone": "Grimdark Fantasy"
        })
        assert start_ok.status_code == 200
        assert start_ok.json()["success"] is True

        # 8. Weryfikacja: sesja ma status 'in_progress', Tura 1 istnieje z narracją i podpowiedziami
        sess_after = await ac.get("/api/session?room_code=kampania-1")
        data_after = sess_after.json()
        assert data_after["status"] == "in_progress"
        assert len(data_after["turns"]) >= 1
        turn1 = data_after["turns"][0]
        assert turn1["turn_number"] == 1
        assert len(turn1["suggested_actions"]) >= 3
