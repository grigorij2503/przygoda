from app.combat import (
    add_status,
    build_boss_encounter,
    calculate_attack_damage,
    infer_action_intent,
    is_retreat_action,
    make_status,
    resolve_boss_turn,
    resolve_status_turn,
    set_character_downed,
)
from app.models import Character, GameSession, InventoryItem, PlayerAction
from app.main import validate_action_item_claim


def make_level_four_character(name: str) -> Character:
    character = Character(
        name=name,
        player_name=name,
        level=4,
        strength=4,
        agility=1,
        intellect=1,
        charisma=0,
        current_hp=40,
        max_hp=40,
        is_alive=True,
    )
    character.inventory = [
        InventoryItem(
            name="Miecz",
            item_type="weapon",
            target_stat="strength",
            stat_bonus=1,
            damage_power=4,
            is_equipped=True,
        )
    ]
    return character


def test_defensive_declaration_is_not_treated_as_attack():
    intent = infer_action_intent("Blokuję atak bossa tarczą i osłaniam sojusznika")

    assert intent == "defend"


def test_escape_declaration_is_a_defensive_retreat():
    text = "Uciekamy i zrywamy kontakt z bossem"

    assert infer_action_intent(text) == "defend"
    assert is_retreat_action(text) is True
    assert is_retreat_action("Nie uciekamy, walczymy dalej") is False


def test_coordinated_retreat_ends_encounter_without_enemy_response():
    characters = [make_level_four_character("Arven"), make_level_four_character("Lira")]
    for index, character in enumerate(characters, start=1):
        character.id = index
    session = GameSession(
        active_boss_name="Purpurowa Bestia",
        active_boss_title="Bestia z otchłani",
        active_boss_hp=40,
        active_boss_max_hp=80,
        active_boss_armor=2,
        active_boss_defense_dc=13,
        active_boss_phase=2,
        active_boss_effects=[],
        active_boss_features=[],
        active_boss_telegraph={"base_damage": 10, "attack_count": 1},
    )
    actions = [
        PlayerAction(
            character_id=character.id,
            action_text="Wycofuję się i zrywam kontakt.",
            intent="defend",
            outcome_tier="failure",
        )
        for character in characters
    ]

    events = resolve_boss_turn(session, characters, actions)

    assert session.active_boss_name is None
    assert session.active_boss_hp is None
    assert any(event["type"] == "party_retreat" for event in events)
    assert not any(event["type"] == "boss_attack" for event in events)
    assert [character.current_hp for character in characters] == [40, 40]


def test_barricading_a_passage_is_treated_as_defence():
    intent = infer_action_intent(
        "Zabarykadowanie wąskiego przejścia żelaznymi kratami i gruzem, by zyskać czas."
    )

    assert intent == "defend"


def test_offensive_action_is_not_changed_by_defence_mentioned_in_proverb():
    intent = infer_action_intent(
        "Boo mówi, że najlepszą obroną jest atak! Krzyknę i wyprowadzę kolejne zamaszyste cięcia."
    )

    assert intent == "attack"


def test_boss_health_scales_above_legacy_value_for_level_four_party():
    party = [make_level_four_character(f"Bohater {index}") for index in range(4)]

    encounter = build_boss_encounter(party, "Demon ognia")

    assert encounter["max_hp"] > 80
    assert encounter["phase"] == 1
    assert len(encounter["features"]) == 3


def test_damage_uses_weapon_stat_level_roll_and_armor(monkeypatch):
    character = make_level_four_character("Wojownik")
    action = PlayerAction(
        action_text="Atakuję mieczem",
        tested_stat="strength",
        stat_modifier=4,
        outcome_tier="success",
    )
    monkeypatch.setattr("app.combat.secrets.randbelow", lambda _: 3)

    damage, damage_roll, base_damage, reduction = calculate_attack_damage(
        character,
        action,
        boss_armor=2,
        boss_effects=[],
    )

    assert damage_roll == 4
    assert base_damage == 14
    assert reduction == 2
    assert damage == 12


def test_reapplying_status_extends_duration_and_stacks_potency():
    effects = [make_status("burning", 1, 1, "Mag")]

    updated = add_status(effects, make_status("burning", 3, 2, "Mag"))

    assert len(updated) == 1
    assert updated[0]["turns_remaining"] == 3
    assert updated[0]["potency"] == 3


def test_status_damage_event_has_a_player_facing_label_and_icon():
    character = make_level_four_character("Poparzony")
    character.status_effects = [make_status("burning", 2, 1, "Smok")]
    action = PlayerAction(character_id=1, action_text="Czekam", intent="other")
    character.id = 1

    events = resolve_status_turn([character], [action])

    status_event = next(event for event in events if event["type"] == "status_damage")
    assert status_event["damage"] == 2
    assert status_event["effect_label"] == "Poparzony"
    assert status_event["effect_icon"] == "🔥"


def test_entering_agony_clears_all_status_effects():
    character = make_level_four_character("Poparzony")
    character.status_effects = [
        make_status("burning", 2, 1, "Smok"),
        make_status("guarded", 2, 2, "Kapłan"),
    ]

    set_character_downed(character)

    assert character.death_state == "downed"
    assert character.status_effects == []


def test_lethal_status_damage_does_not_restore_effect_after_entering_agony():
    character = make_level_four_character("Poparzony")
    character.id = 1
    character.current_hp = 2
    character.status_effects = [
        make_status("burning", 3, 1, "Smok"),
        make_status("frozen", 3, 1, "Mróz"),
    ]
    action = PlayerAction(character_id=1, action_text="Czekam", intent="other")

    resolve_status_turn([character], [action])

    assert character.current_hp == 0
    assert character.death_state == "downed"
    assert character.status_effects == []


def test_death_clears_legacy_status_effects_from_downed_character():
    character = make_level_four_character("Poparzony")
    character.id = 1
    character.current_hp = 0
    character.is_alive = False
    character.death_state = "downed"
    character.death_failures = 2
    character.status_effects = [make_status("burning", 3, 1, "Smok")]

    events = resolve_status_turn([character], [])

    assert character.death_state == "dead"
    assert character.status_effects == []
    assert any(event["type"] == "character_died" for event in events)


def test_boss_status_damage_keeps_the_character_source_for_ui_attribution():
    character = make_level_four_character("Arven")
    character.id = 1
    action = PlayerAction(
        character_id=character.id,
        action_text="Czekam na ruch przeciwnika",
        intent="other",
        outcome_tier="success",
    )
    session = GameSession(
        current_turn_number=1,
        active_boss_name="Żarłoczny cień",
        active_boss_hp=20,
        active_boss_max_hp=20,
        active_boss_armor=0,
        active_boss_defense_dc=12,
        active_boss_phase=1,
        active_boss_effects=[make_status("burning", 2, 1, character.name)],
        active_boss_features=[],
        active_boss_telegraph={"base_damage": 1, "attack_count": 1},
    )

    events = resolve_boss_turn(session, [character], [action])

    status_event = next(
        event for event in events
        if event["type"] == "status_damage" and event["target"] == "Żarłoczny cień"
    )
    assert status_event["source"] == character.name


def test_extinguishing_fire_is_a_defensive_action():
    assert infer_action_intent(
        "Zaczynam się tarzać po ziemi, żeby ugasić płomienie na pancerzu"
    ) == "defend"


def test_successful_extinguishing_removes_burning_before_it_deals_damage():
    character = make_level_four_character("Minsc i Boo")
    character.id = 1
    character.status_effects = [make_status("burning", 3, 2, "Rozdarcie areny")]
    action = PlayerAction(
        character_id=1,
        action_text="Tarzam się po ziemi, żeby ugasić płomienie",
        intent="defend",
        outcome_tier="success",
    )

    events = resolve_status_turn([character], [action])

    assert character.status_effects == []
    assert action.hp_delta in (None, 0)
    assert any(event["type"] == "status_removed" for event in events)
    assert not any(event["type"] == "status_damage" for event in events)


def test_failed_extinguishing_keeps_burning_and_applies_its_damage():
    character = make_level_four_character("Minsc i Boo")
    character.id = 1
    character.status_effects = [make_status("burning", 3, 1, "Rozdarcie areny")]
    action = PlayerAction(
        character_id=1,
        action_text="Próbuję ugasić płomienie",
        intent="defend",
        outcome_tier="failure",
    )

    events = resolve_status_turn([character], [action])

    assert character.status_effects[0]["type"] == "burning"
    assert action.hp_delta == -2
    assert any(event["type"] == "status_relief_failed" for event in events)
    assert any(event["type"] == "status_damage" for event in events)


def test_action_cannot_use_a_bow_missing_from_inventory():
    inventory = [
        InventoryItem(
            name="Miecz",
            item_type="weapon",
            target_stat="strength",
            is_equipped=True,
        )
    ]

    error = validate_action_item_claim("Atakuję z dystansu łukiem", inventory)

    assert error is not None
    assert "Łuk" in error


def test_action_cannot_use_a_bow_from_backpack():
    inventory = [
        InventoryItem(
            name="Łuk myśliwski",
            item_type="weapon",
            target_stat="agility",
            is_equipped=False,
        )
    ]

    error = validate_action_item_claim("Celuję i strzelam z łuku", inventory)

    assert error is not None
    assert "aktywnym slocie" in error
