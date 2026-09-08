import pytest
from app.models import Character, InventoryItem
from app.dice import deduce_tested_attribute, calculate_item_modifier, resolve_dice_roll

def test_deduce_tested_attribute():
    char = Character(
        id=1,
        player_name="Piotr",
        name="Thorgal",
        character_class="Wojownik",
        strength=3,
        agility=1,
        intellect=0,
        charisma=1
    )

    # Test słów kluczowych Siły
    action_str = "Biorę oburęczny miecz i uderzam orka z całej siły, próbując go powalić."
    assert deduce_tested_attribute(action_str, char) == "strength"

    # Test słów kluczowych Zręczności
    action_agi = "Napinam łuk i oddaję cichy strzał z ukrycia, po czym robię szybki unik."
    assert deduce_tested_attribute(action_agi, char) == "agility"

    # Test słów kluczowych Rozumu
    action_int = "Koncentruję się, rzucam zaklęcie kuli ognia i badam magiczne runy na ścianie."
    assert deduce_tested_attribute(action_int, char) == "intellect"

    # Test słów kluczowych Charyzmy
    action_cha = "Krzyczę donośnym głosem, próbując zastraszyć strażników i nakłonić ich do negocjacji."
    assert deduce_tested_attribute(action_cha, char) == "charisma"

def test_calculate_item_modifier():
    char = Character(
        id=1,
        player_name="Anna",
        name="Lyanna",
        character_class="Łowczyni",
        strength=1,
        agility=3,
        intellect=1,
        charisma=0
    )
    item1 = InventoryItem(id=1, character_id=1, name="Długi Łuk", target_stat="agility", stat_bonus=2, is_equipped=True)
    item2 = InventoryItem(id=2, character_id=1, name="Sztylet", target_stat="agility", stat_bonus=1, is_equipped=False)
    item3 = InventoryItem(id=3, character_id=1, name="Amulet Siły", target_stat="strength", stat_bonus=1, is_equipped=True)

    char.inventory = [item1, item2, item3]

    # Dla agility tylko item1 jest założony
    assert calculate_item_modifier(char, "agility") == 2
    # Dla strength tylko item3 jest założony
    assert calculate_item_modifier(char, "strength") == 1
    # Dla intellect brak
    assert calculate_item_modifier(char, "intellect") == 0

def test_resolve_dice_roll():
    char = Character(
        id=1,
        player_name="Marek",
        name="Gimli",
        character_class="Wojownik",
        strength=2,
        agility=0,
        intellect=0,
        charisma=0
    )
    char.inventory = [
        InventoryItem(id=1, character_id=1, name="Topór", target_stat="strength", stat_bonus=1, is_equipped=True)
    ]

    action = "Rozbijam toporem drewnianą skrzynię."
    stat, d20_raw, stat_mod, item_mod, total, outcome_tier = resolve_dice_roll(action, char, dc=12)

    assert stat == "strength"
    assert 1 <= d20_raw <= 20
    assert stat_mod == 2
    assert item_mod == 1
    assert total == d20_raw + stat_mod + item_mod
    assert outcome_tier in ["critical_success", "success", "partial_success", "failure", "critical_failure"]
