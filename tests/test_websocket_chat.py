import json
import pytest
from fastapi.testclient import TestClient
from app.main import app

def test_websocket_chat_communication():
    client = TestClient(app)

    # 1. Pobierz sesję i stwórz postać testową
    sess_res = client.get("/api/session?room_code=kampania-1")
    assert sess_res.status_code == 200
    session_id = sess_res.json()["session_id"]

    char_res = client.post("/api/characters?room_code=kampania-1", json={
        "player_name": "Czatownik1",
        "name": "MówcaTestowy",
        "character_class": "Bard",
        "strength": 0,
        "agility": 1,
        "intellect": 1,
        "charisma": 2
    })
    assert char_res.status_code == 200
    char_id = char_res.json()["character_id"]

    # 2. Połącz klienta WebSocket
    with client.websocket_connect(f"/ws/{session_id}/{char_id}") as ws1:
        # Pierwsza wiadomość: PLAYER_CONNECTED
        msg1 = ws1.receive_json()
        assert msg1["type"] == "PLAYER_CONNECTED"

        # 3. Wyślij wiadomość na czacie
        chat_payload = {
            "type": "CHAT_MESSAGE",
            "author": "MówcaTestowy",
            "character_class": "Bard",
            "text": "Przygotujcie się na starcie w mroku!"
        }
        ws1.send_text(json.dumps(chat_payload))

        # 4. Odbierz zbroadcastowaną wiadomość czatu
        chat_response = ws1.receive_json()
        assert chat_response["type"] == "CHAT_MESSAGE"
        assert chat_response["author"] == "MówcaTestowy"
        assert chat_response["text"] == "Przygotujcie się na starcie w mroku!"
        assert "time" in chat_response

        # 5. Podłącz drugiego gracza i sprawdź czy dostanie CHAT_HISTORY z tą wiadomością
        with client.websocket_connect(f"/ws/{session_id}/9999") as ws2:
            # Pierwsza wiadomość to PLAYER_CONNECTED dla drugiego gracza
            connected_msg = ws2.receive_json()
            assert connected_msg["type"] == "PLAYER_CONNECTED"

            # Druga wiadomość to CHAT_HISTORY
            history_msg = ws2.receive_json()
            assert history_msg["type"] == "CHAT_HISTORY"
            assert len(history_msg["messages"]) >= 1
            assert any(m["text"] == "Przygotujcie się na starcie w mroku!" for m in history_msg["messages"])
