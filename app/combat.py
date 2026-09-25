import math
import re
import secrets
import unicodedata
from typing import Iterable

from app.inventory import get_effectively_equipped_items
from app.dice import calculate_item_modifier_details
from app.magic import get_ability
from app.models import Character, GameSession, InventoryItem, PlayerAction
from app.worlds.models import WorldPack
from app.worlds.registry import get_default_world_pack


INTENT_RULES: dict[str, tuple[tuple[str, int, str], ...]] = {
    "attack": (
        (r"\b(?:atakuj|walcz|nacier|szarz|uderz|tne|tnij|siek|strzel|wystrzel|rani|zabij|dobij)\w*\b", 5, "bezpośrednia czynność ofensywna"),
        (r"\brzuc\w*\s+(?:kamien|kamyk|cegl|pocisk|noz|granat)\w*\b", 5, "rzut przedmiotem w cel"),
        (r"\bwyprowadz\w*\s+(?:kolejn\w*\s+|zamaszyst\w*\s+)*(?:cios|cieci|atak)\w*\b", 5, "wyprowadzany cios lub cięcie"),
        (r"\b(?:cios|cieci|strzal|pocisk)\w*\b", 3, "opis ciosu lub pocisku"),
        (r"\b(?:atak|natarci|ofensyw)\w*\b", 1, "wzmianka o ataku"),
    ),
    "defend": (
        (r"\b(?:ugas|gasz|zgasz|stlum|zdusz)\w*\b", 5, "usunięcie płomieni lub szkodliwego efektu"),
        (r"\btarz\w*\b.{0,60}\b(?:ogien|plomien|poz[a-z]*r)\w*\b", 5, "gaszenie płomieni ruchem obronnym"),
        (r"\b(?:broni|blokuj|paruj|unikam|uskakuj|odskakuj|oslaniam|zaslaniam|chronie|cofam|wycof|uciek)\w*\b", 5, "bezpośrednia czynność obronna"),
        (r"\b(?:uciec|uciecz\w*|odwrot\w*)\b", 5, "próba odwrotu"),
        (r"\b(?:barykad|zabarykad)\w*\b", 5, "wzniesienie barykady lub zamknięcie przejścia"),
        (r"\b(?:przyjm|zajm)\w*\s+(?:bezpieczn\w*\s+|tward\w*\s+)?pozycj\w*\s+obron\w*\b", 4, "przyjęcie pozycji obronnej"),
        (r"\b(?:tarc|blok|parad|unik|oslona|obronn)\w*\b", 3, "obronny sposób działania"),
        (r"\b(?:obrona|obrony|obronie|obrona)\b", 1, "wzmianka o obronie"),
    ),
    "interact": (
        (r"\b(?:bada|zbada|analiz|rozpozn|przeszuk|urucham|otwier|otworz|rozszyfr|manipul)\w*\b", 5, "badanie lub użycie otoczenia"),
        (r"\b(?:niszcze|przewracam|przesuwam)\w*\s+(?:filar|mechanizm|pieczec|element|obiekt|drzwi)\w*\b", 4, "zmiana elementu otoczenia"),
        (r"\b(?:mechanizm|pieczec|filar|run|arena|otoczen)\w*\b", 2, "odwołanie do otoczenia"),
    ),
    "support": (
        (r"\b(?:wspier|pomag|lecz|uzdraw|opatru|stabiliz|oczyszcz)\w*\b", 5, "bezpośrednia pomoc sojusznikowi"),
        (r"\b(?:odwracam\s+uwage|wkraczam\s+miedzy)\b.{0,80}\b(?:sojusz|druzyn|rann)\w*\b", 5, "działanie tworzące przewagę dla sojusznika"),
        (r"\b(?:wspier|pomoc|leczen|uzdrow|opatrun|antidot)\w*\b", 2, "opis wsparcia"),
    ),
}

RETREAT_PATTERN = re.compile(
    r"\b(?:uciek\w*|uciec|uciecz\w*|wycof\w*|odwrot\w*|cofam(?:y)?\s+sie|zryw\w*\s+kontakt\w*)\b"
)
RETREAT_NEGATION_PATTERN = re.compile(
    r"\b(?:nie|bez)\s+(?:uciek\w*|uciecz\w*|wycof\w*|odwrot\w*)\b"
)

STATUS_CATALOG = {
    status.id: status.model_dump(mode="python")
    for status in get_default_world_pack().status_presentations
}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", (value or "").casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())


def is_retreat_action(action_text: str) -> bool:
    """Recognize an explicit decision to leave an encounter, not a passing mention."""
    normalized = normalize_text(action_text)
    return bool(RETREAT_PATTERN.search(normalized)) and not RETREAT_NEGATION_PATTERN.search(normalized)


def clear_active_enemy(session: GameSession) -> None:
    session.active_boss_name = None
    session.active_boss_title = None
    session.active_boss_hp = None
    session.active_boss_max_hp = None
    session.active_boss_armor = 0
    session.active_boss_defense_dc = 12
    session.active_boss_phase = 1
    session.active_boss_effects = []
    session.active_boss_features = []
    session.active_boss_telegraph = None


def infer_action_intent_details(
    action_text: str,
    explicit_intent: str | None = None,
) -> dict[str, str | float]:
    """Rozpoznaje dominujący zamiar, nadając pierwszeństwo wykonywanej czynności."""
    if explicit_intent in {"attack", "defend", "interact", "support", "other"}:
        return {
            "intent": explicit_intent,
            "confidence": 1.0,
            "reason": "korekta gracza lub reguła wybranej zdolności",
        }

    normalized = normalize_text(action_text)
    scores = {intent: 0 for intent in INTENT_RULES}
    strongest_matches: dict[str, tuple[int, int, str] | None] = {
        intent: None for intent in INTENT_RULES
    }

    for intent, rules in INTENT_RULES.items():
        for pattern, weight, reason in rules:
            match = re.search(pattern, normalized)
            if not match:
                continue
            scores[intent] += weight
            candidate = (weight, -match.start(), reason)
            current = strongest_matches[intent]
            if current is None or candidate > current:
                strongest_matches[intent] = candidate

    top_score = max(scores.values(), default=0)
    if top_score == 0:
        return {
            "intent": "other",
            "confidence": 0.25,
            "reason": "brak jednoznacznej czynności w opisie",
        }

    candidates = [intent for intent, score in scores.items() if score == top_score]
    if len(candidates) > 1:
        candidates.sort(
            key=lambda intent: strongest_matches[intent] or (0, 0, ""),
            reverse=True,
        )
    selected = candidates[0]
    runner_up = max((score for intent, score in scores.items() if intent != selected), default=0)
    margin = top_score - runner_up
    confidence = 0.92 if top_score >= 5 and margin >= 3 else 0.76 if top_score >= 3 and margin >= 1 else 0.55
    match = strongest_matches[selected]
    return {
        "intent": selected,
        "confidence": confidence,
        "reason": match[2] if match else "najsilniejszy kontekst zdania",
    }


def make_status(
    effect_type: str,
    turns: int,
    potency: int = 1,
    source: str = "",
    world_pack: WorldPack | None = None,
) -> dict:
    definitions = (
        {
            status.id: status.model_dump(mode="python")
            for status in world_pack.status_presentations
        }
        if world_pack else STATUS_CATALOG
    )
    definition = definitions[effect_type]
    return {
        "type": effect_type,
        "label": definition["label"],
        "icon": definition["icon"],
        "description": definition["description"],
        "tone": definition["tone"],
        "turns_remaining": turns,
        "potency": potency,
        "source": source,
    }


def status_list(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [dict(effect) for effect in value if isinstance(effect, dict) and effect.get("type")]


def add_status(effects: list[dict], new_effect: dict) -> list[dict]:
    updated = status_list(effects)
    existing = next((effect for effect in updated if effect["type"] == new_effect["type"]), None)
    if existing:
        existing["turns_remaining"] = max(
            int(existing.get("turns_remaining", 0)),
            int(new_effect.get("turns_remaining", 0)),
        )
        existing["potency"] = min(
            5,
            int(existing.get("potency", 1)) + int(new_effect.get("potency", 1)),
        )
        existing["source"] = new_effect.get("source", existing.get("source", ""))
        return updated
    updated.append(new_effect)
    return updated


def has_status(effects: Iterable[dict], effect_type: str) -> bool:
    return any(effect.get("type") == effect_type for effect in effects)


def consume_status(effects: list[dict], effect_type: str) -> list[dict]:
    return [effect for effect in status_list(effects) if effect.get("type") != effect_type]


STATUS_RELIEF_PATTERNS: dict[str, tuple[str, ...]] = {
    "burning": (
        r"\b(?:ugas|gasz|zgasz|stlum|zdusz)\w*\b",
        r"\btarz\w*\b.{0,60}\b(?:ogien|plomien|pozar)\w*\b",
    ),
    "frozen": (
        r"\b(?:rozbij|skrusz|zrzuc|uwolni)\w*\b.{0,60}\b(?:lod|szron)\w*\b",
    ),
}


def infer_status_relief_type(action_text: str) -> str | None:
    """Rozpoznaje jawnie zadeklarowaną próbę usunięcia własnego efektu."""
    normalized = normalize_text(action_text)
    for effect_type, patterns in STATUS_RELIEF_PATTERNS.items():
        if any(re.search(pattern, normalized) for pattern in patterns):
            return effect_type
    return None


def _resolve_status_relief_action(
    character: Character,
    action: PlayerAction,
    events: list[dict],
) -> bool:
    effect_type = infer_status_relief_type(action.action_text)
    if not effect_type:
        return False
    effects = status_list(character.status_effects)
    effect = next((item for item in effects if item.get("type") == effect_type), None)
    if not effect:
        return True

    outcome = action.outcome_tier or "failure"
    event_base = {
        "actor": character.name,
        "target": character.name,
        "effect": effect_type,
        "effect_label": effect.get("label") or effect_type,
        "effect_icon": effect.get("icon") or "⚠️",
        "outcome_tier": outcome,
    }
    if outcome in {"success", "critical_success"}:
        character.status_effects = consume_status(effects, effect_type)
        events.append({"type": "status_removed", **event_base})
        return True
    if outcome == "partial_success":
        previous_duration = max(1, int(effect.get("turns_remaining", 1)))
        previous_potency = max(1, int(effect.get("potency", 1)))
        effect["turns_remaining"] = max(1, previous_duration - 1)
        effect["potency"] = max(1, previous_potency - 1)
        character.status_effects = effects
        events.append({
            "type": "status_reduced",
            **event_base,
            "turns_reduced": previous_duration - int(effect["turns_remaining"]),
            "potency_reduced": previous_potency - int(effect["potency"]),
        })
        return True
    events.append({"type": "status_relief_failed", **event_base})
    return True


def infer_item_damage_power(item: InventoryItem) -> int:
    configured = int(getattr(item, "damage_power", 0) or 0)
    if configured > 0:
        return configured
    if item.item_type == "weapon":
        return 6 if int(getattr(item, "hands_required", 1) or 1) == 2 else 4
    if item.item_type in {"accessory", "misc"} and item.target_stat == "intellect":
        return 3
    return 0


def offensive_item(character: Character, tested_stat: str) -> InventoryItem | None:
    candidates = [
        item
        for item in get_effectively_equipped_items(character.inventory)
        if item.item_type == "weapon"
        or (item.item_type in {"accessory", "misc"} and item.target_stat == tested_stat)
    ]
    return max(candidates, key=infer_item_damage_power, default=None)


def estimate_character_damage(character: Character, defense_dc: int, armor: int) -> float:
    """Expected damage from one attack, including d20 odds and enemy armor."""
    estimates = []
    for tested_stat in ("strength", "agility", "intellect", "charisma", "perception"):
        stat_value = int(getattr(character, tested_stat, 0) or 0)
        item_bonus = calculate_item_modifier_details(
            character,
            tested_stat,
            action_text="atakuję przeciwnika",
            intent="attack",
        )[0]
        item = offensive_item(character, tested_stat)
        weapon_power = infer_item_damage_power(item) if item else 2
        base_damage = weapon_power + stat_value + character.level // 2
        expected = 0.0
        for roll in range(1, 21):
            if roll == 1:
                continue
            multiplier = (
                1.75 if roll == 20 else
                1.0 if roll + stat_value + item_bonus >= defense_dc else
                0.5 if roll + stat_value + item_bonus >= defense_dc - 2 else 0.0
            )
            if multiplier:
                expected += sum(
                    max(1, round((base_damage + damage_roll) * multiplier) - armor)
                    for damage_roll in range(1, 7)
                ) / 120
        estimates.append(expected)
    return max(estimates, default=0.0)


def attack_telegraph_description(description: str, attack_count: int) -> str:
    if attack_count <= 1:
        return description
    return f"{description} Zagrożenie może uderzyć w maksymalnie {attack_count} różne postacie."


def effective_attack_count(stored_attack_count: int | None, party_size: int) -> int:
    """Cap a persisted encounter response to the currently participating party."""
    if party_size <= 0:
        return 0
    current_party_cap = min(3, max(1, (party_size + 1) // 2))
    return min(max(1, int(stored_attack_count or 1)), current_party_cap, party_size)


def effective_attack_telegraph(telegraph: dict | None, party_size: int) -> dict | None:
    """Return a display-only telegraph with the live response count."""
    if not telegraph:
        return None
    result = dict(telegraph)
    attack_count = effective_attack_count(result.get("attack_count", 1), party_size)
    description = re.sub(
        r"\s+Zagrożenie może uderzyć w maksymalnie \d+ różne postacie\.$",
        "",
        str(result.get("description") or ""),
    )
    result["attack_count"] = attack_count
    result["description"] = attack_telegraph_description(description, attack_count)
    return result


def build_enemy_encounter(
    characters: Iterable[Character],
    description: str,
    world_pack: WorldPack | None = None,
) -> dict:
    world_pack = world_pack or get_default_world_pack()
    profile = world_pack.enemy_profile
    party = [
        character for character in characters
        if character.is_alive and character.is_participating
    ]
    average_level = sum(character.level for character in party) / len(party) if party else 1
    armor = max(1, min(4, int(average_level // 2)))
    defense_dc = 11 + min(4, int(average_level // 2))
    expected_turn_damage = sum(
        estimate_character_damage(character, defense_dc, armor) for character in party
    )
    minimum_hp = 20 + 10 * len(party) if party else 60
    max_hp = max(minimum_hp, int(math.ceil(expected_turn_damage * 3.5 / 5) * 5))
    attack_count = min(3, max(1, (len(party) + 1) // 2))
    normalized_description = normalize_text(description)
    status_effect = next(
        (
            cue.status_effect for cue in profile.status_cues
            if any(normalize_text(marker) in normalized_description for marker in cue.markers)
        ),
        profile.default_status_effect,
    )
    features = [
        {
            **feature.model_dump(mode="python"),
            "dc": defense_dc + feature.dc_offset,
            "state": "active",
        }
        for feature in profile.features
    ]
    first_attack = next(attack for attack in profile.attacks if attack.phase == 1)
    return {
        "hp": max_hp,
        "max_hp": max_hp,
        "armor": armor,
        "defense_dc": defense_dc,
        "phase": 1,
        "effects": [],
        "features": features,
        "telegraph": {
            "name": first_attack.name,
            "icon": first_attack.icon,
            "description": attack_telegraph_description(first_attack.description, attack_count),
            "base_damage": max(1, round((5 + int(average_level)) * (0.7 if len(party) == 1 else 1))),
            "attack_count": attack_count,
            "status_effect": status_effect,
        },
        "description": description,
    }


def build_boss_encounter(characters: Iterable[Character], description: str) -> dict:
    """Legacy entry point retained for the published dark_fantasy@1 contract."""
    return build_enemy_encounter(characters, description)


def ensure_enemy_encounter(
    session: GameSession,
    characters: Iterable[Character],
    world_pack: WorldPack | None = None,
) -> bool:
    """Uzupełnia mechanikę bossów utworzonych przed wprowadzeniem systemu starć."""
    if not session.active_boss_name or session.active_boss_features:
        return False
    previous_max_hp = int(session.active_boss_max_hp or 0)
    previous_hp = int(
        session.active_boss_hp
        if session.active_boss_hp is not None
        else previous_max_hp
    )
    health_ratio = previous_hp / previous_max_hp if previous_max_hp > 0 else 1.0
    world_pack = world_pack or get_default_world_pack()
    encounter = build_enemy_encounter(
        characters,
        session.active_boss_title or world_pack.enemy_profile.role_label,
        world_pack,
    )
    session.active_boss_max_hp = encounter["max_hp"]
    session.active_boss_hp = max(0, round(encounter["max_hp"] * health_ratio))
    session.active_boss_armor = encounter["armor"]
    session.active_boss_defense_dc = encounter["defense_dc"]
    session.active_boss_phase = 1 if health_ratio > 0.66 else 2 if health_ratio > 0.33 else 3
    session.active_boss_effects = encounter["effects"]
    session.active_boss_features = encounter["features"]
    session.active_boss_telegraph = encounter["telegraph"]
    return True


def ensure_boss_encounter(session: GameSession, characters: Iterable[Character]) -> bool:
    return ensure_enemy_encounter(session, characters)


def infer_action_intent(action_text: str, explicit_intent: str | None = None) -> str:
    return str(infer_action_intent_details(action_text, explicit_intent)["intent"])


def action_dc(
    session: GameSession,
    action: PlayerAction,
    *,
    challenge_tier: str = "standard",
    average_level: float = 1,
) -> tuple[int, str | None]:
    intent = infer_action_intent(action.action_text, action.intent)
    if intent == "attack" and session.active_boss_hp and session.active_boss_hp > 0:
        return int(session.active_boss_defense_dc or 12), None
    if intent == "interact" and action.target_ref:
        feature = next(
            (
                item for item in (session.active_boss_features or [])
                if isinstance(item, dict) and item.get("id") == action.target_ref
            ),
            None,
        )
        if feature and feature.get("state") == "active":
            return int(feature.get("dc", 12)), str(feature.get("required_stat") or "") or None
    if session.active_boss_hp and session.active_boss_hp > 0:
        return 12, None
    if challenge_tier == "hard":
        return min(25, 15 + int(average_level // 2)), None
    if challenge_tier == "climactic":
        return min(30, 18 + int(average_level // 2)), None
    return 12, None


def status_roll_penalty(character: Character) -> int:
    effects = status_list(character.status_effects)
    penalty = 0
    if has_status(effects, "poisoned"):
        penalty -= 2
    if has_status(effects, "frozen"):
        penalty -= 1
    return penalty


def calculate_attack_damage(
    character: Character,
    action: PlayerAction,
    boss_armor: int,
    boss_effects: list[dict],
) -> tuple[int, int, int, int]:
    if action.outcome_tier not in {"partial_success", "success", "critical_success"}:
        return 0, 0, 0, 0
    damage_roll = secrets.randbelow(6) + 1
    item = offensive_item(character, action.tested_stat or "strength")
    weapon_power = infer_item_damage_power(item) if item else 2
    base_damage = weapon_power + int(action.stat_modifier or 0) + character.level // 2 + damage_roll
    multiplier = {
        "partial_success": 0.5,
        "success": 1.0,
        "critical_success": 1.75,
    }[action.outcome_tier]
    if has_status(boss_effects, "exposed"):
        multiplier += 0.25
    if has_status(boss_effects, "frozen"):
        multiplier += 0.25
    if has_status(boss_effects, "stunned"):
        multiplier += 0.15
    reduction = max(0, int(boss_armor or 0))
    final_damage = max(1, round(base_damage * multiplier) - reduction)
    if getattr(action, "named_attack_id", None):
        final_damage += 1
    return final_damage, damage_roll, base_damage, reduction


def effect_from_attack(
    action_text: str,
    outcome_tier: str,
    source: str,
    ability: dict | None = None,
    world_pack: WorldPack | None = None,
) -> dict | None:
    if outcome_tier not in {"success", "critical_success"}:
        return None
    normalized = normalize_text(action_text)
    world_pack = world_pack or get_default_world_pack()
    potency = 2 if outcome_tier == "critical_success" else 1
    ability_params = ability.get("mechanic_params", {}) if ability else {}
    status_type = ability_params.get("status_type")
    if status_type:
        return make_status(
            str(status_type),
            int(ability_params.get("status_duration", 2)),
            int(ability_params.get("status_potency", potency)),
            source,
            world_pack,
        )
    for cue in world_pack.attack_status_cues:
        if any(normalize_text(marker) in normalized for marker in cue.markers):
            return make_status(
                cue.status_effect, cue.duration, potency, source, world_pack
            )
    return None


def _apply_hp_delta(character: Character, delta: int, action: PlayerAction) -> int:
    previous_hp = character.current_hp
    character.current_hp = max(0, min(character.max_hp, character.current_hp + delta))
    applied = character.current_hp - previous_hp
    action.hp_delta = int(action.hp_delta or 0) + applied
    if character.current_hp == 0:
        set_character_downed(character)
    elif character.current_hp > 0:
        character.is_alive = True
        character.death_state = "alive"
        character.death_failures = 0
    return applied


def set_character_downed(character: Character) -> None:
    """Przenosi postać do agonii i usuwa efekty, które nie trwają po utracie przytomności."""
    character.current_hp = 0
    character.is_alive = False
    character.status_effects = []
    if getattr(character, "death_state", "alive") not in {"downed", "stable", "dead"}:
        character.death_state = "downed"
        character.death_failures = 0


def _resolve_support_action(
    actor: Character,
    action: PlayerAction,
    characters: list[Character],
    events: list[dict],
    ability: dict | None = None,
    world_pack: WorldPack | None = None,
) -> None:
    target = None
    if action.target_ref:
        try:
            target_id = int(action.target_ref)
        except (TypeError, ValueError):
            target_id = None
        target = next((item for item in characters if item.id == target_id), None)

    is_resurrection = bool(ability and ability.get("mechanic_key") == "revive")
    if not target:
        candidates = [
            item for item in characters
            if item.id != actor.id
            and item.is_participating
            and (
                getattr(item, "death_state", "alive") == "dead"
                if is_resurrection
                else getattr(item, "death_state", "alive") != "dead"
            )
        ]
        target = min(
            candidates,
            key=lambda item: (item.current_hp / max(1, item.max_hp), item.current_hp),
            default=None,
        )
        if target:
            action.target_ref = str(target.id)

    if not target:
        events.append({"type": "support_failed", "actor": actor.name, "reason": "no_ally"})
        return

    outcome = action.outcome_tier or "failure"
    target_state = getattr(target, "death_state", "alive") or "alive"

    if is_resurrection and target_state != "dead":
        events.append({
            "type": "resurrection_failed",
            "actor": actor.name,
            "target": target.name,
            "reason": "not_dead",
        })
        return

    if target_state == "dead":
        if not is_resurrection or outcome not in {"success", "critical_success"}:
            events.append({
                "type": "resurrection_failed" if is_resurrection else "support_failed",
                "actor": actor.name,
                "target": target.name,
                "reason": "dead",
            })
            return
        previous_hp = target.current_hp
        revive_params = ability.get("mechanic_params", {}) if ability else {}
        restored_percent = (
            revive_params.get("critical_percent", 50)
            if outcome == "critical_success"
            else revive_params.get("success_percent", 25)
        )
        restored = max(1, round(target.max_hp * float(restored_percent) / 100))
        target.current_hp = restored
        target.is_alive = True
        target.death_state = "alive"
        target.death_failures = 0
        target.status_effects = []
        action.hp_delta = int(action.hp_delta or 0) + restored - previous_hp
        events.append({
            "type": "resurrection",
            "actor": actor.name,
            "target": target.name,
            "healing": restored,
        })
        return

    if outcome not in {"partial_success", "success", "critical_success"}:
        events.append({"type": "support_failed", "actor": actor.name, "target": target.name})
        return

    mechanic_key = ability.get("mechanic_key") if ability else None
    params = ability.get("mechanic_params", {}) if ability else {}
    healing_intent = mechanic_key == "heal" or bool(re.search(
        r"\b(?:lecz|uzdraw|opatru|stabiliz|bandaz|reanim|pierwsz\w*\s+pomoc)\w*\b",
        normalize_text(action.action_text),
    ))

    if mechanic_key == "cleanse":
        removable = {
            marker.strip() for marker in str(
                params.get("status_types", "burning,poisoned,frozen")
            ).split(",") if marker.strip()
        }
        before = status_list(target.status_effects)
        removed = sorted({
            str(effect.get("type")) for effect in before
            if effect.get("type") in removable
        })
        target.status_effects = [
            effect for effect in before if effect.get("type") not in removable
        ]
        events.append({
            "type": "ability_cleanse", "actor": actor.name,
            "target": target.name, "removed_types": removed,
        })
        return

    if not healing_intent:
        if target_state in {"downed", "stable"}:
            events.append({
                "type": "support_failed",
                "actor": actor.name,
                "target": target.name,
                "reason": "incapacitated_requires_healing",
            })
            return
        default_potency = {
            "partial_success": 1,
            "success": 2,
            "critical_success": 3,
        }[outcome]
        potency = int(params.get("potency", default_potency))
        duration = int(params.get("duration", 2))
        target.status_effects = add_status(
            status_list(target.status_effects),
            make_status("guarded", duration, potency, actor.name, world_pack),
        )
        events.append({
            "type": "support_guard",
            "actor": actor.name,
            "target": target.name,
            "potency": potency,
        })
        return

    if target_state in {"downed", "stable"} and outcome == "partial_success":
        target.death_state = "stable"
        target.death_failures = 0
        target.is_alive = False
        events.append({"type": "stabilized", "actor": actor.name, "target": target.name})
        return

    multiplier = 1 if outcome == "partial_success" else 2 if outcome == "success" else 3
    if mechanic_key == "heal" and params:
        tested_stat = str(ability.get("tested_stat") or "intellect")
        stat_value = int(getattr(actor, tested_stat, 0) or 0)
        healing = max(
            2,
            round(
                (float(params.get("base_healing", 2))
                 + stat_value * float(params.get("stat_scale", 1)))
                * multiplier
            ),
        )
    else:
        healing = max(2, (2 + actor.intellect) * multiplier)
    previous_hp = target.current_hp
    target.current_hp = min(target.max_hp, max(1, target.current_hp + healing))
    applied = target.current_hp - previous_hp
    target.is_alive = True
    target.death_state = "alive"
    target.death_failures = 0
    action.hp_delta = int(action.hp_delta or 0) + applied
    events.append({
        "type": "revived" if target_state in {"downed", "stable"} else "support",
        "actor": actor.name,
        "target": target.name,
        "healing": applied,
    })


def _resolve_utility_ability(
    session: GameSession | None,
    actor: Character,
    action: PlayerAction,
    ability: dict | None,
    events: list[dict],
    world_pack: WorldPack,
) -> bool:
    if not ability:
        return False
    key = ability.get("mechanic_key")
    if key not in {"scan", "jam", "move"}:
        return False
    if action.outcome_tier not in {"partial_success", "success", "critical_success"}:
        events.append({
            "type": "ability_failed", "actor": actor.name,
            "ability": ability["name"],
        })
        return True
    params = ability.get("mechanic_params", {})
    if key in {"scan", "jam"} and session and (session.active_boss_hp or 0) > 0:
        status_type = "exposed" if key == "scan" else "stunned"
        session.active_boss_effects = add_status(
            status_list(session.active_boss_effects),
            make_status(
                status_type,
                int(params.get("duration", 2)),
                int(params.get("potency", 1)),
                actor.name,
                world_pack,
            ),
        )
    events.append({
        "type": f"ability_{key}", "actor": actor.name,
        "ability": ability["name"],
        "target": session.active_boss_name if session else None,
    })
    return True


def _advance_death_states(
    characters: list[Character],
    downed_at_turn_start: set[int],
    events: list[dict],
) -> None:
    for character in characters:
        if character.id not in downed_at_turn_start or character.death_state != "downed":
            continue
        character.death_failures = min(3, int(character.death_failures or 0) + 1)
        if character.death_failures >= 3:
            character.death_state = "dead"
            character.status_effects = []
            events.append({"type": "character_died", "target": character.name})
        else:
            events.append({
                "type": "death_failure",
                "target": character.name,
                "failures": character.death_failures,
            })


def _tick_character_effects(character: Character, action: PlayerAction, events: list[dict]) -> None:
    remaining = []
    for effect in status_list(character.status_effects):
        effect_type = effect.get("type")
        potency = max(1, int(effect.get("potency", 1)))
        damage = potency * 2 if effect_type == "burning" else potency if effect_type == "poisoned" else 0
        if damage:
            applied = _apply_hp_delta(character, -damage, action)
            if applied:
                events.append({
                    "type": "status_damage",
                    "target": character.name,
                    "effect": effect_type,
                    "effect_label": effect.get("label") or effect_type,
                    "effect_icon": effect.get("icon") or "⚠️",
                    "damage": abs(applied),
                })
            if character.current_hp == 0:
                remaining = []
                break
        duration = int(effect.get("turns_remaining", 1))
        effect["turns_remaining"] = duration if duration >= 90 else duration - 1
        if effect["turns_remaining"] > 0:
            remaining.append(effect)
    character.status_effects = remaining


def _tick_boss_effects(session: GameSession, events: list[dict]) -> None:
    remaining = []
    for effect in status_list(session.active_boss_effects):
        effect_type = effect.get("type")
        potency = max(1, int(effect.get("potency", 1)))
        damage = potency * 2 if effect_type == "burning" else potency if effect_type == "poisoned" else 0
        if damage and session.active_boss_hp and session.active_boss_hp > 0:
            applied = min(damage, session.active_boss_hp)
            session.active_boss_hp -= applied
            events.append({
                "type": "status_damage",
                "target": session.active_boss_name,
                "source": effect.get("source"),
                "effect": effect_type,
                "effect_label": effect.get("label") or effect_type,
                "effect_icon": effect.get("icon") or "⚠️",
                "damage": applied,
            })
        duration = int(effect.get("turns_remaining", 1))
        effect["turns_remaining"] = duration if duration >= 90 else duration - 1
        if effect["turns_remaining"] > 0:
            remaining.append(effect)
    session.active_boss_effects = remaining


def _resolve_environment_action(
    session: GameSession,
    character: Character,
    action: PlayerAction,
    events: list[dict],
    world_pack: WorldPack,
) -> None:
    features = [dict(feature) for feature in (session.active_boss_features or []) if isinstance(feature, dict)]
    feature = next((item for item in features if item.get("id") == action.target_ref), None)
    if not feature or feature.get("state") != "active":
        return
    succeeded = action.outcome_tier in {"partial_success", "success", "critical_success"}
    if not succeeded:
        applied = _apply_hp_delta(character, -3, action)
        events.append({
            "type": "environment_failure",
            "actor": character.name,
            "feature": feature.get("name"),
            "damage": abs(applied),
        })
        return
    effectiveness = 0.5 if action.outcome_tier == "partial_success" else 1.0
    if action.outcome_tier == "critical_success":
        effectiveness = 1.5
    direct_damage = round((session.active_boss_max_hp or 0) * int(feature.get("damage_percent", 0)) / 100 * effectiveness)
    if direct_damage and session.active_boss_hp:
        direct_damage = min(direct_damage, session.active_boss_hp)
        session.active_boss_hp -= direct_damage
        action.damage_dealt = int(action.damage_dealt or 0) + direct_damage
    effect_type = feature.get("effect")
    if effect_type == "guarded":
        character.status_effects = add_status(
            status_list(character.status_effects),
            make_status(
                "guarded", 2, 5, feature.get("name", "Otoczenie"), world_pack
            ),
        )
    elif effect_type in STATUS_CATALOG:
        session.active_boss_effects = add_status(
            status_list(session.active_boss_effects),
            make_status(
                effect_type, 2, 1, feature.get("name", "Otoczenie"), world_pack
            ),
        )
    if not feature.get("reusable"):
        feature["state"] = "used"
    session.active_boss_features = features
    events.append({
        "type": "environment_success",
        "actor": character.name,
        "feature": feature.get("name"),
        "damage": direct_damage,
        "effect": effect_type,
    })


def _resolve_boss_response(
    session: GameSession,
    characters: list[Character],
    actions: list[PlayerAction],
    events: list[dict],
    world_pack: WorldPack,
) -> None:
    if not session.active_boss_hp or session.active_boss_hp <= 0:
        return
    alive = [
        character for character in characters
        if character.is_alive and character.is_participating
    ]
    if not alive:
        return
    action_by_character = {action.character_id: action for action in actions}
    telegraph = dict(session.active_boss_telegraph or {})
    attack_count = effective_attack_count(telegraph.get("attack_count", 1), len(alive))
    first_target = (session.current_turn_number - 1) % len(alive)
    targets = [alive[(first_target + offset) % len(alive)] for offset in range(attack_count)]
    damage = int(telegraph.get("base_damage", 6)) + max(0, int(session.active_boss_phase or 1) - 1) * 2
    boss_effects = status_list(session.active_boss_effects)
    if has_status(boss_effects, "stunned"):
        damage = max(1, damage // 2)
        session.active_boss_effects = consume_status(boss_effects, "stunned")
    defenders = [
        action for action in actions
        if action.intent == "defend" and action.outcome_tier in {"success", "critical_success"}
    ]
    defense_reduction = (
        5 if any(action.outcome_tier == "critical_success" for action in defenders)
        else 3 if defenders else 0
    )
    for target in targets:
        target_action = action_by_character.get(target.id)
        if not target_action:
            continue
        target_damage = damage
        guarded_reduction = 0
        guarded = next(
            (effect for effect in status_list(target.status_effects) if effect.get("type") == "guarded"),
            None,
        )
        if guarded:
            before_guard = target_damage
            target_damage = max(0, target_damage - max(1, int(guarded.get("potency", 1))))
            guarded_reduction = before_guard - target_damage
            target.status_effects = consume_status(status_list(target.status_effects), "guarded")
        before_team_defense = target_damage
        target_damage = max(0, target_damage - defense_reduction)
        team_defense_reduction = before_team_defense - target_damage
        applied = _apply_hp_delta(target, -target_damage, target_action)
        applied_effect = None
        applied_status = None
        if applied < 0 and int(session.active_boss_phase or 1) >= 2:
            applied_effect = str(
                telegraph.get("status_effect") or world_pack.enemy_profile.default_status_effect
            )
            applied_status = make_status(
                applied_effect, 3, 1,
                session.active_boss_name or world_pack.enemy_profile.role_label,
                world_pack,
            )
            target.status_effects = add_status(
                status_list(target.status_effects),
                applied_status,
            )
        events.append({
            "type": "boss_attack",
            "boss": session.active_boss_name,
            "attack": telegraph.get("name", world_pack.enemy_profile.attacks[0].name),
            "target": target.name,
            "damage": abs(applied),
            "base_damage": damage,
            "guarded_reduction": guarded_reduction,
            "team_defense_reduction": team_defense_reduction,
            "total_reduction": guarded_reduction + team_defense_reduction,
            "effect": applied_effect,
            "effect_label": applied_status.get("label") if applied_status else None,
            "effect_icon": applied_status.get("icon") if applied_status else None,
        })


def _update_boss_phase(
    session: GameSession,
    events: list[dict],
    world_pack: WorldPack,
) -> None:
    if not session.active_boss_max_hp:
        return
    ratio = max(0, session.active_boss_hp or 0) / session.active_boss_max_hp
    new_phase = 1 if ratio > 0.66 else 2 if ratio > 0.33 else 3
    old_phase = int(session.active_boss_phase or 1)
    session.active_boss_phase = new_phase
    if new_phase > old_phase and session.active_boss_hp:
        session.active_boss_effects = add_status(
            status_list(session.active_boss_effects),
            make_status(
                "enraged", 99, new_phase - 1, "Przemiana fazy", world_pack
            ),
        )
        events.append({"type": "phase_change", "phase": new_phase, "boss": session.active_boss_name})
    attack = next(
        definition for definition in world_pack.enemy_profile.attacks
        if definition.phase == new_phase
    )
    current_base = int((session.active_boss_telegraph or {}).get("base_damage", 6))
    attack_count = int((session.active_boss_telegraph or {}).get("attack_count", 1))
    session.active_boss_telegraph = {
        "name": attack.name,
        "icon": attack.icon,
        "description": attack_telegraph_description(attack.description, attack_count),
        "base_damage": current_base,
        "attack_count": attack_count,
        "status_effect": (session.active_boss_telegraph or {}).get(
            "status_effect", world_pack.enemy_profile.default_status_effect
        ),
    }


def _resolve_character_attack(
    actor: Character,
    action: PlayerAction,
    characters: list[Character],
    actions: list[PlayerAction],
    events: list[dict],
) -> bool:
    if not action.target_ref or not str(action.target_ref).isdigit():
        return False
    target = next(
        (character for character in characters
         if character.id == int(action.target_ref) and character.id != actor.id),
        None,
    )
    if target is None:
        return False
    if not target.is_alive or not target.is_participating:
        events.append({"type": "character_attack", "actor": actor.name,
                       "target": target.name, "damage": 0})
        return True
    if action.outcome_tier not in {"partial_success", "success", "critical_success"}:
        events.append({"type": "character_attack", "actor": actor.name,
                       "target": target.name, "damage": 0})
        return True

    if re.search(r"\b(?:kamien|kamyk|otoczak)\w*\b", normalize_text(action.action_text)):
        roll = secrets.randbelow(4) + 1
        base = roll + max(0, int(action.stat_modifier or 0) // 2)
        multiplier = {"partial_success": 0.5, "success": 1, "critical_success": 1.5}[action.outcome_tier]
        damage = max(1, round(base * multiplier))
        action.damage_roll = roll
        action.damage_base = base
        action.damage_reduction = 0
    else:
        damage, action.damage_roll, action.damage_base, action.damage_reduction = (
            calculate_attack_damage(actor, action, 0, [])
        )
    previous_hp = target.current_hp
    target.current_hp = max(0, previous_hp - damage)
    action.damage_dealt = previous_hp - target.current_hp
    target_action = next((item for item in actions if item.character_id == target.id), None)
    if target_action:
        target_action.hp_delta = int(target_action.hp_delta or 0) - action.damage_dealt
    if target.current_hp == 0:
        set_character_downed(target)
    events.append({"type": "character_attack", "actor": actor.name,
                   "target": target.name, "damage": action.damage_dealt})
    return True


def resolve_boss_turn(
    session: GameSession,
    characters: list[Character],
    actions: list[PlayerAction],
    *,
    world_pack: WorldPack | None = None,
) -> list[dict]:
    world_pack = world_pack or get_default_world_pack()
    events: list[dict] = []
    downed_at_turn_start = {
        character.id for character in characters
        if getattr(character, "death_state", "alive") == "downed"
    }
    action_by_character = {action.character_id: action for action in actions}
    living_at_turn_start = [
        character for character in characters
        if character.is_alive and character.is_participating
    ]
    retreating_character_ids = {
        action.character_id for action in actions
        if is_retreat_action(action.action_text)
    }
    coordinated_retreat = bool(living_at_turn_start) and all(
        character.id in retreating_character_ids for character in living_at_turn_start
    )
    _tick_boss_effects(session, events)
    for character in characters:
        action = action_by_character.get(character.id)
        if action:
            # Samoobrona przed aktywnym efektem zachodzi przed jego tyknięciem.
            # Udane ugaszenie nie może najpierw zranić postaci "za sukces".
            _resolve_status_relief_action(character, action, events)
            _tick_character_effects(character, action, events)

    intent_priority = {"interact": 0, "defend": 1, "support": 1, "attack": 2, "other": 3}
    ordered_actions = sorted(
        actions,
        key=lambda action: (
            intent_priority.get(infer_action_intent(action.action_text, action.intent), 3),
            action.id or 0,
        ),
    )
    for action in ordered_actions:
        character = next((item for item in characters if item.id == action.character_id), None)
        if not character or not character.is_alive or not character.is_participating:
            continue
        intent = infer_action_intent(action.action_text, action.intent)
        action.intent = intent
        ability = get_ability(
            world_pack,
            character.class_id or character.character_class,
            action.ability_id or action.magic_ability_id,
        )
        if _resolve_utility_ability(
            session, character, action, ability, events, world_pack
        ):
            continue
        if intent == "attack" and _resolve_character_attack(
            character, action, characters, actions, events
        ):
            continue
        if intent == "attack" and session.active_boss_hp and session.active_boss_hp > 0:
            boss_effects = status_list(session.active_boss_effects)
            damage, damage_roll, base_damage, reduction = calculate_attack_damage(
                character,
                action,
                int(session.active_boss_armor or 0),
                boss_effects,
            )
            damage = min(damage, session.active_boss_hp)
            session.active_boss_hp -= damage
            action.damage_dealt = damage
            action.damage_roll = damage_roll
            action.damage_base = base_damage
            action.damage_reduction = reduction
            applied_effect = effect_from_attack(
                action.action_text,
                action.outcome_tier or "failure",
                character.name,
                ability,
                world_pack,
            )
            used_item = offensive_item(character, action.tested_stat or "strength")
            used_item_name = normalize_text(used_item.name) if used_item else ""
            if not applied_effect and action.outcome_tier in {"success", "critical_success"}:
                for cue in world_pack.attack_status_cues:
                    if any(normalize_text(marker) in used_item_name for marker in cue.markers):
                        applied_effect = make_status(
                            cue.status_effect, cue.duration, 1, character.name,
                            world_pack,
                        )
                        break
            if applied_effect and session.active_boss_hp > 0:
                session.active_boss_effects = add_status(
                    status_list(session.active_boss_effects),
                    applied_effect,
                )
            if has_status(boss_effects, "frozen") and action.outcome_tier in {"success", "critical_success"}:
                session.active_boss_effects = consume_status(
                    status_list(session.active_boss_effects), "frozen"
                )
            events.append({
                "type": "player_attack",
                "actor": character.name,
                "target": session.active_boss_name,
                "damage": damage,
                "named_attack_id": action.named_attack_id,
                "named_attack_bonus": 1 if action.named_attack_id and damage > 0 else 0,
                "effect": applied_effect.get("type") if applied_effect else None,
            })
        elif intent == "interact":
            _resolve_environment_action(
                session, character, action, events, world_pack
            )
        elif intent == "defend" and action.outcome_tier in {"partial_success", "success", "critical_success"}:
            params = ability.get("mechanic_params", {}) if ability else {}
            potency = int(params.get("potency", 3 if action.outcome_tier == "partial_success" else 5 if action.outcome_tier == "success" else 8))
            duration = int(params.get("duration", 2))
            character.status_effects = add_status(
                status_list(character.status_effects),
                make_status(
                    "guarded", duration, potency, character.name, world_pack
                ),
            )
            events.append({"type": "defence", "actor": character.name, "potency": potency})
        elif intent == "support":
            _resolve_support_action(
                character, action, characters, events, ability, world_pack
            )

    if coordinated_retreat:
        enemy_name = session.active_boss_name
        events.append({
            "type": "party_retreat",
            "characters": [character.name for character in living_at_turn_start],
            "enemy": enemy_name,
            "restored_hp": 0,
            "mode": "declared",
        })
        clear_active_enemy(session)
    else:
        _resolve_boss_response(session, characters, actions, events, world_pack)
    _advance_death_states(characters, downed_at_turn_start, events)
    _update_boss_phase(session, events, world_pack)
    if session.active_boss_hp == 0:
        events.append({"type": "boss_defeated", "boss": session.active_boss_name})
    return events


def resolve_status_turn(
    characters: list[Character],
    actions: list[PlayerAction],
    *,
    world_pack: WorldPack | None = None,
) -> list[dict]:
    """Rozlicza pozostałe efekty także po zakończeniu walki z bossem."""
    world_pack = world_pack or get_default_world_pack()
    events: list[dict] = []
    downed_at_turn_start = {
        character.id for character in characters
        if getattr(character, "death_state", "alive") == "downed"
    }
    action_by_character = {action.character_id: action for action in actions}
    for character in characters:
        action = action_by_character.get(character.id)
        if action and character.is_alive and character.is_participating:
            _resolve_status_relief_action(character, action, events)
            _tick_character_effects(character, action, events)
    for action in actions:
        actor = next((item for item in characters if item.id == action.character_id), None)
        if not actor or not actor.is_alive or not actor.is_participating:
            continue
        if infer_action_intent(action.action_text, action.intent) == "attack" and (
            _resolve_character_attack(actor, action, characters, actions, events)
        ):
            continue
        ability = get_ability(
            world_pack,
            actor.class_id or actor.character_class,
            action.ability_id or action.magic_ability_id,
        )
        if _resolve_utility_ability(
            None, actor, action, ability, events, world_pack
        ):
            continue
        if infer_action_intent(action.action_text, action.intent) == "support":
            _resolve_support_action(
                actor, action, characters, events, ability, world_pack
            )
    _advance_death_states(characters, downed_at_turn_start, events)
    return events
