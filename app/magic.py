"""Pack-driven abilities with temporary legacy ``magic_*`` adapters."""

import re
import unicodedata
from typing import Any

from app.worlds.models import AbilityDefinition, WorldClassDefinition, WorldPack
from app.worlds.registry import WORLD_PACK_REGISTRY, get_default_world_pack


def normalize_ability_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", (value or "").casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def _resolve_class(pack: WorldPack, class_id_or_name: str | None) -> WorldClassDefinition:
    if not class_id_or_name:
        raise LookupError(f"missing class id in world pack {pack.key}")
    return WORLD_PACK_REGISTRY.get_class(pack, class_id_or_name)


def _legacy_class_id(character_class: str) -> str:
    return WORLD_PACK_REGISTRY.resolve_class(
        get_default_world_pack(), character_class
    ).id


def _ability_payload(ability: AbilityDefinition) -> dict[str, Any]:
    payload = ability.model_dump(mode="python")
    payload["mechanic_params"] = {
        parameter.key: parameter.value for parameter in ability.mechanic_params
    }
    return payload


def get_ability(
    pack: WorldPack,
    class_id: str | None,
    ability_id: str | None,
) -> dict[str, Any] | None:
    if not ability_id:
        return None
    class_definition = _resolve_class(pack, class_id)
    book = class_definition.ability_book
    if not book or ability_id not in book.ability_ids:
        return None
    ability = next((item for item in pack.abilities if item.id == ability_id), None)
    return _ability_payload(ability) if ability else None


def get_ability_casting_stat(pack: WorldPack, class_id: str) -> str | None:
    book = _resolve_class(pack, class_id).ability_book
    return book.casting_stat if book else None


def get_ability_book(
    pack: WorldPack,
    class_id: str,
    level: int,
) -> dict[str, Any] | None:
    class_definition = _resolve_class(pack, class_id)
    book = class_definition.ability_book
    if not book:
        return None
    abilities_by_id = {ability.id: ability for ability in pack.abilities}
    return {
        "kind": book.kind,
        "title": book.title,
        "icon": book.icon,
        "resource_label": book.resource_label,
        "casting_stat": book.casting_stat,
        "abilities": [
            {
                **_ability_payload(abilities_by_id[ability_id]),
                "unlocked": level >= abilities_by_id[ability_id].required_level,
            }
            for ability_id in book.ability_ids
        ],
    }


def get_unlocked_abilities(
    pack: WorldPack,
    class_id: str,
    level: int,
) -> list[dict[str, Any]]:
    book = get_ability_book(pack, class_id, level)
    if not book:
        return []
    return [
        {key: value for key, value in ability.items() if key != "action_text"}
        for ability in book["abilities"]
        if ability["unlocked"]
    ]


def find_ability_in_text(
    pack: WorldPack,
    action_text: str,
) -> tuple[str, dict[str, Any]] | None:
    normalized = normalize_ability_text(action_text)
    if not normalized:
        return None
    abilities_by_id = {ability.id: ability for ability in pack.abilities}
    for class_definition in pack.classes:
        book = class_definition.ability_book
        if not book:
            continue
        for ability_id in book.ability_ids:
            ability = abilities_by_id[ability_id]
            phrases = (ability.name, *ability.aliases)
            if any(
                normalize_ability_text(phrase) in normalized
                for phrase in phrases
                if normalize_ability_text(phrase)
            ):
                return class_definition.id, _ability_payload(ability)
    return None


def looks_like_ability_action(pack: WorldPack, action_text: str) -> bool:
    normalized = normalize_ability_text(action_text)
    markers = (
        marker
        for class_definition in pack.classes
        if class_definition.ability_book
        for marker in class_definition.ability_book.action_markers
    )
    return bool(
        find_ability_in_text(pack, normalized)
        or any(normalize_ability_text(marker) in normalized for marker in markers)
    )


def validate_ability_action(
    pack: WorldPack,
    class_id: str,
    level: int,
    action_text: str,
    ability_id: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    class_definition = _resolve_class(pack, class_id)
    book = class_definition.ability_book
    if ability_id:
        if not book:
            return None, "Ta klasa nie ma dostępu do księgi zdolności."
        ability = get_ability(pack, class_definition.id, ability_id)
        if not ability:
            return None, "Wybrana zdolność nie należy do księgi tej postaci."
        if level < ability["required_level"]:
            return None, f"„{ability['name']}” wymaga poziomu {ability['required_level']}."
        return ability, None

    matched = find_ability_in_text(pack, action_text)
    if matched:
        matched_class_id, ability = matched
        if not book:
            return None, "Ta klasa nie ma dostępu do rozpoznanej zdolności."
        if matched_class_id != class_definition.id:
            return None, "Rozpoznana zdolność nie należy do księgi tej postaci."
        if level < ability["required_level"]:
            return None, f"„{ability['name']}” wymaga poziomu {ability['required_level']}."
        return ability, None

    if looks_like_ability_action(pack, action_text):
        if book:
            return None, (
                f"Akcje specjalne muszą pochodzić z widoku „{book.title}”. "
                "Wybierz dostępną zdolność."
            )
        return None, "Ta klasa nie ma dostępu do deklarowanej zdolności specjalnej."
    return None, None


# Adaptery kompatybilności dla dark_fantasy@1. Nowy runtime korzysta z funkcji
# powyżej i zawsze przekazuje pakiet przypięty do kampanii.
def normalize_magic_class(character_class: str) -> str | None:
    class_definition = WORLD_PACK_REGISTRY.resolve_class(
        get_default_world_pack(), character_class
    )
    return class_definition.id if class_definition.ability_book else None


def get_magic_ability(character_class: str, ability_id: str | None) -> dict[str, Any] | None:
    return get_ability(get_default_world_pack(), _legacy_class_id(character_class), ability_id)


def get_magic_casting_stat(character_class: str) -> str | None:
    return get_ability_casting_stat(get_default_world_pack(), _legacy_class_id(character_class))


def find_magic_ability_in_text(action_text: str) -> tuple[str, dict[str, Any]] | None:
    return find_ability_in_text(get_default_world_pack(), action_text)


def get_magic_book(character_class: str, level: int) -> dict[str, Any] | None:
    return get_ability_book(get_default_world_pack(), _legacy_class_id(character_class), level)


def get_unlocked_magic_abilities(character_class: str, level: int) -> list[dict[str, Any]]:
    return get_unlocked_abilities(get_default_world_pack(), _legacy_class_id(character_class), level)


def looks_like_magic_action(action_text: str) -> bool:
    return looks_like_ability_action(get_default_world_pack(), action_text)


def validate_magic_action(
    character_class: str,
    level: int,
    action_text: str,
    ability_id: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    return validate_ability_action(
        get_default_world_pack(),
        _legacy_class_id(character_class),
        level,
        action_text,
        ability_id,
    )
