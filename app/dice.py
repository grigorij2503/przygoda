import re
import secrets
from typing import Tuple
from app.inventory import get_effectively_equipped_items
from app.models import Character

ATTRIBUTE_KEYWORDS = {
    "strength": [
        "atak", "uderz", "miecz", "topór", "młot", "rozbij", "wyważ", "pchnij",
        "zepchnij", "podnieś", "wyłam", "tarcza", "powal", "szarża", "cios",
        "cięcie", "zniszcz", "rąb", "zgnieć", "krzepa", "siła", "wręcz"
    ],
    "agility": [
        "łuk", "strzał", "kusza", "sztylet", "unik", "uskocz", "przekrad", "skrad",
        "skocz", "wspin", "zwin", "ukryj", "uciek", "rzuć", "wytrych", "pułapk",
        "kradzież", "zwód", "wślizg", "dystans", "zręczn"
    ],
    "intellect": [
        "czar", "zaklę", "magia", "ogień", "laska", "księg", "zbadaj", "rozpozn",
        "analiz", "wiedz", "przypomn", "rozszyfr", "zwoj", "skupien", "medytac",
        "wykryj", "runa", "alchemi", "rozum", "inteligencj", "wytrop"
    ],
    "charisma": [
        "perswaz", "przekon", "zastrasz", "negocj", "blef", "okłam", "krzycz",
        "dowodzen", "zainspir", "modlitw", "bóstw", "urok", "dyplomac", "uspokój",
        "zawoł", "charyzm", "błag", "dyskusj"
    ]
}

def deduce_tested_attribute(action_text: str, character: Character) -> str:
    """
    Dedukuje najbardziej adekwatną statystykę do rzutu na podstawie tekstu akcji gracza.
    Jeżeli akcja nie zawiera wyraźnych słów kluczowych, bierze najwyższą pasującą statystykę postaci.
    """
    cleaned_text = action_text.lower()
    scores = {"strength": 0, "agility": 0, "intellect": 0, "charisma": 0}

    for stat, keywords in ATTRIBUTE_KEYWORDS.items():
        for kw in keywords:
            if kw in cleaned_text:
                scores[stat] += 1

    # Sprawdź statystykę z największą liczbą dopasowań słów kluczowych
    best_stat = max(scores, key=scores.get)
    if scores[best_stat] > 0:
        return best_stat

    # Fallback: zależnie od klasy postaci lub najwyższej statystyki postaci
    char_stats = {
        "strength": character.strength,
        "agility": character.agility,
        "intellect": character.intellect,
        "charisma": character.charisma
    }
    return max(char_stats, key=char_stats.get)

def calculate_item_modifier(character: Character, tested_stat: str) -> int:
    """
    Zlicza bonusy z aktualnie wyekwipowanych przedmiotów gracza pasujące do testowanego atrybutu.
    """
    modifier = 0
    for item in get_effectively_equipped_items(character.inventory):
        if item.target_stat == tested_stat or item.target_stat == "all":
            modifier += item.stat_bonus
    return modifier

def resolve_dice_roll(
    action_text: str,
    character: Character,
    dc: int = 12,
    tested_stat_override: str | None = None,
    roll_modifier: int = 0,
) -> Tuple[str, int, int, int, int, str]:
    """
    Wykonuje deterministyczny, kryptograficznie bezpieczny rzut kością k20
    oraz oblicza całkowity wynik z uwzględnieniem statystyk i ekwipunku.

    Zwraca krotkę:
    (tested_stat, dice_roll_raw, stat_modifier, item_modifier, dice_total, outcome_tier)
    """
    tested_stat = (
        tested_stat_override
        if tested_stat_override in {"strength", "agility", "intellect", "charisma"}
        else deduce_tested_attribute(action_text, character)
    )

    # Wartość cechy postaci
    stat_val = getattr(character, tested_stat, 0)

    # Bonus z ekwipunku
    item_mod = calculate_item_modifier(character, tested_stat)

    # Rzut kością k20 (1-20)
    dice_roll_raw = secrets.randbelow(20) + 1

    dice_total = dice_roll_raw + stat_val + item_mod + roll_modifier

    # Klasyfikacja wyniku
    if dice_roll_raw == 20:
        outcome_tier = "critical_success"
    elif dice_roll_raw == 1:
        outcome_tier = "critical_failure"
    elif dice_total >= dc:
        outcome_tier = "success"
    elif dice_total >= dc - 2:
        outcome_tier = "partial_success"
    else:
        outcome_tier = "failure"

    return tested_stat, dice_roll_raw, stat_val, item_mod, dice_total, outcome_tier
