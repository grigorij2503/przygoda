import ast
import json
import time
from pathlib import Path

import pytest
import pytest_asyncio
from fastapi.routing import APIRoute, APIWebSocketRoute
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.magic import get_magic_book
from app.main import app
from app.map_generator import GENERATOR_VERSION, generate_campaign_map, serialize_campaign_map
from app.models import CampaignMap, Character, GameSession
from app.services.room_access import ROOM_SESSION_COOKIE, create_room_session_token


CONTRACT_PATH = Path(__file__).parent / "fixtures" / "dark_fantasy_v1_contract.json"


def iter_registered_routes(routes):
    """Flatten FastAPI's lazy included routers without depending on private types."""
    for route in routes:
        included_router = getattr(route, "original_router", None)
        if included_router is not None:
            yield from iter_registered_routes(included_router.routes)
        else:
            yield route


@pytest.fixture(scope="module")
def dark_fantasy_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


@pytest_asyncio.fixture
async def isolated_contract_db():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as db:
        db.add(GameSession(
            room_code="dark-fantasy-contract",
            title="Cienie Nad Przeklętą Kryptą",
            setting_theme="Dark Fantasy / Gotycki Horror",
            campaign_intro="Kontrakt istniejącej kampanii Dark Fantasy.",
            current_turn_number=1,
            status="lobby",
        ))
        await db.commit()

    async def override_get_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield session_factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


def test_public_route_table_matches_current_contract(dark_fantasy_contract):
    actual_http_routes: dict[str, set[str]] = {}
    actual_websocket_routes = []
    static_public_paths = {"/", "/favicon.ico", "/manifest.json", "/sw.js"}

    for route in iter_registered_routes(app.routes):
        if (
            isinstance(route, APIRoute)
            and (route.path.startswith("/api/") or route.path in static_public_paths)
        ):
            methods = {method for method in route.methods if method not in {"HEAD", "OPTIONS"}}
            actual_http_routes.setdefault(route.path, set()).update(methods)
        elif isinstance(route, APIWebSocketRoute):
            actual_websocket_routes.append(route.path)

    expected_http_routes = {
        path: set(methods)
        for path, methods in dark_fantasy_contract["public_http_routes"].items()
    }
    assert actual_http_routes == expected_http_routes
    assert sorted(actual_websocket_routes) == sorted(
        dark_fantasy_contract["public_websocket_routes"]
    )


def test_websocket_event_names_match_current_contract(dark_fantasy_contract):
    event_types = set()
    app_directory = Path(__file__).parents[1] / "app"
    for source_path in app_directory.rglob("*.py"):
        syntax_tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(syntax_tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "type"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                    and value.value.replace("_", "").isupper()
                ):
                    event_types.add(value.value)

    assert event_types == set(dark_fantasy_contract["websocket_event_types"])


def test_current_class_ability_books_match_contract(dark_fantasy_contract):
    for class_name, class_contract in dark_fantasy_contract["classes"].items():
        expected_book = class_contract["ability_book"]
        actual_book = get_magic_book(class_name, level=25)
        if expected_book is None:
            assert actual_book is None
            continue

        assert actual_book["kind"] == expected_book["kind"]
        assert actual_book["title"] == expected_book["title"]
        assert actual_book["casting_stat"] == expected_book["casting_stat"]
        assert [
            [ability["id"], ability["required_level"]]
            for ability in actual_book["abilities"]
        ] == expected_book["abilities"]
        assert all(ability["unlocked"] is True for ability in actual_book["abilities"])


def test_current_map_profile_matches_contract(dark_fantasy_contract):
    map_contract = dark_fantasy_contract["map"]
    layout = generate_campaign_map(3078, "Kontrakt", "Dark Fantasy")

    assert GENERATOR_VERSION == map_contract["generator_version"]
    assert layout["start_node_id"] == map_contract["start_node_id"]
    assert layout["nodes"][0]["name"] == map_contract["start_name"]
    final_node = next(
        node for node in layout["nodes"] if node["id"] == layout["final_node_id"]
    )
    assert final_node["name"] == map_contract["finale_name"]

    campaign_map = CampaignMap(
        seed=3078,
        generator_version=GENERATOR_VERSION,
        layout=layout,
        current_node_id=layout["start_node_id"],
        discovered_node_ids=[layout["start_node_id"]],
    )
    serialized = serialize_campaign_map(campaign_map)
    hidden_nodes = [node for node in serialized["nodes"] if node["visibility"] == "hidden"]
    assert hidden_nodes
    assert all(node["name"] == map_contract["hidden_name"] for node in hidden_nodes)


@pytest.mark.asyncio
async def test_existing_classes_keep_starter_items_and_session_shape(
    isolated_contract_db,
    dark_fantasy_contract,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(ROOM_SESSION_COOKIE, create_room_session_token(int(time.time()) + 3600))
        created_ids = []
        for index, (class_name, class_contract) in enumerate(
            dark_fantasy_contract["classes"].items(),
            start=1,
        ):
            response = await client.post(
                "/api/characters?room_code=dark-fantasy-contract",
                json={
                    "player_name": f"Gracz kontraktowy {index}",
                    "name": f"Bohater kontraktowy {index}",
                    "character_class": class_name,
                    "strength": 2,
                    "agility": 1,
                    "intellect": 1,
                    "charisma": 0,
                },
            )
            assert response.status_code == 200
            created_ids.append(response.json()["character_id"])

        session_response = await client.get(
            "/api/session?room_code=dark-fantasy-contract"
        )
        assert session_response.status_code == 200
        session_payload = session_response.json()

    assert set(session_payload) == set(dark_fantasy_contract["session_response_keys"])
    assert session_payload["setting_theme"] == "Dark Fantasy / Gotycki Horror"
    assert session_payload["world_pack_id"] == "dark_fantasy"
    assert session_payload["world_pack_version"] == 1
    assert session_payload["world_pack"]["key"] == "dark_fantasy@1"

    characters_by_class = {
        character["character_class"]: character
        for character in session_payload["characters"]
        if character["id"] in created_ids
    }
    for class_name, class_contract in dark_fantasy_contract["classes"].items():
        character = characters_by_class[class_name]
        assert set(character) == set(dark_fantasy_contract["character_response_keys"])
        assert character["class_id"] == class_contract["class_id"]
        assert character["narrative_form"] == "neutral"
        assert character["perception"] == 0
        assert sorted(item["name"] for item in character["inventory"]) == sorted(
            class_contract["starter_items"]
        )
        assert character["current_hp"] == 30
        assert character["max_hp"] == 30

    async with isolated_contract_db() as db:
        characters = (
            await db.execute(
                select(Character)
                .where(Character.id.in_(created_ids))
                .options(selectinload(Character.inventory))
            )
        ).scalars().all()
        assert len(characters) == len(dark_fantasy_contract["classes"])


@pytest.mark.asyncio
async def test_current_ui_markers_remain_rendered(
    isolated_contract_db,
    dark_fantasy_contract,
):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    for marker in dark_fantasy_contract["ui_markers"]:
        assert marker in response.text
