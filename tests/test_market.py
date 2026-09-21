"""Market behavior on an isolated in-memory database."""

import time

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Character, GameSession, InventoryItem
from app.services import market_service
from app.services.room_access import ROOM_SESSION_COOKIE, create_room_session_token
from app.worlds.registry import get_default_world_pack


@pytest_asyncio.fixture
async def isolated_market():
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
            room_code="market-isolated",
            status="in_progress",
            current_turn_number=1,
            crafting_available_until_turn=1,
        )
        db.add(session)
        await db.flush()
        character = Character(
            session_id=session.id, player_name="Gracz", name="Runa",
            coins=30, agility=2, charisma=2,
        )
        db.add(character)
        await db.flush()
        character = (await db.execute(
            select(Character).options(selectinload(Character.inventory)).where(Character.id == character.id)
        )).scalar_one()
        market_service.open_market_visit(
            session, [character], get_default_world_pack(), 1, guaranteed=True
        )
        await db.commit()
        character_id = character.id

    async def override_db():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            client.cookies.set(ROOM_SESSION_COOKIE, create_room_session_token(int(time.time()) + 3600))
            yield client, factory, character_id
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_buy_and_sell_change_wallet_stock_and_inventory(isolated_market):
    client, factory, character_id = isolated_market
    async with factory() as db:
        session = (await db.execute(select(GameSession).where(GameSession.room_code == "market-isolated"))).scalar_one()
        offer = session.market_state["offers"][0]
        original_price = offer["price"]

    bought = await client.post("/api/market/transaction", json={
        "character_id": character_id, "operation": "buy", "offer_id": offer["id"],
    })
    assert bought.status_code == 200
    assert bought.json()["coins_delta"] == -original_price

    async with factory() as db:
        character = (await db.execute(select(Character).where(Character.id == character_id))).scalar_one()
        item = (await db.execute(select(InventoryItem).where(
            InventoryItem.character_id == character_id, InventoryItem.name == offer["name"],
        ))).scalar_one()
        session = (await db.execute(select(GameSession).where(GameSession.room_code == "market-isolated"))).scalar_one()
        assert character.coins == 30 - original_price
        assert next(entry for entry in session.market_state["offers"] if entry["id"] == offer["id"])["stock"] == 0
        item_id = item.id

    sold = await client.post("/api/market/transaction", json={
        "character_id": character_id, "operation": "sell", "item_id": item_id,
    })
    assert sold.status_code == 200
    assert 0 < sold.json()["coins_delta"] < original_price
    async with factory() as db:
        character = (await db.execute(select(Character).where(Character.id == character_id))).scalar_one()
        assert character.coins == 30 - original_price + sold.json()["coins_delta"]
        assert (await db.execute(select(InventoryItem).where(InventoryItem.id == item_id))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_caught_theft_fines_and_blocks_next_merchant(isolated_market, monkeypatch):
    client, factory, character_id = isolated_market
    monkeypatch.setattr(market_service.secrets, "randbelow", lambda _: 0)
    async with factory() as db:
        session = (await db.execute(select(GameSession).where(GameSession.room_code == "market-isolated"))).scalar_one()
        offer = session.market_state["offers"][0]

    caught = await client.post("/api/market/interact", json={
        "character_id": character_id, "text": f"Kradnę po cichu {offer['name']}.",
    })
    assert caught.status_code == 200
    assert caught.json()["success"] is False
    assert caught.json()["coins_lost"] > 0
    retry = await client.post("/api/market/interact", json={
        "character_id": character_id, "text": f"Kradnę {offer['name']}.",
    })
    assert retry.status_code == 403

    async with factory() as db:
        session = (await db.execute(select(GameSession).where(GameSession.room_code == "market-isolated"))).scalar_one()
        character = (await db.execute(
            select(Character).options(selectinload(Character.inventory)).where(Character.id == character_id)
        )).scalar_one()
        next_visit = market_service.build_market_visit(
            session.market_state, [character], get_default_world_pack(), 2, guaranteed=True
        )
        assert character_id in next_visit["banned"]
        assert character.coins == 30 - caught.json()["coins_lost"]
