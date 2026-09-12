from app.loot import resolve_inventory_mechanics, validate_special_action
from app.models import CampaignMap, Character, GameSession, InventoryItem, PlayerAction, Turn


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


def test_boss_drops_one_shared_item_and_opens_next_turn_crafting():
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
    assert session.crafting_available_until_turn == 5


def test_location_can_produce_only_one_shared_loot_award():
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
    assert first.new_items[0].character_id == recipient.id
    assert second.new_items == []
    assert session.looted_location_ids == ["room-01"]


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
