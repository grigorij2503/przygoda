from app.combat import infer_action_intent, make_status, resolve_status_turn
from app.models import Character, PlayerAction
from app.targeting import infer_character_attack_target


def make_character(character_id: int, name: str, hp: int = 25) -> Character:
    return Character(
        id=character_id, session_id=1, name=name, player_name=name,
        is_alive=True, death_state="alive", current_hp=hp, max_hp=25,
        strength=2, agility=1, intellect=2, charisma=1, perception=0,
        level=1, status_effects=[],
    )


def test_written_party_target_is_inferred_without_target_picker():
    actor = make_character(1, "Mag")
    target = make_character(2, "Piotr")
    bystander = make_character(3, "Ala")

    assert infer_action_intent("Rzucam kamień w Piotra") == "attack"
    chosen, error = infer_character_attack_target(
        "Rzucam kamień w Piotra", actor, [actor, target, bystander]
    )
    assert chosen is target and error is None

    chosen, error = infer_character_attack_target(
        "Rzucam kamień w kolegę", actor, [actor, target, bystander]
    )
    assert chosen is None and "imię" in error


def test_successful_character_attack_changes_target_hp_and_own_summary():
    actor = make_character(1, "Mag")
    target = make_character(2, "Piotr")
    attack = PlayerAction(
        character_id=1, action_text="Rzucam kamień w Piotra", intent="attack",
        target_ref="2", outcome_tier="success", stat_modifier=2,
    )
    target_action = PlayerAction(character_id=2, action_text="Czekam", intent="other")

    events = resolve_status_turn([actor, target], [attack, target_action])

    assert any(event["type"] == "character_attack" and event["target"] == "Piotr" for event in events)
    assert attack.damage_dealt > 0
    assert target.current_hp == 25 - attack.damage_dealt
    assert target_action.hp_delta == -attack.damage_dealt
    assert attack.hp_delta in (None, 0)


def test_healing_can_target_caster():
    caster = make_character(1, "Czarodziej", hp=10)
    action = PlayerAction(
        character_id=1, action_text="Leczę siebie", intent="support",
        target_ref="1", outcome_tier="success",
    )

    events = resolve_status_turn([caster], [action])

    assert caster.current_hp > 10
    assert any(event["type"] == "support" and event["target"] == "Czarodziej" for event in events)


def test_non_healing_support_grants_protection_instead_of_restoring_hp():
    actor = make_character(1, "Bard")
    target = make_character(2, "Piotr", hp=10)
    action = PlayerAction(
        character_id=1,
        action_text="Odwracam uwagę przeciwnika, żeby osłonić Piotra",
        intent="support",
        target_ref="2",
        outcome_tier="success",
    )

    events = resolve_status_turn([actor, target], [action])

    assert target.current_hp == 10
    assert any(effect["type"] == "guarded" for effect in target.status_effects)
    assert any(event["type"] == "support_guard" for event in events)
    assert not any(event["type"] == "support" for event in events)


def test_basic_support_stabilizes_downed_character_without_restoring_hp():
    actor = make_character(1, "Minsc")
    target = make_character(2, "Markello", hp=0)
    target.is_alive = False
    target.death_state = "downed"
    target.death_failures = 2
    action = PlayerAction(
        character_id=1,
        action_text="Korzystam z wiedzy Boo, by pomóc Markello",
        intent="support",
        target_ref="2",
        outcome_tier="critical_success",
    )

    events = resolve_status_turn([actor, target], [action])

    assert target.current_hp == 0
    assert target.death_state == "stable"
    assert target.death_failures == 0
    assert target.is_alive is False
    assert any(event["type"] == "stabilized" and event["target"] == "Markello" for event in events)
    assert not any(event["type"] in {"support_failed", "revived"} for event in events)


def test_resurrection_does_not_restore_status_effects_left_on_dead_character():
    cleric = make_character(1, "Kapłan")
    cleric.class_id = "cleric"
    cleric.level = 7
    target = make_character(2, "Piotr", hp=0)
    target.is_alive = False
    target.death_state = "dead"
    target.death_failures = 3
    target.status_effects = [make_status("burning", 3, 1, "Smok")]
    action = PlayerAction(
        character_id=1,
        action_text="Wskrzeszam Piotra",
        intent="support",
        target_ref="2",
        outcome_tier="success",
        ability_id="resurrection",
    )

    events = resolve_status_turn([cleric, target], [action])

    assert target.death_state == "alive"
    assert target.current_hp > 0
    assert target.status_effects == []
    assert any(event["type"] == "resurrection" for event in events)
