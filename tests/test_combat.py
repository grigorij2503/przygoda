from app.combat import (
    add_status,
    build_boss_encounter,
    calculate_attack_damage,
    infer_action_intent,
    make_status,
)
from app.models import Character, InventoryItem, PlayerAction
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
