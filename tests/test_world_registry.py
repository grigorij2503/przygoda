import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.main import app
from app.models import GameSession
from app.schemas import SubmitActionRequest
from app.services.world_service import resolve_requested_world_pack
from app.worlds.models import WorldPack
from app.worlds.registry import WORLD_PACK_REGISTRY, WorldPackNotFoundError


def test_registry_contains_only_versioned_dark_fantasy_pack():
    packs = WORLD_PACK_REGISTRY.list()

    assert [pack.key for pack in packs] == ["dark_fantasy@1"]
    assert WORLD_PACK_REGISTRY.default is packs[0]
    assert packs[0].ruleset_id == "d20_v1"
    assert [attribute.id for attribute in packs[0].attributes] == [
        "strength",
        "agility",
        "intellect",
        "charisma",
        "perception",
    ]


def test_registry_never_falls_back_for_an_explicit_unknown_version():
    with pytest.raises(WorldPackNotFoundError, match="unknown world pack"):
        WORLD_PACK_REGISTRY.get("dark_fantasy", 2)

    with pytest.raises(WorldPackNotFoundError, match="provided together"):
        WORLD_PACK_REGISTRY.get("dark_fantasy", None)


def test_world_pack_rejects_unknown_ability_references():
    payload = WORLD_PACK_REGISTRY.default.model_dump(mode="json")
    wizard = next(item for item in payload["classes"] if item["id"] == "wizard")
    wizard["ability_book"]["ability_ids"].append("unknown_spell")

    with pytest.raises(ValidationError, match="unknown abilities"):
        WorldPack.model_validate(payload)


def test_world_pack_rejects_noncanonical_d20_attributes():
    payload = WORLD_PACK_REGISTRY.default.model_dump(mode="json")
    payload["attributes"] = payload["attributes"][:-1]

    with pytest.raises(ValidationError, match="canonical order"):
        WorldPack.model_validate(payload)


def test_default_pack_keeps_current_classes_starters_and_narrative():
    pack = WORLD_PACK_REGISTRY.default
    classes = {class_definition.name: class_definition for class_definition in pack.classes}

    assert set(classes) == {"Wojownik", "Łotrzyk", "Czarodziej", "Kleryk"}
    assert [item.name for item in classes["Wojownik"].starter_items] == [
        "Krasnoludzki Miecz",
        "Skórzana Zbroja",
        "Mikstura Lecznicza",
    ]
    assert classes["Czarodziej"].ability_book.title == "Księga czarów"
    assert classes["Kleryk"].ability_book.title == "Modlitwy i cuda"
    assert pack.narrative_profile.default_title == "Cienie Nad Przeklętą Kryptą"
    assert pack.map_profile.finale_location_name == "Sanktuarium Cienia"


def test_legacy_class_resolution_handles_polish_names_without_false_substrings():
    pack = WORLD_PACK_REGISTRY.default

    assert WORLD_PACK_REGISTRY.resolve_class(pack, "Łotrzyk").id == "rogue"
    assert WORLD_PACK_REGISTRY.resolve_class(pack, "Lotrzyk").id == "rogue"
    assert WORLD_PACK_REGISTRY.resolve_class(pack, "Pilot").id == "cleric"


def test_active_campaign_rejects_world_pack_change():
    session = GameSession(
        world_pack_id="dark_fantasy",
        world_pack_version=1,
        status="in_progress",
        current_turn_number=3,
    )

    with pytest.raises(HTTPException) as error:
        resolve_requested_world_pack(session, "cyberpunk_3078", 1)

    assert error.value.status_code == 409


def test_ability_id_accepts_legacy_alias_but_rejects_conflicts():
    legacy = SubmitActionRequest(
        character_id=1,
        action_text="Rzucam Pocisk arkanów.",
        magic_ability_id="arcane_bolt",
    )
    current = SubmitActionRequest(
        character_id=1,
        action_text="Rzucam Pocisk arkanów.",
        ability_id="arcane_bolt",
    )

    assert legacy.selected_ability_id == "arcane_bolt"
    assert current.selected_ability_id == "arcane_bolt"
    with pytest.raises(ValidationError, match="must identify the same ability"):
        SubmitActionRequest(
            character_id=1,
            action_text="Sprzeczne ID.",
            ability_id="arcane_bolt",
            magic_ability_id="meteor",
        )


@pytest.mark.asyncio
async def test_world_catalog_exposes_public_summaries_without_selection():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/worlds")

    assert response.status_code == 200
    payload = response.json()
    assert payload["default_world"] == {
        "id": "dark_fantasy",
        "version": 1,
        "key": "dark_fantasy@1",
    }
    assert [world["key"] for world in payload["worlds"]] == ["dark_fantasy@1"]
    assert [attribute["id"] for attribute in payload["worlds"][0]["attributes"]] == [
        "strength",
        "agility",
        "intellect",
        "charisma",
        "perception",
    ]
