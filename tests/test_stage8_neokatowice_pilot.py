"""Pure contract checks for the first playable alternate world."""

import pytest
from pydantic import ValidationError

from app.magic import get_ability_book, validate_ability_action
from app.map_generator import generate_campaign_map
from app.models import GameSession, InventoryItem
from app.services.runtime import validate_action_item_claim
from app.services.world_service import get_session_world_pack, serialize_world_runtime
from app.worlds.models import WorldPack
from app.worlds.registry import WORLD_PACK_REGISTRY


@pytest.fixture
def pack():
    return WORLD_PACK_REGISTRY.get("neokatowice_3077", 1)


def test_pilot_has_polish_setting_four_distinct_books_and_usable_starters(pack):
    assert pack.display_name == "NeoKatowice 3077"
    assert "Polska" in pack.narrative_profile.setting_theme
    assert "Katowice" in pack.narrative_profile.campaign_intro
    assert [item.name for item in pack.classes] == [
        "Haker", "Neurotechnik", "Egzoochroniarz", "Fixer"
    ]
    assert [item.ability_book.title for item in pack.classes] == [
        "Księga hacków", "Księga neuroprotokołów",
        "Księga systemów bojowych", "Księga kontaktów"
    ]
    assert all(len(item.starter_items) >= 3 for item in pack.classes)
    assert all(item.quick_actions for item in pack.classes)
    assert pack.theme.shape_id == "cut_corner"
    assert WORLD_PACK_REGISTRY.default.theme.shape_id == "rounded"
    assert serialize_world_runtime(pack)["ui_copy"]["character_selection_heading"] == (
        "WYBIERZ SWOJEGO OPERATORA"
    )
    assert pack.narrative_profile.party_presence_prefix == "W operacji uczestniczą:"
    assert WORLD_PACK_REGISTRY.default.narrative_profile.party_presence_prefix == (
        "W wyprawie uczestniczą:"
    )


def test_every_level_one_book_ability_can_be_submitted_with_its_own_starters(pack):
    for class_definition in pack.classes:
        starter_items = [
            InventoryItem(id=index + 1, **item.model_dump())
            for index, item in enumerate(class_definition.starter_items)
        ]
        book = get_ability_book(pack, class_definition.id, 1)
        assert book is not None
        for ability in book["abilities"]:
            if not ability["unlocked"]:
                continue
            resolved, error = validate_ability_action(
                pack, class_definition.id, 1,
                ability["action_text"], ability["id"],
            )
            assert error is None
            assert resolved["id"] == ability["id"]
            assert validate_action_item_claim(
                ability["action_text"], starter_items, world_pack=pack
            ) is None


def test_pilot_map_and_lore_use_city_sectors_not_fantasy_rooms(pack):
    layout = generate_campaign_map(
        3077, "Sygnał spod Spodka", pack.narrative_profile.setting_theme,
        pack.map_profile,
    )
    nodes = {node["id"]: node for node in layout["nodes"]}
    assert nodes[layout["start_node_id"]]["name"] == "Przystanek pod Spodkiem"
    assert nodes[layout["final_node_id"]]["name"] == "Rdzeń sieci Silesia"
    assert layout["generator_id"] == "neokatowice_sectors"
    assert serialize_world_runtime(pack)["map_room_icons"]["finale"] == "⬡"
    assert serialize_world_runtime(WORLD_PACK_REGISTRY.default)["map_room_icons"] == {}
    assert {category.id for category in pack.lore_categories} == {
        "boss", "location", "npc", "weapon", "attack"
    }
    assert "Sanktuarium Cienia" not in str(layout)


def test_pinned_pilot_pack_and_controlled_shape_fail_closed(pack):
    session = GameSession(
        world_pack_id=pack.id, world_pack_version=pack.version,
    )
    assert get_session_world_pack(session) is pack

    invalid = pack.model_dump(mode="json")
    invalid["theme"]["shape_id"] = "custom-css"
    with pytest.raises(ValidationError):
        WorldPack.model_validate(invalid)
