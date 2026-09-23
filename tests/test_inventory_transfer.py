import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.inventory import get_effectively_equipped_items
from app.main import app
from app.models import Character, GameSession, InventoryItem


def test_helmet_and_boots_have_independent_effective_slots():
    items = [
        InventoryItem(id=1, item_type="helmet", is_equipped=True),
        InventoryItem(id=2, item_type="helmet", is_equipped=True),
        InventoryItem(id=3, item_type="boots", is_equipped=True),
    ]
    assert {item.id for item in get_effectively_equipped_items(items)} == {2, 3}


@pytest.mark.asyncio
async def test_transfer_splits_stack_and_rejects_invalid_destinations():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as db:
        db.add_all([
            GameSession(id=1, room_code="transfer-room", status="in_progress", is_turn_resolving=False),
            GameSession(id=2, room_code="another-room", status="in_progress"),
            Character(id=1, session_id=1, player_name="A", name="A", is_alive=True),
            Character(id=2, session_id=1, player_name="B", name="B", is_alive=True),
            Character(id=3, session_id=2, player_name="C", name="C", is_alive=True),
            InventoryItem(id=10, character_id=1, name="Mikstura", item_type="consumable", quantity=3, is_equipped=False),
            InventoryItem(id=11, character_id=1, name="Hełm", item_type="helmet", quantity=1, is_equipped=True),
        ])
        await db.commit()

    async def override_get_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            endpoint = "/api/characters/1/inventory/10/transfer"
            payload = {"recipient_character_id": 2, "quantity": 2}
            assert (await client.post(endpoint, json=payload)).status_code == 403
            assert (await client.post(
                "/api/verify-password", json={
                    "room_code": "transfer-room", "password": settings.ROOM_PASSWORD,
                }
            )).status_code == 200
            assert (await client.post(endpoint, json=payload)).status_code == 200
            assert (await client.post(endpoint, json={"recipient_character_id": 3, "quantity": 1})).status_code == 404
            assert (await client.post(
                "/api/characters/1/inventory/11/transfer",
                json={"recipient_character_id": 2, "quantity": 1},
            )).status_code == 400

            async with session_factory() as db:
                session = await db.get(GameSession, 1)
                session.is_turn_resolving = True
                await db.commit()
            assert (await client.post(
                endpoint, json={"recipient_character_id": 2, "quantity": 1}
            )).status_code == 409

        async with session_factory() as db:
            items = (await db.execute(select(InventoryItem).where(
                InventoryItem.name == "Mikstura"
            ))).scalars().all()
            assert sorted((item.character_id, item.quantity) for item in items) == [(1, 1), (2, 2)]
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()
