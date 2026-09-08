import json
import logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # session_id -> list of (WebSocket, character_id)
        self.active_rooms: Dict[int, List[Dict[str, any]]] = {}
        # session_id -> list of recent chat messages (max 50)
        self.chat_history: Dict[int, List[Dict[str, any]]] = {}

    def add_chat_message(self, session_id: int, message: dict):
        if session_id not in self.chat_history:
            self.chat_history[session_id] = []
        self.chat_history[session_id].append(message)
        if len(self.chat_history[session_id]) > 50:
            self.chat_history[session_id] = self.chat_history[session_id][-50:]

    def get_chat_history(self, session_id: int) -> List[dict]:
        return list(self.chat_history.get(session_id, []))

    async def connect(self, websocket: WebSocket, session_id: int, character_id: int):
        await websocket.accept()
        if session_id not in self.active_rooms:
            self.active_rooms[session_id] = []
        self.active_rooms[session_id].append({
            "ws": websocket,
            "character_id": character_id
        })
        logger.info(f"WebSocket connected for character {character_id} in session {session_id}")

    def disconnect(self, websocket: WebSocket, session_id: int):
        if session_id in self.active_rooms:
            self.active_rooms[session_id] = [
                conn for conn in self.active_rooms[session_id] if conn["ws"] != websocket
            ]
            if not self.active_rooms[session_id]:
                del self.active_rooms[session_id]
            logger.info(f"WebSocket disconnected from session {session_id}")

    async def broadcast_to_session(self, session_id: int, message: dict):
        if session_id not in self.active_rooms:
            return

        dead_connections = []
        payload = json.dumps(message)

        for conn in list(self.active_rooms.get(session_id, [])):
            try:
                await conn["ws"].send_text(payload)
            except Exception as e:
                logger.warning(f"Error broadcasting to WebSocket: {e}")
                dead_connections.append(conn)

        for dead in dead_connections:
            if dead in self.active_rooms.get(session_id, []):
                self.active_rooms[session_id].remove(dead)

ws_manager = ConnectionManager()
