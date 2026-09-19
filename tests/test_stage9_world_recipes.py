"""Contract coverage for the thirteen declarative stage-nine worlds."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.map_generator import generate_campaign_map
from app.magic import get_ability_book
from app.worlds.models import WorldPack
from app.worlds.recipes import WorldRecipe, materialize_recipe
from app.worlds.registry import PACKS_DIR, WORLD_PACK_REGISTRY


STAGE_NINE_IDS = {
    "archipelag_korsarzy", "piaski_ekspedycji", "slowianska_gromada",
    "front_1944_relikty_nocy", "wiedzmy_pogranicza",
    "kurz_olow_brzydkie_sprawy", "wyspy_kruczego_sztormu",
    "wieczna_wojna_gwiazd", "katedry_popiolu",
    "norki_zielonego_wzgorza", "szepty_zatopionej_gwiazdy",
    "zagadka_gazowej_latarni", "lochy_lup_klopoty",
}
PEACEFUL_IDS = {
    "norki_zielonego_wzgorza", "szepty_zatopionej_gwiazdy",
    "zagadka_gazowej_latarni",
}


def _recipe_payload(world_id: str) -> dict:
    path: Path = PACKS_DIR / f"{world_id}_v1.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("world_id", sorted(STAGE_NINE_IDS))
def test_stage_nine_recipe_expands_to_complete_world_contract(world_id: str):
    recipe = WorldRecipe.model_validate(_recipe_payload(world_id))
    pack = WORLD_PACK_REGISTRY.get(world_id, 1)

    assert materialize_recipe(recipe) == pack
    assert WorldPack.model_validate(pack.model_dump(mode="json")) == pack
    assert pack.ruleset_id == "d20_v1"
    assert len(pack.classes) >= 3
    assert len(pack.loot_tables) == 5
    assert len(pack.theme.tokens) == 13
    assert len(pack.narrative_profile.scenario_options) >= 3
    assert pack.narrative_profile.offline_auto_enemy_naming == (world_id not in PEACEFUL_IDS)
    assert all(len(cls.starter_items) == 3 and len(cls.quick_actions) == 2
               and cls.ability_book is not None for cls in pack.classes)

    for cls in pack.classes:
        book = get_ability_book(pack, cls.id, 1)
        assert book is not None and len(book["abilities"]) >= 2
        assert book["abilities"][0]["unlocked"] is True
        assert any(not ability["unlocked"] for ability in book["abilities"])

    layout = generate_campaign_map(3077, pack.display_name, pack.narrative_profile.setting_theme,
                                   pack.map_profile)
    nodes = {node["id"]: node for node in layout["nodes"]}
    assert nodes[layout["start_node_id"]]["name"] == pack.map_profile.start_location_name
    assert nodes[layout["final_node_id"]]["name"] == pack.map_profile.finale_location_name


def test_stage_nine_recipe_source_set_is_complete():
    recipe_ids = {
        path.stem.removesuffix("_v1")
        for path in PACKS_DIR.glob("*_v1.json")
        if json.loads(path.read_text(encoding="utf-8")).get("format") == "recipe_v1"
    }
    assert recipe_ids == STAGE_NINE_IDS
    assert len(WORLD_PACK_REGISTRY.list()) == 15
    assert WORLD_PACK_REGISTRY.default.key == "dark_fantasy@1"


def test_recipe_rejects_unknown_mechanic_and_executable_extension():
    payload = _recipe_payload("zagadka_gazowej_latarni")
    payload["classes"][0]["abilities"][0]["mechanic"] = "execute_python"
    with pytest.raises(ValidationError):
        WorldRecipe.model_validate(payload)

    payload = _recipe_payload("zagadka_gazowej_latarni")
    payload["script"] = "alert('unsafe')"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        WorldRecipe.model_validate(payload)


def test_recipe_rejects_incomplete_map_and_invalid_theme_color():
    payload = _recipe_payload("szepty_zatopionej_gwiazdy")
    payload["places"]["main"] = payload["places"]["main"][:2]
    with pytest.raises(ValidationError):
        WorldRecipe.model_validate(payload)

    payload = _recipe_payload("lochy_lup_klopoty")
    payload["palette"]["primary"] = "url(https://example.invalid/asset)"
    with pytest.raises(ValidationError):
        WorldRecipe.model_validate(payload)
