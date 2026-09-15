"""Contracts for pack-driven content without registering a second campaign."""

import pytest
from pydantic import ValidationError

from app.combat import build_enemy_encounter, effect_from_attack
from app.dice import deduce_tested_attribute_details
from app.magic import get_ability_book, validate_ability_action
from app.map_generator import generate_campaign_map
from app.models import Character
from app.services.world_service import serialize_world_runtime
from app.worlds.models import WorldPack
from app.worlds.registry import WORLD_PACK_REGISTRY, WorldPackNotFoundError


def trial_pack() -> WorldPack:
    payload = WORLD_PACK_REGISTRY.default.model_dump(mode="json")
    payload["id"] = "trial_world"
    payload["version"] = 1
    payload["display_name"] = "Próbny świat"
    payload["theme_id"] = "trial"
    payload["theme"]["id"] = "trial"
    payload["attributes"][2]["label"] = "Technika"
    payload["action_stat_cues"] = [
        {"marker": "hack", "stat": "intellect", "weight": 4},
        {"marker": "sensor", "stat": "perception", "weight": 4},
    ]
    payload["map_profile"]["start_location_name"] = "Stacja wejściowa"
    payload["map_profile"]["room_types"][0]["names"] = ["Stacja wejściowa"]
    payload["enemy_profile"]["role_label"] = "agent"
    payload["enemy_profile"]["features"][0]["name"] = "Żuraw serwisowy"
    payload["enemy_profile"]["attacks"][0]["name"] = "Impuls zakłócający"
    payload["narrative_profile"]["loot_search_action"]["label"] = "Przeszukaj sprzęt"
    payload["classes"][2]["id"] = "hacker"
    payload["classes"][2]["name"] = "Haker"
    payload["classes"][2]["ability_book"]["title"] = "Księga hacków"
    payload["abilities"][2]["name"] = "Skan sieci"
    payload["abilities"][2]["action_text"] = "Skanuję sieć w poszukiwaniu zagrożeń."
    return WorldPack.model_validate(payload)


def test_trial_content_flows_through_generic_interfaces():
    pack = trial_pack()
    runtime = serialize_world_runtime(pack)
    book = get_ability_book(pack, "hacker", 1)
    encounter = build_enemy_encounter([], "System ochrony", pack)
    layout = generate_campaign_map(3078, "Próba", "Technologia", pack.map_profile)

    assert runtime["attributes"][2]["label"] == "Technika"
    assert runtime["action_stat_cues"][0]["marker"] == "hack"
    assert runtime["classes"][2]["name"] == "Haker"
    assert runtime["loot_search_action"]["label"] == "Przeszukaj sprzęt"
    assert book["title"] == "Księga hacków"
    assert book["abilities"][2]["name"] == "Skan sieci"
    assert encounter["features"][0]["name"] == "Żuraw serwisowy"
    assert encounter["telegraph"]["name"] == "Impuls zakłócający"
    start_node = next(
        node for node in layout["nodes"] if node["id"] == layout["start_node_id"]
    )
    assert start_node["name"] == "Stacja wejściowa"


def test_trial_action_cues_keep_technical_analysis_distinct_from_sensors():
    pack = trial_pack()
    character = Character(
        strength=1, agility=1, intellect=2, charisma=0, perception=1,
    )
    assert deduce_tested_attribute_details(
        "Hackuję terminal.", character, "interact", world_pack=pack
    )["tested_stat"] == "intellect"
    assert deduce_tested_attribute_details(
        "Skanuję sensorami wejście.", character, "interact", world_pack=pack
    )["tested_stat"] == "perception"


def test_trial_ability_validation_is_closed_to_other_class_ids():
    pack = trial_pack()
    ability, error = validate_ability_action(
        pack, "hacker", 1, "Skanuję sieć.", "detect_magic"
    )
    assert error is None
    assert ability["mechanic_key"] == "scan"

    with pytest.raises(WorldPackNotFoundError, match="unknown class"):
        validate_ability_action(pack, "unknown_class", 1, "Skanuję sieć.", None)


def test_declared_status_overrides_world_keyword_cues():
    pack = trial_pack()
    status = effect_from_attack(
        "Wykonuję precyzyjny atak.",
        "success",
        "Haker",
        {
            "mechanic_key": "damage",
            "mechanic_params": {
                "status_type": "poisoned",
                "status_duration": 4,
                "status_potency": 2,
            },
        },
        pack,
    )
    assert status["type"] == "poisoned"
    assert status["turns_remaining"] == 4
    assert status["potency"] == 2


def test_pack_rejects_unsupported_or_invalid_mechanic_parameters():
    payload = WORLD_PACK_REGISTRY.default.model_dump(mode="json")
    payload["abilities"][0]["mechanic_params"] = [
        {"key": "arbitrary_code", "value": "run_me"}
    ]
    with pytest.raises(ValidationError, match="unsupported parameters"):
        WorldPack.model_validate(payload)

    payload["abilities"][0]["mechanic_params"] = [
        {"key": "status_type", "value": "unknown_status"}
    ]
    with pytest.raises(ValidationError, match="unknown status type"):
        WorldPack.model_validate(payload)
