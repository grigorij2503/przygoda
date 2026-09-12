import re
import secrets
import unicodedata
from typing import Tuple
from app.inventory import get_effectively_equipped_items
from app.models import Character

_POLISH_CHAR_TRANSLATION = str.maketrans("ąćęłńóśźż", "acelnoszz")

# Reguły korzystają z rdzeni słów, aby obejmować polską odmianę. Waga 4 oznacza
# jawną deklarację cechy lub magii, 3 jednoznaczny sposób wykonania akcji,
# 2 mocny kontekst, a 1 jedynie poszlakę.
ATTRIBUTE_RULES: dict[str, tuple[tuple[str, int], ...]] = {
    "strength": (
        (r"\b(?:sila|sily|sile)\b", 4),
        (r"\b(?:silny\w*|krzep\w*|muskul\w*)\b", 3),
        (r"\b(?:miecz\w*|topor\w*|mlot\w*|maczug\w*|halabard\w*|wloczni\w*)\b", 3),
        (r"\b(?:uderz\w*|cios\w*|tn\w*|cieci\w*|rab\w*|rozbij\w*|zgnie\w*)\b", 2),
        (r"\b(?:wywaz\w*|wylam\w*|pchn\w*|zepchn\w*|podn\w*|dzwig\w*|przesun\w*)\b", 2),
        (r"\b(?:powal\w*|szarz\w*|siluj\w*|kop\w*|chwyt\w*|zapas\w*|piesc\w*|bark\w*)\b", 2),
        (r"\b(?:walka\s+wrecz|wrecz|tarcza\w*|blok\w*|paruj\w*)\b", 2),
    ),
    "agility": (
        (r"\bzrecz\w*\b", 4),
        (r"\b(?:precyz\w*|celn\w*|refleks\w*)\b", 3),
        (r"\b(?:luk\w*|kusz\w*|proca\w*|strzal\w*|strzel\w*|belt\w*)\b", 3),
        (r"\b(?:unik\w*|uskocz\w*|odskocz\w*|przekrad\w*|skrad\w*|ukry\w*)\b", 2),
        (r"\b(?:skocz\w*|wspin\w*|wslizg\w*|czolg\w*|akrobat\w*|balans\w*|uciek\w*)\b", 2),
        (r"\b(?:wytrych\w*|pulapk\w*|krad\w*|kieszon\w*|zwod\w*)\b", 2),
        (r"\b(?:sztylet\w*|noz\w*|rapier\w*|dystans\w*|celuj\w*)\b", 2),
        (r"\b(?:rzuc\w*|szybk\w*|cich\w*|zwinn\w*)\b", 1),
    ),
    "intellect": (
        (r"\b(?:rozum\w*|intelekt\w*|logik\w*)\b", 4),
        (r"\b(?:magi(?:a|i|e|o)?|czar(?!odziej|ownic)\w*|zakle\w*|wyczar\w*|inkant\w*|rytual\w*)\b", 4),
        (r"\bmagiczn\w*\b", 2),
        (r"\b(?:mana\w*|run\w*|zwoj\w*|artefakt\w*|alchemi\w*|eliksir\w*)\b", 3),
        (r"\b(?:nekrom\w*|telepat\w*|iluzj\w*|przyzyw\w*|zaklin\w*|medyt\w*)\b", 3),
        (r"\b(?:kula\s+ognia|ognist\w*\s+kula\w*|blyskawic\w*|telekinez\w*|teleport\w*)\b", 3),
        (r"\b(?:bada\w*|zbada\w*|analiz\w*|rozpozn\w*|rozszyfr\w*|odczyt\w*)\b", 2),
        (r"\b(?:wiedz\w*|przypomn\w*|histori\w*|legend\w*|zagad\w*|deduk\w*)\b", 2),
        (r"\b(?:wykry\w*|wytrop\w*|trop\w*|nasluch\w*|obserw\w*|dostrzeg\w*)\b", 2),
        (r"\b(?:ksieg\w*|bibliotek\w*|map\w*|mechanizm\w*|slad\w*|skup\w*)\b", 1),
    ),
    "charisma": (
        (r"\b(?:charyzm\w*|autorytet\w*|retory\w*)\b", 4),
        (r"\b(?:perswad\w*|przekon\w*|zastrasz\w*|negocj\w*|dyplomac\w*)\b", 3),
        (r"\b(?:blef\w*|oklam\w*|oszuk\w*|uwodz\w*|flirt\w*|urok\w*)\b", 3),
        (r"\b(?:dowodz\w*|rozkaz\w*|zainspir\w*|przemow\w*|motyw\w*)\b", 2),
        (r"\b(?:uspok\w*|pociesz\w*|blag\w*|dyskut\w*|wypyt\w*|targuj\w*|naklon\w*)\b", 2),
        (r"\b(?:krzycz\w*|zawol\w*|spiew\w*|wystep\w*|opowiad\w*)\b", 1),
        (r"\b(?:modlitw\w*|modl\w*|bostw\w*|kaplan\w*)\b", 2),
    ),
}


def _normalize_action_text(action_text: str) -> str:
    normalized = unicodedata.normalize("NFKD", action_text.casefold())
    normalized = normalized.translate(_POLISH_CHAR_TRANSLATION)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def deduce_tested_attribute(action_text: str, character: Character) -> str:
    """
    Dedukuje najbardziej adekwatną statystykę do rzutu na podstawie tekstu akcji gracza.
    Jeżeli akcja nie zawiera wyraźnych słów kluczowych, bierze najwyższą pasującą statystykę postaci.
    """
    cleaned_text = _normalize_action_text(action_text)
    scores = {"strength": 0, "agility": 0, "intellect": 0, "charisma": 0}
    strongest_evidence = {stat: 0 for stat in scores}

    for stat, rules in ATTRIBUTE_RULES.items():
        for pattern, weight in rules:
            if re.search(pattern, cleaned_text):
                scores[stat] += weight
                strongest_evidence[stat] = max(strongest_evidence[stat], weight)

    # Najpierw liczy się najbardziej jednoznaczna przesłanka, potem suma kontekstu.
    # Dzięki temu np. jawne "zaklęcie" nie przegrywa z kilkoma słabszymi
    # określeniami ruchu. Dopiero pełny remis rozstrzyga mocniejsza cecha postaci.
    ranks = {
        stat: (strongest_evidence[stat], scores[stat])
        for stat in scores
    }
    best_rank = max(ranks.values())
    if best_rank > (0, 0):
        candidates = [stat for stat, rank in ranks.items() if rank == best_rank]
        return max(candidates, key=lambda stat: getattr(character, stat, 0))

    # Fallback dla akcji bez rozpoznawalnego kontekstu: najwyższa statystyka postaci.
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
