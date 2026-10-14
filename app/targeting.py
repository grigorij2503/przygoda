"""Resolve an explicitly described character target without a target picker."""

import re
import unicodedata

from app.action_dialogue import action_mechanics_text
from app.models import Character


_ATTACK_VERB = re.compile(
    r"\b(?:atakuj|uderz|rzuc|cisn|strzel|traf|rani|tnij|tne|siek|kop|pchni)\w*\b"
)
_ALLY_WORD = re.compile(r"\b(?:koleg|kolezan|towarzysz|sojusznik|druzynnik)\w*\b")


def _plain(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def infer_character_attack_target(
    action_text: str, actor: Character, characters: list[Character]
) -> tuple[Character | None, str | None]:
    """Only infer a target when an offensive declaration points at a party member."""
    normalized = _plain(action_mechanics_text(action_text))
    attack = _ATTACK_VERB.search(normalized)
    if not attack:
        return None, None
    clause = normalized[attack.end():].split(" a potem ", 1)[0]
    clause = clause.split(" nastepnie ", 1)[0]
    clause = clause.split(" zeby ", 1)[0]
    clause = clause.split(" aby ", 1)[0]
    others = [
        character for character in characters
        if character.id != actor.id and character.is_alive and character.is_participating
    ]
    named = []
    for character in others:
        name = _plain(character.name)
        variants = {name}
        variants.update({name + "a", name + "e", name + "em", name + "owi"})
        if name.endswith("ek") and len(name) > 4:
            variants.add(name[:-2] + "ka")
        if name.endswith("cek") and len(name) > 5:
            variants.add(name[:-3] + "cka")
        if name.endswith("a") and len(name) > 3:
            variants.update({name[:-1] + "e", name[:-1] + "y"})
        if any(re.search(
            rf"(?:^\s*|\b(?:w|na|do|przeciwko)\s+|"
            rf"\b(?:koleg|kolezan|towarzysz|sojusznik)\w*\s+){re.escape(variant)}\b",
            clause,
        ) for variant in variants):
            named.append(character)
    if len(named) > 1:
        return None, "W opisie ataku wskaż jedną postać z drużyny."
    if named:
        return named[0], None
    if re.search(r"\b(?:w|na|do|przeciwko)\s+(?:koleg|kolezan|towarzysz|sojusznik|druzynnik)\w*\b", clause) or (
        _ALLY_WORD.match(clause.strip())
    ):
        if len(others) == 1:
            return others[0], None
        if not others:
            return None, "Brak żywej postaci z drużyny, którą można zaatakować."
        return None, "Wpisz imię atakowanej postaci w opisie akcji."
    return None, None
