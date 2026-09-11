import math
import secrets
import unicodedata
from typing import Iterable

from app.inventory import get_effectively_equipped_items
from app.models import Character, GameSession, InventoryItem, PlayerAction


ATTACK_WORDS = (
    "atak", "walcz", "zabij", "dobij", "ranie", "cios", "tnę", "tne", "uderz", "strzel", "strzał", "strzal",
    "pocisk", "zaklęcie ofensywne", "zaklecie ofensywne", "kula ognia",
    "kula ognia", "blyskawic", "podpal", "zamraz", "truj", "miecz",
    "topor", "luk", "wlocz",
)
DEFENCE_WORDS = (
    "bronię", "bron", "blok", "zasłani", "oslani", "tarc", "unik",
    "osłon", "oslon", "chronię", "chronie",
)
INTERACTION_WORDS = (
    "badam", "urucham", "niszczę", "niszcze", "przewrac", "pieczęć",
    "pieczec", "filar", "otoczen", "mechanizm", "run", "arena",
)
SUPPORT_WORDS = ("lecz", "uzdraw", "opatru", "antidot", "oczyszcz", "wspier")

STATUS_CATALOG = {
    "burning": {
        "label": "Poparzony",
        "icon": "🔥",
        "description": "Otrzymuje obrażenia od ognia na początku kolejnej tury.",
        "tone": "orange",
    },
    "poisoned": {
        "label": "Zatruty",
        "icon": "☠️",
        "description": "Otrzymuje obrażenia i ma karę do testów.",
        "tone": "green",
    },
    "frozen": {
        "label": "Zamrożony",
        "icon": "❄️",
        "description": "Ma obniżoną obronę; następny silny cios rozbija lód.",
        "tone": "cyan",
    },
    "stunned": {
        "label": "Oszołomiony",
        "icon": "💫",
        "description": "Najbliższy atak zadaje więcej obrażeń, a atak bossa jest słabszy.",
        "tone": "yellow",
    },
    "exposed": {
        "label": "Odsłonięty",
        "icon": "🎯",
        "description": "Otrzymuje o 25% więcej obrażeń.",
        "tone": "rose",
    },
    "guarded": {
        "label": "Osłonięty",
        "icon": "🛡️",
        "description": "Redukuje obrażenia następnego ataku.",
        "tone": "blue",
    },
    "enraged": {
        "label": "Rozwścieczony",
        "icon": "😡",
        "description": "Ataki bossa są silniejsze w tej fazie.",
        "tone": "rose",
    },
}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", (value or "").casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def make_status(
    effect_type: str,
    turns: int,
    potency: int = 1,
    source: str = "",
) -> dict:
    definition = STATUS_CATALOG[effect_type]
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


def estimate_character_damage(character: Character) -> float:
    equipped = get_effectively_equipped_items(character.inventory)
    item = max(equipped, key=infer_item_damage_power, default=None)
    weapon_power = infer_item_damage_power(item) if item else 2
    best_stat = max(character.strength, character.agility, character.intellect)
    average_success_damage = weapon_power + best_stat + character.level // 2 + 3.5
    return max(6.0, average_success_damage * 0.75)


def build_boss_encounter(characters: Iterable[Character], description: str) -> dict:
    party = [character for character in characters if character.is_alive]
    average_level = sum(character.level for character in party) / len(party) if party else 1
    expected_turn_damage = sum(estimate_character_damage(character) for character in party) or 15
    max_hp = max(60, int(math.ceil((expected_turn_damage * 4) / 5) * 5))
    armor = max(1, min(4, int(average_level // 2)))
    defense_dc = 11 + min(4, int(average_level // 2))
    hazard_dc = defense_dc + 1
    normalized_description = normalize_text(description)
    if any(word in normalized_description for word in ("lod", "mroz", "szron")):
        boss_status_effect = "frozen"
    elif any(word in normalized_description for word in ("jad", "truciz", "toksyn")):
        boss_status_effect = "poisoned"
    else:
        boss_status_effect = "burning"
    features = [
        {
            "id": "unstable_pillar",
            "name": "Niestabilny filar",
            "icon": "🗿",
            "description": "Przewrócenie filaru rani i oszałamia bossa.",
            "required_stat": "strength",
            "dc": hazard_dc,
            "state": "active",
            "damage_percent": 12,
            "effect": "stunned",
        },
        {
            "id": "runic_seal",
            "name": "Runiczna pieczęć",
            "icon": "🔮",
            "description": "Złamanie pieczęci odsłania słaby punkt przeciwnika.",
            "required_stat": "intellect",
            "dc": hazard_dc,
            "state": "active",
            "damage_percent": 0,
            "effect": "exposed",
        },
        {
            "id": "broken_battlement",
            "name": "Kamienna osłona",
            "icon": "🧱",
            "description": "Zajęcie pozycji osłania bohatera przed kolejnym ciosem.",
            "required_stat": "agility",
            "dc": defense_dc,
            "state": "active",
            "damage_percent": 0,
            "effect": "guarded",
            "reusable": True,
        },
    ]
    return {
        "hp": max_hp,
        "max_hp": max_hp,
        "armor": armor,
        "defense_dc": defense_dc,
        "phase": 1,
        "effects": [],
        "features": features,
        "telegraph": {
            "name": "Miażdżące natarcie",
            "icon": "⚠️",
            "description": "Boss szykuje potężny cios w jednego z bohaterów.",
            "base_damage": 5 + int(average_level),
            "status_effect": boss_status_effect,
        },
        "description": description,
    }


def ensure_boss_encounter(session: GameSession, characters: Iterable[Character]) -> bool:
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
    encounter = build_boss_encounter(characters, session.active_boss_title or "Boss")
    session.active_boss_max_hp = encounter["max_hp"]
    session.active_boss_hp = max(0, round(encounter["max_hp"] * health_ratio))
    session.active_boss_armor = encounter["armor"]
    session.active_boss_defense_dc = encounter["defense_dc"]
    session.active_boss_phase = 1 if health_ratio > 0.66 else 2 if health_ratio > 0.33 else 3
    session.active_boss_effects = encounter["effects"]
    session.active_boss_features = encounter["features"]
    session.active_boss_telegraph = encounter["telegraph"]
    return True


def infer_action_intent(action_text: str, explicit_intent: str | None = None) -> str:
    if explicit_intent in {"attack", "defend", "interact", "support", "other"}:
        return explicit_intent
    normalized = normalize_text(action_text)
    if any(word in normalized for word in DEFENCE_WORDS):
        return "defend"
    if any(word in normalized for word in INTERACTION_WORDS):
        return "interact"
    if any(word in normalized for word in SUPPORT_WORDS):
        return "support"
    if any(word in normalized for word in ATTACK_WORDS):
        return "attack"
    return "other"


def action_dc(session: GameSession, action: PlayerAction) -> tuple[int, str | None]:
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
    return final_damage, damage_roll, base_damage, reduction


def effect_from_attack(action_text: str, outcome_tier: str, source: str) -> dict | None:
    if outcome_tier not in {"success", "critical_success"}:
        return None
    normalized = normalize_text(action_text)
    potency = 2 if outcome_tier == "critical_success" else 1
    if any(word in normalized for word in ("ogien", "plomien", "podpal", "zar")):
        return make_status("burning", 2, potency, source)
    if any(word in normalized for word in ("truj", "truciz", "zatrut", "jad", "toksyn")):
        return make_status("poisoned", 3, potency, source)
    if any(word in normalized for word in ("lod", "mroz", "zamraz", "szron")):
        return make_status("frozen", 2, potency, source)
    return None


def _apply_hp_delta(character: Character, delta: int, action: PlayerAction) -> int:
    previous_hp = character.current_hp
    character.current_hp = max(0, min(character.max_hp, character.current_hp + delta))
    applied = character.current_hp - previous_hp
    action.hp_delta = int(action.hp_delta or 0) + applied
    if character.current_hp == 0:
        character.is_alive = False
    return applied


def _tick_character_effects(character: Character, action: PlayerAction, events: list[dict]) -> None:
    remaining = []
    for effect in status_list(character.status_effects):
        effect_type = effect.get("type")
        potency = max(1, int(effect.get("potency", 1)))
        damage = potency * 2 if effect_type == "burning" else potency if effect_type == "poisoned" else 0
        if damage:
            applied = _apply_hp_delta(character, -damage, action)
            events.append({
                "type": "status_damage",
                "target": character.name,
                "effect": effect_type,
                "damage": abs(applied),
            })
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
                "effect": effect_type,
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
            make_status("guarded", 2, 5, feature.get("name", "Otoczenie")),
        )
    elif effect_type in STATUS_CATALOG:
        session.active_boss_effects = add_status(
            status_list(session.active_boss_effects),
            make_status(effect_type, 2, 1, feature.get("name", "Otoczenie")),
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
) -> None:
    if not session.active_boss_hp or session.active_boss_hp <= 0:
        return
    alive = [character for character in characters if character.is_alive]
    if not alive:
        return
    action_by_character = {action.character_id: action for action in actions}
    target = alive[(session.current_turn_number - 1) % len(alive)]
    target_action = action_by_character.get(target.id)
    if not target_action:
        return
    telegraph = dict(session.active_boss_telegraph or {})
    damage = int(telegraph.get("base_damage", 6)) + max(0, int(session.active_boss_phase or 1) - 1) * 2
    boss_effects = status_list(session.active_boss_effects)
    if has_status(boss_effects, "stunned"):
        damage = max(1, damage // 2)
        session.active_boss_effects = consume_status(boss_effects, "stunned")
    guarded = next(
        (effect for effect in status_list(target.status_effects) if effect.get("type") == "guarded"),
        None,
    )
    if guarded:
        damage = max(0, damage - max(1, int(guarded.get("potency", 1))))
        target.status_effects = consume_status(status_list(target.status_effects), "guarded")
    defenders = [
        action for action in actions
        if action.intent == "defend" and action.outcome_tier in {"success", "critical_success"}
    ]
    if defenders:
        damage = max(0, damage - (5 if any(a.outcome_tier == "critical_success" for a in defenders) else 3))
    applied = _apply_hp_delta(target, -damage, target_action)
    applied_effect = None
    if applied < 0 and int(session.active_boss_phase or 1) >= 2:
        applied_effect = str(telegraph.get("status_effect") or "burning")
        target.status_effects = add_status(
            status_list(target.status_effects),
            make_status(applied_effect, 3, 1, session.active_boss_name or "Boss"),
        )
    events.append({
        "type": "boss_attack",
        "boss": session.active_boss_name,
        "attack": telegraph.get("name", "Atak bossa"),
        "target": target.name,
        "damage": abs(applied),
        "effect": applied_effect,
    })


def _update_boss_phase(session: GameSession, events: list[dict]) -> None:
    if not session.active_boss_max_hp:
        return
    ratio = max(0, session.active_boss_hp or 0) / session.active_boss_max_hp
    new_phase = 1 if ratio > 0.66 else 2 if ratio > 0.33 else 3
    old_phase = int(session.active_boss_phase or 1)
    session.active_boss_phase = new_phase
    if new_phase > old_phase and session.active_boss_hp:
        session.active_boss_effects = add_status(
            status_list(session.active_boss_effects),
            make_status("enraged", 99, new_phase - 1, "Przemiana fazy"),
        )
        events.append({"type": "phase_change", "phase": new_phase, "boss": session.active_boss_name})
    attack_names = {
        1: ("Miażdżące natarcie", "Boss szykuje potężny cios w jednego z bohaterów."),
        2: ("Rozdarcie areny", "Boss zamierza uderzyć z większą siłą; osłona ograniczy obrażenia."),
        3: ("Ostatnia furia", "Desperacki atak bossa będzie znacznie silniejszy."),
    }
    name, description = attack_names[new_phase]
    current_base = int((session.active_boss_telegraph or {}).get("base_damage", 6))
    session.active_boss_telegraph = {
        "name": name,
        "icon": "⚠️",
        "description": description,
        "base_damage": current_base,
        "status_effect": (session.active_boss_telegraph or {}).get("status_effect", "burning"),
    }


def resolve_boss_turn(
    session: GameSession,
    characters: list[Character],
    actions: list[PlayerAction],
) -> list[dict]:
    events: list[dict] = []
    action_by_character = {action.character_id: action for action in actions}
    _tick_boss_effects(session, events)
    for character in characters:
        action = action_by_character.get(character.id)
        if action:
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
        if not character or not character.is_alive:
            continue
        intent = infer_action_intent(action.action_text, action.intent)
        action.intent = intent
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
            )
            used_item = offensive_item(character, action.tested_stat or "strength")
            used_item_name = normalize_text(used_item.name) if used_item else ""
            if not applied_effect and action.outcome_tier in {"success", "critical_success"}:
                if any(word in used_item_name for word in ("zatrut", "jad", "toksyn")):
                    applied_effect = make_status("poisoned", 3, 1, character.name)
                elif any(word in used_item_name for word in ("ogien", "plomien")):
                    applied_effect = make_status("burning", 2, 1, character.name)
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
                "effect": applied_effect.get("type") if applied_effect else None,
            })
        elif intent == "interact":
            _resolve_environment_action(session, character, action, events)
        elif intent == "defend" and action.outcome_tier in {"partial_success", "success", "critical_success"}:
            potency = 3 if action.outcome_tier == "partial_success" else 5 if action.outcome_tier == "success" else 8
            character.status_effects = add_status(
                status_list(character.status_effects),
                make_status("guarded", 2, potency, character.name),
            )
            events.append({"type": "defence", "actor": character.name, "potency": potency})
        elif intent == "support" and action.outcome_tier in {"partial_success", "success", "critical_success"}:
            multiplier = 1 if action.outcome_tier == "partial_success" else 2 if action.outcome_tier == "success" else 3
            healing = max(2, (2 + character.intellect) * multiplier)
            applied = _apply_hp_delta(character, healing, action)
            if action.outcome_tier == "critical_success":
                character.status_effects = [
                    effect for effect in status_list(character.status_effects)
                    if effect.get("type") not in {"burning", "poisoned", "frozen"}
                ]
            events.append({"type": "support", "actor": character.name, "healing": applied})

    _resolve_boss_response(session, characters, actions, events)
    _update_boss_phase(session, events)
    if session.active_boss_hp == 0:
        events.append({"type": "boss_defeated", "boss": session.active_boss_name})
    return events


def resolve_status_turn(
    characters: list[Character],
    actions: list[PlayerAction],
) -> list[dict]:
    """Rozlicza pozostałe efekty także po zakończeniu walki z bossem."""
    events: list[dict] = []
    action_by_character = {action.character_id: action for action in actions}
    for character in characters:
        action = action_by_character.get(character.id)
        if action and character.is_alive:
            _tick_character_effects(character, action, events)
    return events
