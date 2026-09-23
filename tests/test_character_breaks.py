"""Character breaks preserve progression and remove open-turn participation."""

import time
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Character, GameSession, PlayerAction, ProxyActionDecision, Turn
from app.services.runtime import GM_SESSION_COOKIE, create_gm_session_token
from app.services.room_access import ROOM_SESSION_COOKIE, create_room_session_token


@pytest_asyncio.fixture
async def isolated_character_break():
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
            room_code="break-isolated",
            status="in_progress",
            current_turn_number=60,
        )
        db.add(session)
        await db.flush()
        character = Character(
            session_id=session.id,
            player_name="Chory gracz",
            name="Arven",
            level=9,
            xp=1234,
            current_hp=17,
            max_hp=35,
            coins=21,
        )
        db.add(character)
        await db.flush()
        turn = Turn(
            session_id=session.id,
            turn_number=60,
            status="waiting_for_actions",
        )
        db.add(turn)
        await db.flush()
        db.add(PlayerAction(
            turn_id=turn.id,
            character_id=character.id,
            action_text="Idę dalej z drużyną.",
        ))
        db.add(ProxyActionDecision(
            turn_id=turn.id,
            target_character_id=character.id,
            options=[],
            status="open",
            opened_at=datetime.now(timezone.utc),
            closes_at=datetime.now(timezone.utc) + timedelta(hours=2),
        ))
        await db.commit()
        character_id = character.id

    async def override_db():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            client.cookies.set(
                GM_SESSION_COOKIE,
                create_gm_session_token(int(time.time()) + 3600),
            )
            client.cookies.set(
                ROOM_SESSION_COOKIE,
                create_room_session_token(int(time.time()) + 3600, "break-isolated"),
            )
            yield client, factory, character_id
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_break_preserves_progress_and_can_be_reversed(isolated_character_break):
    client, factory, character_id = isolated_character_break
    paused = await client.put(
        f"/api/admin/characters/{character_id}/participation",
        json={
            "room_code": "break-isolated",
            "participation_status": "on_break",
        },
    )
    assert paused.status_code == 200
    assert paused.json()["break_started_turn"] == 60

    async with factory() as db:
        character = (
            await db.execute(select(Character).where(Character.id == character_id))
        ).scalar_one()
        assert character.participation_status == "on_break"
        assert (character.level, character.xp, character.current_hp, character.max_hp) == (
            9, 1234, 17, 35,
        )
        assert character.coins == 21
        assert (
            await db.execute(
                select(PlayerAction).where(PlayerAction.character_id == character_id)
            )
        ).scalar_one_or_none() is None
        assert (
            await db.execute(
                select(ProxyActionDecision).where(
                    ProxyActionDecision.target_character_id == character_id
                )
            )
        ).scalar_one_or_none() is None

    blocked_action = await client.post("/api/actions", json={
        "character_id": character_id,
        "action_text": "Wracam do przygody bez zgody MG.",
    })
    assert blocked_action.status_code == 409

    resumed = await client.put(
        f"/api/admin/characters/{character_id}/participation",
        json={
            "room_code": "break-isolated",
            "participation_status": "active",
        },
    )
    assert resumed.status_code == 200
    assert resumed.json()["participation_status"] == "active"
    assert resumed.json()["break_started_turn"] is None

    async with factory() as db:
        character = (
            await db.execute(select(Character).where(Character.id == character_id))
        ).scalar_one()
        assert (character.level, character.xp, character.current_hp, character.max_hp) == (
            9, 1234, 17, 35,
        )


@pytest.mark.asyncio
async def test_gm_can_resolve_fully_incapacitated_party_with_retreat(isolated_character_break):
    client, factory, character_id = isolated_character_break
    async with factory() as db:
        character = (
            await db.execute(select(Character).where(Character.id == character_id))
        ).scalar_one()
        session = (await db.execute(select(GameSession))).scalar_one()
        character.current_hp = 0
        character.is_alive = False
        character.death_state = "downed"
        character.death_failures = 1
        character.status_effects = [{
            "type": "burning", "label": "Poparzony", "icon": "🔥",
            "turns_remaining": 2, "potency": 1,
        }]
        session.active_boss_name = "Purpurowa Bestia"
        session.active_boss_title = "Bestia z otchłani"
        session.active_boss_hp = 40
        session.active_boss_max_hp = 80
        resting_character = Character(
            session_id=session.id,
            player_name="Nieobecny gracz",
            name="Lira",
            current_hp=12,
            max_hp=30,
            participation_status="on_break",
            break_started_turn=59,
            status_effects=[{
                "type": "burning", "label": "Poparzony", "icon": "🔥",
                "turns_remaining": 2, "potency": 1,
            }],
        )
        dead_character = Character(
            session_id=session.id,
            player_name="Poległy gracz",
            name="Torin",
            current_hp=0,
            max_hp=30,
            is_alive=False,
            death_state="dead",
            death_failures=3,
        )
        db.add_all([resting_character, dead_character])
        await db.execute(delete(PlayerAction))
        await db.commit()
        resting_id = resting_character.id
        dead_id = dead_character.id

    response = await client.post(
        "/api/session/resolve-party-crisis",
        json={"room_code": "break-isolated"},
    )

    assert response.status_code == 200
    assert response.json()["new_turn_number"] == 61
    async with factory() as db:
        character = (
            await db.execute(select(Character).where(Character.id == character_id))
        ).scalar_one()
        session = (await db.execute(select(GameSession))).scalar_one()
        turns = list((await db.execute(select(Turn).order_by(Turn.turn_number))).scalars())
        resting_character = (
            await db.execute(select(Character).where(Character.id == resting_id))
        ).scalar_one()
        dead_character = (
            await db.execute(select(Character).where(Character.id == dead_id))
        ).scalar_one()

    assert (character.current_hp, character.is_alive, character.death_state) == (1, True, "alive")
    assert character.death_failures == 0
    assert character.status_effects == []
    assert session.active_boss_name is None
    assert session.current_turn_number == 61
    assert (resting_character.current_hp, resting_character.participation_status) == (12, "on_break")
    assert resting_character.status_effects[0]["type"] == "burning"
    assert (dead_character.current_hp, dead_character.death_state) == (0, "dead")
    assert turns[0].status == "completed"
    assert turns[0].combat_events[0]["type"] == "party_retreat"
    assert turns[1].status == "waiting_for_actions"


@pytest.mark.asyncio
async def test_party_retreat_is_rejected_while_an_active_character_can_act(
    isolated_character_break,
):
    client, factory, _ = isolated_character_break

    response = await client.post(
        "/api/session/resolve-party-crisis",
        json={"room_code": "break-isolated"},
    )

    assert response.status_code == 409
    async with factory() as db:
        session = (await db.execute(select(GameSession))).scalar_one()
        turns = list((await db.execute(select(Turn))).scalars())
    assert session.current_turn_number == 60
    assert len(turns) == 1
    assert turns[0].status == "waiting_for_actions"
