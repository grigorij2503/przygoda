import json
import re
import unicodedata
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Character, ChatMessage
from app.push_service import schedule_web_push
from app.services.runtime import CHAT_HISTORY_LIMIT, logger
from app.websocket_manager import ws_manager


def chat_message_payload(message: ChatMessage) -> dict:
    created_at = message.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return {
        "type": "CHAT_MESSAGE",
        "id": message.id,
        "character_id": message.character_id,
        "author": message.author,
        "character_class": message.character_class,
        "text": message.text,
        "time": created_at.isoformat(),
    }


async def get_recent_chat_messages(session_id: int) -> list[dict]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(CHAT_HISTORY_LIMIT)
        )
        messages = list(reversed(result.scalars().all()))
    return [chat_message_payload(message) for message in messages]


async def get_mentioned_character_ids(
    session_id: int,
    sender_character_id: int,
    message_text: str,
) -> list[int]:
    async with AsyncSessionLocal() as db:
        characters = (
            await db.execute(select(Character).where(Character.session_id == session_id))
        ).scalars().all()

    normalized_text = unicodedata.normalize("NFC", message_text)
    candidates = [character for character in characters if character.id != sender_character_id]
    if re.search(r"(?<![\w@])@all(?!\w)", normalized_text, flags=re.IGNORECASE):
        return [character.id for character in candidates]

    mentioned_ids: list[int] = []
    for character in sorted(candidates, key=lambda item: len(item.name), reverse=True):
        pattern = rf"(?<![\w@])@{re.escape(unicodedata.normalize('NFC', character.name))}(?!\w)"
        if re.search(pattern, normalized_text, flags=re.IGNORECASE):
            mentioned_ids.append(character.id)
    return mentioned_ids


async def save_chat_message(
    session_id: int,
    character_id: int,
    author: str,
    character_class: str,
    text: str,
) -> dict:
    message = ChatMessage(
        session_id=session_id,
        character_id=character_id,
        author=author,
        character_class=character_class,
        text=text,
        created_at=datetime.now(timezone.utc),
    )
    async with AsyncSessionLocal() as db:
        db.add(message)
        await db.commit()
    return chat_message_payload(message)


async def websocket_endpoint(websocket: WebSocket, session_id: int, character_id: int):
    await ws_manager.connect(websocket, session_id, character_id)
    # Broadcast że gracz dołączył
    await ws_manager.broadcast_to_session(session_id, {
        "type": "PLAYER_CONNECTED",
        "character_id": character_id,
        "message": f"Gracz połączył się ze stołem gry."
    })
    # Wyślij historię czatu do połączonego gracza
    history = await get_recent_chat_messages(session_id)
    if history:
        await websocket.send_text(json.dumps({
            "type": "CHAT_HISTORY",
            "messages": history
        }))

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "CHAT_MESSAGE":
                    text = msg.get("text", "").strip()
                    if text:
                        chat_entry = await save_chat_message(
                            session_id=session_id,
                            character_id=character_id,
                            author=msg.get("author", "Gracz"),
                            character_class=msg.get("character_class", "Bohater"),
                            text=text,
                        )
                        await ws_manager.broadcast_to_session(session_id, chat_entry)
                        mentioned_ids = await get_mentioned_character_ids(
                            session_id,
                            character_id,
                            text,
                        )
                        if mentioned_ids:
                            notification_text = " ".join(text.split())
                            if len(notification_text) > 180:
                                notification_text = f"{notification_text[:177]}..."
                            schedule_web_push(
                                session_id,
                                title=f"💬 {chat_entry['author']} wspomina o Tobie",
                                body=notification_text,
                                tag=f"chat-{session_id}-{chat_entry['id']}",
                                character_ids=mentioned_ids,
                            )
            except Exception as e:
                logger.error(f"Błąd przetwarzania wiadomości WebSocket: {e}")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, session_id)
        await ws_manager.broadcast_to_session(session_id, {
            "type": "PLAYER_DISCONNECTED",
            "character_id": character_id
        })
