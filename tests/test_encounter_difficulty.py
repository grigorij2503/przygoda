from app.combat import (
    action_dc,
    build_enemy_encounter,
    estimate_character_damage,
    resolve_boss_turn,
)
from app.models import Character, GameSession, InventoryItem, PlayerAction


def make_character(index: int, *, level: int = 1, strength: int = 2) -> Character:
    character = Character(
        id=index,
        name=f"Bohater {index}",
        level=level,
        strength=strength,
        agility=1,
        intellect=1,
        charisma=0,
        perception=0,
        current_hp=20 + strength * 5,
        max_hp=20 + strength * 5,
        is_alive=True,
        death_state="alive",
        status_effects=[],
    )
    character.inventory = [InventoryItem(
        item_type="weapon",
        target_stat="strength",
        stat_bonus=1,
        damage_power=4,
        is_equipped=True,
    )]
    return character


def test_encounter_uses_hit_odds_and_party_size_without_overloading_solo_player():
    solo = build_enemy_encounter([make_character(1)], "Przeciwnik")
    party = build_enemy_encounter(
        [make_character(index) for index in range(1, 5)], "Przeciwnik"
    )

    assert party["max_hp"] > solo["max_hp"]
    assert solo["telegraph"]["attack_count"] == 1
    assert party["telegraph"]["attack_count"] == 2
    assert solo["telegraph"]["base_damage"] < party["telegraph"]["base_damage"]


def test_estimated_damage_accounts_for_armor_dc_and_equipment():
    character = make_character(1)
    baseline = estimate_character_damage(character, defense_dc=12, armor=1)

    assert baseline > estimate_character_damage(character, defense_dc=16, armor=1)
    assert baseline > estimate_character_damage(character, defense_dc=12, armor=4)
    character.inventory[0].stat_bonus = 3
    assert estimate_character_damage(character, defense_dc=12, armor=1) > baseline


def test_enemy_hits_distinct_targets_and_keeps_its_initial_attack_count():
    characters = [make_character(index) for index in range(1, 5)]
    encounter = build_enemy_encounter(characters, "Przeciwnik")
    session = GameSession(
        current_turn_number=1,
        active_boss_name="Przeciwnik",
        active_boss_hp=encounter["hp"],
        active_boss_max_hp=encounter["max_hp"],
        active_boss_armor=encounter["armor"],
        active_boss_defense_dc=encounter["defense_dc"],
        active_boss_phase=1,
        active_boss_effects=[],
        active_boss_features=encounter["features"],
        active_boss_telegraph=encounter["telegraph"],
    )
    actions = [PlayerAction(character_id=c.id, action_text="Czekam", intent="other") for c in characters]

    events = resolve_boss_turn(session, characters, actions)
    hits = [event for event in events if event["type"] == "boss_attack"]

    assert len(hits) == 2
    assert len({event["target"] for event in hits}) == 2
    assert session.active_boss_telegraph["attack_count"] == 2

    for character in characters[:3]:
        character.is_alive = False
    session.current_turn_number = 2
    remaining_hits = [
        event for event in resolve_boss_turn(session, characters, actions)
        if event["type"] == "boss_attack"
    ]
    assert len(remaining_hits) == 1
    assert remaining_hits[0]["target"] == characters[3].name
    assert session.active_boss_max_hp == encounter["max_hp"]


def test_enemy_response_is_capped_to_current_participating_party_size():
    characters = [make_character(index) for index in range(1, 6)]
    encounter = build_enemy_encounter(characters, "Przeciwnik")
    session = GameSession(
        current_turn_number=1,
        active_boss_name="Przeciwnik",
        active_boss_hp=encounter["hp"],
        active_boss_max_hp=encounter["max_hp"],
        active_boss_phase=1,
        active_boss_effects=[],
        active_boss_features=encounter["features"],
        active_boss_telegraph=encounter["telegraph"],
    )
    characters[3].participation_status = "on_break"
    characters[4].participation_status = "on_break"
    actions = [
        PlayerAction(character_id=character.id, action_text="Czekam", intent="other")
        for character in characters[:3]
    ]

    hits = [
        event for event in resolve_boss_turn(session, characters, actions)
        if event["type"] == "boss_attack"
    ]

    assert encounter["telegraph"]["attack_count"] == 3
    assert len(hits) == 2
    assert len({event["target"] for event in hits}) == 2


def test_boss_attack_event_exposes_defence_breakdown():
    characters = [make_character(index) for index in range(1, 3)]
    encounter = build_enemy_encounter(characters, "Przeciwnik")
    session = GameSession(
        current_turn_number=1,
        active_boss_name="Przeciwnik",
        active_boss_hp=encounter["hp"],
        active_boss_max_hp=encounter["max_hp"],
        active_boss_phase=1,
        active_boss_effects=[],
        active_boss_features=encounter["features"],
        active_boss_telegraph=encounter["telegraph"],
    )
    actions = [
        PlayerAction(
            character_id=characters[0].id,
            action_text="Barykaduję przejście",
            intent="defend",
            outcome_tier="success",
        ),
        PlayerAction(
            character_id=characters[1].id,
            action_text="Czekam",
            intent="other",
            outcome_tier="success",
        ),
    ]

    hit = next(
        event for event in resolve_boss_turn(session, characters, actions)
        if event["type"] == "boss_attack"
    )

    assert hit["base_damage"] == encounter["telegraph"]["base_damage"]
    assert hit["guarded_reduction"] > 0
    assert hit["team_defense_reduction"] > 0
    assert hit["total_reduction"] == hit["guarded_reduction"] + hit["team_defense_reduction"]


def test_noncombat_tiers_scale_but_encounter_dc_keeps_priority():
    session = GameSession(active_boss_hp=None)
    action = PlayerAction(action_text="Badam urządzenie", intent="interact")

    assert action_dc(session, action, challenge_tier="standard", average_level=25)[0] == 12
    assert action_dc(session, action, challenge_tier="hard", average_level=25)[0] == 25
    assert action_dc(session, action, challenge_tier="climactic", average_level=25)[0] == 30

    session.active_boss_hp = 40
    session.active_boss_defense_dc = 14
    attack = PlayerAction(action_text="Atakuję", intent="attack")
    assert action_dc(session, attack, challenge_tier="climactic", average_level=25)[0] == 14
    assert action_dc(session, action, challenge_tier="climactic", average_level=25)[0] == 12
