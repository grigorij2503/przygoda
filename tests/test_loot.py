from app.loot import reconcile_loot_narration, resolve_inventory_mechanics, validate_special_action
from app.dice import calculate_item_modifier
from app.models import CampaignMap, Character, GameSession, InventoryItem, PlayerAction, Turn
from app.worlds.registry import get_default_world_pack


def make_character(character_id: int, name: str, character_class: str = "Wojownik") -> Character:
    return Character(
        id=character_id,
        session_id=1,
        player_name=name,
        name=name,
        character_class=character_class,
        level=1,
        is_alive=True,
    )


def make_map() -> CampaignMap:
    return CampaignMap(
        id=1,
        session_id=1,
        seed=1,
        generator_version=1,
        layout={"nodes": []},
        current_node_id="room-01",
        discovered_node_ids=["room-01"],
    )


def test_boss_drops_one_shared_item_and_opens_three_turn_post():
    previous_winner = make_character(1, "Aldren")
    next_winner = make_character(2, "Bera", "Czarodziej")
    session = GameSession(
        id=1,
        room_code="test",
        active_boss_name="Upiór",
        active_boss_hp=0,
        last_loot_character_id=previous_winner.id,
        crafting_available_until_turn=0,
        looted_location_ids=[],
    )
    turn = Turn(id=10, session_id=1, turn_number=4, combat_events=[
        {"type": "boss_defeated", "boss": "Upiór"},
    ])

    result = resolve_inventory_mechanics(
        session,
        turn,
        [previous_winner, next_winner],
        make_map(),
    )

    assert len(result.new_items) == 1
    assert result.new_items[0].character_id == next_winner.id
    assert result.new_items[0].stat_bonus <= 2 or result.new_items[0].item_type == "consumable"
    assert next_winner.coins == 6
    assert result.events[-1]["coins_awarded"] == 6
    assert session.crafting_available_until_turn == 7
    assert session.market_state["visit_turn"] == 5
    assert session.market_state["expires_turn"] == 7
    assert session.market_state["location_node_id"] == "room-01"


def test_location_can_produce_only_one_shared_loot_award(monkeypatch):
    monkeypatch.setattr("app.loot.secrets.randbelow", lambda upper: 1 if upper > 1 else 0)
    finder = make_character(1, "Aldren")
    recipient = make_character(2, "Bera")
    action = PlayerAction(
        id=1,
        turn_id=10,
        character_id=finder.id,
        action_text="Dokładnie przeszukuję tę lokację w poszukiwaniu łupu.",
        outcome_tier="success",
    )
    turn = Turn(id=10, session_id=1, turn_number=2, combat_events=[], actions=[action])
    session = GameSession(
        id=1,
        room_code="test",
        last_loot_character_id=finder.id,
        looted_location_ids=[],
        crafting_available_until_turn=0,
    )
    campaign_map = make_map()

    first = resolve_inventory_mechanics(session, turn, [finder, recipient], campaign_map)
    second = resolve_inventory_mechanics(session, turn, [finder, recipient], campaign_map)

    assert len(first.new_items) == 1
    assert first.new_items[0].character_id == finder.id
    assert second.new_items == []
    assert session.looted_location_ids == ["room-01"]
    assert finder.coins == 3


def test_successful_search_can_find_an_empty_room(monkeypatch):
    monkeypatch.setattr("app.loot.secrets.randbelow", lambda upper: 0)
    finder = make_character(1, "Aldren")
    action = PlayerAction(character_id=1, action_text="Przeszukuję pokój.", outcome_tier="success")
    turn = Turn(turn_number=2, combat_events=[], actions=[action])
    session = GameSession(room_code="empty", looted_location_ids=[])

    result = resolve_inventory_mechanics(session, turn, [finder], make_map())

    assert result.new_items == []
    assert result.events == [{"type": "loot_search_empty", "location_id": "room-01", "reason": "empty"}]
    assert session.looted_location_ids == ["room-01"]


def test_cursed_item_applies_both_stats_only_while_equipped():
    character = make_character(1, "Aldren")
    item = InventoryItem(
        id=1, character_id=1, item_type="accessory", target_stat="strength",
        stat_bonus=2, curse_stat="charisma", curse_penalty=-1,
        is_equipped=True,
    )
    character.inventory = [item]

    assert calculate_item_modifier(character, "strength") == 2
    assert calculate_item_modifier(character, "charisma") == -1
    item.is_equipped = False
    assert calculate_item_modifier(character, "strength") == 0
    assert calculate_item_modifier(character, "charisma") == 0


def test_unawarded_amulet_is_removed_from_story():
    narration = (
        "Przeszukuje dymiący kokon. Wygrzebał Amulet Szeptów z Żelaznego Szlaku, "
        "parząc dłonie."
    )
    result = reconcile_loot_narration(
        narration,
        [{"type": "loot_search_empty", "location_id": "room-01", "reason": "empty"}],
        get_default_world_pack(),
    )

    assert "Amulet Szeptów" not in result
    assert "nie przynosi łupu" in result


def test_crafting_requires_three_items_of_the_same_type_in_the_open_window():
    character = make_character(1, "Aldren")
    character.inventory = [
        InventoryItem(id=1, character_id=1, name="Miecz A", item_type="weapon", target_stat="strength", stat_bonus=1),
        InventoryItem(id=2, character_id=1, name="Miecz B", item_type="weapon", target_stat="strength", stat_bonus=1),
        InventoryItem(id=3, character_id=1, name="Miecz C", item_type="weapon", target_stat="strength", stat_bonus=1),
    ]
    session = GameSession(
        id=1,
        room_code="test",
        active_boss_hp=0,
        crafting_available_until_turn=3,
        looted_location_ids=[],
    )
    action_text = "Scalam Miecz A, Miecz B oraz Miecz C w jeden oręż."

    error = validate_special_action(
        action_text,
        character.inventory,
        session,
        3,
        "other",
        False,
        make_map(),
    )

    assert error is None


def test_successful_crafting_consumes_three_items_and_caps_upgrade():
    character = make_character(1, "Aldren")
    character.inventory = [
        InventoryItem(id=1, character_id=1, name="Miecz A", item_type="weapon", target_stat="strength", stat_bonus=1),
        InventoryItem(id=2, character_id=1, name="Miecz B", item_type="weapon", target_stat="strength", stat_bonus=1),
        InventoryItem(id=3, character_id=1, name="Miecz C", item_type="weapon", target_stat="strength", stat_bonus=1),
    ]
    action = PlayerAction(
        id=1,
        turn_id=10,
        character_id=character.id,
        action_text="Scalam Miecz A, Miecz B oraz Miecz C w jeden oręż.",
        outcome_tier="success",
    )
    turn = Turn(id=10, session_id=1, turn_number=3, combat_events=[], actions=[action])
    session = GameSession(
        id=1,
        room_code="test",
        active_boss_hp=0,
        crafting_available_until_turn=3,
        looted_location_ids=[],
    )

    result = resolve_inventory_mechanics(session, turn, [character], make_map())

    assert len(result.new_items) == 1
    assert result.new_items[0].stat_bonus == 2
    assert len(result.consumed_items) == 3
    assert result.events[0]["type"] == "item_crafted"
