import re
import secrets
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from app.action_dialogue import action_mechanics_text
from app.models import CampaignMap, Character, GameSession, InventoryItem, Turn
from app.worlds.models import LootRarityDefinition, WorldPack
from app.worlds.registry import WORLD_PACK_REGISTRY, get_default_world_pack


CRAFTING_KEYWORDS = (
    "scal", "ulepsz", "przekuw", "przerab", "wytwarz",
)
AMBIGUOUS_CRAFTING_KEYWORDS = ("lacz", "polacz", "wzmacn")
CRAFTING_OBJECT_KEYWORDS = (
    "przedmiot", "skladnik", "ekwipun", "bron",
)
COMBAT_ACTION_KEYWORDS = (
    "atak", "uderz", "strzel", "tne", "cios", "bronie", "oslaniam", "lecze", "wspieram",
)
MOVEMENT_ACTION_KEYWORDS = (
    "ide", "idziemy", "wchodze", "przechodze", "ruszam", "uciekam", "odwrot",
)
CRAFTABLE_ITEM_TYPES = {"weapon", "shield", "armor", "helmet", "boots", "accessory", "misc"}
CRAFTING_SUCCESS_TIERS = {"partial_success", "success", "critical_success"}
LOOT_SUCCESS_TIERS = {"success", "critical_success"}


@dataclass
class InventoryResolution:
    new_items: list[InventoryItem] = field(default_factory=list)
    consumed_items: list[InventoryItem] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)


def normalize_game_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _item_quantity(item: InventoryItem) -> int:
    """Treat an unflushed ORM default as one item without accepting zero stock."""
    return int(item.quantity if item.quantity is not None else 1)


def _has_token_stem(value: str, stems: Iterable[str]) -> bool:
    tokens = re.findall(r"[a-z0-9]+", normalize_game_text(value))
    return any(token.startswith(stem) for token in tokens for stem in stems)


def has_crafting_intent(action_text: str, world_pack: WorldPack | None = None) -> bool:
    action_text = action_mechanics_text(action_text)
    if _has_token_stem(action_text, CRAFTING_KEYWORDS):
        return True
    pack = world_pack or get_default_world_pack()
    vocabulary = tuple(
        normalize_game_text(alias)[:4]
        for rule in pack.item_vocabulary
        for alias in rule.aliases
    )
    object_markers = tuple(
        normalize_game_text(marker)
        for marker in pack.crafting_profile.object_markers
    )
    return (
        _has_token_stem(action_text, AMBIGUOUS_CRAFTING_KEYWORDS)
        and _has_token_stem(
            action_text, (*CRAFTING_OBJECT_KEYWORDS, *object_markers, *vocabulary)
        )
    )


def has_loot_search_intent(
    action_text: str, world_pack: WorldPack | None = None
) -> bool:
    world_pack = world_pack or get_default_world_pack()
    action_text = action_mechanics_text(action_text)
    normalized = normalize_game_text(action_text)
    return any(
        normalize_game_text(marker) in normalized
        or _has_token_stem(action_text, (normalize_game_text(marker),))
        for marker in world_pack.narrative_profile.loot_search_markers
    )


def infer_crafting_source_items(
    action_text: str,
    inventory: Iterable[InventoryItem],
    world_pack: WorldPack | None = None,
) -> list[InventoryItem]:
    """Rozpoznaje konkretne, trwałe przedmioty wymienione w deklaracji craftingu."""
    action_text = action_mechanics_text(action_text)
    if not has_crafting_intent(action_text, world_pack):
        return []

    normalized_action = normalize_game_text(action_text)
    inventory_items = [item for item in inventory if item.item_type in CRAFTABLE_ITEM_TYPES]
    pack = world_pack or get_default_world_pack()
    ignored_name_parts = {
        normalize_game_text(part)
        for part in pack.crafting_profile.ignored_name_parts
    }
    item_prefixes: dict[int, set[str]] = {}
    prefix_counts: Counter[str] = Counter()
    for item in inventory_items:
        prefixes = {
            part[:4]
            for part in normalize_game_text(item.name).split()
            if len(part) >= 4 and not any(part.startswith(ignored) for ignored in ignored_name_parts)
        }
        item_prefixes[id(item)] = prefixes
        prefix_counts.update(prefixes)

    matched_items: list[InventoryItem] = []
    for item in inventory_items:
        normalized_name = normalize_game_text(item.name)
        if normalized_name in normalized_action:
            matched_items.append(item)
            continue

        # Odmieniona nazwa może zostać rozpoznana po unikalnym rdzeniu, ale wspólne
        # słowo typu „miecz” nie może automatycznie zaznaczyć całego plecaka.
        unique_prefixes = [
            prefix for prefix in item_prefixes[id(item)] if prefix_counts[prefix] == 1
        ]
        if any(prefix in normalized_action for prefix in unique_prefixes):
            matched_items.append(item)
    return matched_items


def validate_special_action(
    action_text: str,
    inventory: Iterable[InventoryItem],
    session: GameSession,
    current_turn_number: int,
    inferred_intent: str,
    uses_magic: bool,
    campaign_map: CampaignMap | None,
    world_pack: WorldPack | None = None,
    craft_item_ids: list[int] | None = None,
) -> str | None:
    world_pack = world_pack or get_default_world_pack()
    action_text = action_mechanics_text(action_text)
    crafting = has_crafting_intent(action_text, world_pack)
    searching = has_loot_search_intent(action_text, world_pack)

    if crafting and searching:
        return "Jedna tura obejmuje jeden główny zamiar. Wybierz crafting albo przeszukiwanie."
    if uses_magic and (crafting or searching):
        return "Użycie zdolności, crafting i przeszukiwanie są osobnymi akcjami. Wybierz jedną z nich."
    normalized_action = normalize_game_text(action_text)
    includes_combat_action = _has_token_stem(normalized_action, COMBAT_ACTION_KEYWORDS)
    includes_movement = _has_token_stem(normalized_action, MOVEMENT_ACTION_KEYWORDS)
    if (crafting or searching) and (
        inferred_intent in {"attack", "defend", "support"} or includes_combat_action
    ):
        return "Atak, obrona lub wsparcie nie mogą być łączone w jednej turze z craftingiem ani szukaniem łupu."
    if searching and includes_movement:
        return "Przemieszczenie i przeszukiwanie lokacji są osobnymi akcjami. Wybierz jeden zamiar."

    boss_alive = bool(session.active_boss_name and (session.active_boss_hp or 0) > 0)
    if searching:
        if boss_alive:
            return "Nie możesz przeszukiwać pobojowiska podczas aktywnej walki."
        node_id = campaign_map.current_node_id if campaign_map else None
        if node_id and node_id in (session.looted_location_ids or []):
            return "Ta lokacja została już dokładnie przeszukana."

    if crafting:
        if boss_alive:
            return "Nie możesz scalać ani ulepszać przedmiotów podczas aktywnej walki."
        from app.services.market_service import workshop_is_open

        if not workshop_is_open(
            session,
            location_node_id=(campaign_map.current_node_id if campaign_map else None),
            current_turn_number=current_turn_number,
        ):
            return world_pack.crafting_profile.workshop_unavailable_message
        sources = (
            [item for item in inventory if item.id in craft_item_ids]
            if craft_item_ids is not None
            else infer_crafting_source_items(action_text, inventory, world_pack)
        )
        if craft_item_ids is not None and (
            len(set(craft_item_ids)) != 3
            or {item.id for item in sources} != set(craft_item_ids)
            or any(item.is_equipped or _item_quantity(item) < 1 for item in sources)
            or any(item.item_type not in CRAFTABLE_ITEM_TYPES for item in sources)
        ):
            return "Wybierz trzy różne przedmioty z plecaka."
        if len(sources) != 3:
            return "Crafting wymaga wskazania w akcji dokładnie trzech posiadanych przedmiotów."
        item_types = {item.item_type for item in sources}
        if len(item_types) != 1:
            return "Scalić można tylko trzy przedmioty tego samego typu."
    elif craft_item_ids is not None:
        return "Wybór przedmiotów wymaga deklaracji craftingu."
    return None


def resolve_inventory_mechanics(
    session: GameSession,
    turn: Turn,
    characters: list[Character],
    campaign_map: CampaignMap | None,
    world_pack: WorldPack | None = None,
) -> InventoryResolution:
    world_pack = world_pack or get_default_world_pack()
    resolution = InventoryResolution()
    boss_defeated = any(
        isinstance(event, dict) and event.get("type") == "boss_defeated"
        for event in (turn.combat_events or [])
    )
    from app.services.market_service import workshop_is_open

    for action in turn.actions:
        if not has_crafting_intent(action.action_text, world_pack):
            continue
        if (
            boss_defeated
            or (session.active_boss_name and (session.active_boss_hp or 0) > 0)
            or not workshop_is_open(
                session,
                location_node_id=(campaign_map.current_node_id if campaign_map else None),
                current_turn_number=turn.turn_number,
            )
        ):
            continue
        character = next((item for item in characters if item.id == action.character_id), None)
        if not character or action.outcome_tier not in CRAFTING_SUCCESS_TIERS:
            continue
        sources = (
            [item for item in character.inventory if item.id in action.craft_item_ids]
            if action.craft_item_ids is not None
            else infer_crafting_source_items(action.action_text, character.inventory, world_pack)
        )
        if (
            len(sources) != 3
            or len({item.item_type for item in sources}) != 1
            or any(item.is_equipped or _item_quantity(item) < 1 for item in sources)
            or any(item.item_type not in CRAFTABLE_ITEM_TYPES for item in sources)
        ):
            continue
        crafted = _build_crafted_item(character, sources, world_pack)
        resolution.new_items.append(crafted)
        for source in sources:
            source_quantity = _item_quantity(source)
            if source_quantity > 1:
                source.quantity = source_quantity - 1
            else:
                resolution.consumed_items.append(source)
        resolution.events.append({
            "type": "item_crafted",
            "actor": character.name,
            "item": crafted.name,
            "source_items": [item.name for item in sources],
            "stat_bonus": crafted.stat_bonus,
        })

    if boss_defeated:
        from app.services.market_service import open_market_visit

        visit_turn = turn.turn_number + 1
        merchant = open_market_visit(
            session,
            characters,
            world_pack,
            visit_turn,
            location_node_id=(campaign_map.current_node_id if campaign_map else None),
        )
        if merchant:
            resolution.events.append({
                "type": "merchant_arrived",
                "name": merchant["name"],
                "role": merchant["role"],
                "greeting": merchant["greeting"],
            })
        recipient = _choose_recipient(
            [
                character for character in characters
                if character.is_alive and character.is_participating
            ],
            session.last_loot_character_id,
        )
        if recipient:
            item = _build_random_loot(recipient, world_pack, boss_reward=True)
            coins_awarded = 5 + recipient.level
            recipient.coins = int(recipient.coins or 0) + coins_awarded
            resolution.new_items.append(item)
            session.last_loot_character_id = recipient.id
            resolution.events.append({
                "type": "item_found",
                "source": "boss",
                "actor": recipient.name,
                "item": item.name,
                "stat_bonus": item.stat_bonus,
                "curse_stat": item.curse_stat,
                "curse_penalty": int(item.curse_penalty or 0),
                "coins_awarded": coins_awarded,
            })
        return resolution

    search_actions = [
        action for action in turn.actions
        if has_loot_search_intent(action.action_text, world_pack)
    ]
    if not search_actions:
        return resolution
    if session.active_boss_name and (session.active_boss_hp or 0) > 0:
        return resolution

    node_id = campaign_map.current_node_id if campaign_map else f"turn-{turn.turn_number}"
    looted_locations = list(session.looted_location_ids or [])
    if node_id in looted_locations:
        return resolution
    looted_locations.append(node_id)
    session.looted_location_ids = looted_locations

    living_by_id = {
        character.id: character for character in characters
        if character.is_alive and character.is_participating
    }
    successful_actions = [
        action for action in search_actions
        if action.character_id in living_by_id and action.outcome_tier in LOOT_SUCCESS_TIERS
    ]
    if not successful_actions:
        resolution.events.append({"type": "loot_search_empty", "location_id": node_id, "reason": "failure"})
        return resolution

    finder_action = max(
        successful_actions,
        key=lambda action: (
            1 if action.outcome_tier == "critical_success" else 0,
            int(action.dice_total or 0),
            -int(action.id or 0),
        ),
    )
    finder = living_by_id[finder_action.character_id]

    if secrets.randbelow(5) == 0:
        resolution.events.append({"type": "loot_search_empty", "location_id": node_id, "reason": "empty"})
        return resolution

    critical = finder_action.outcome_tier == "critical_success"
    recipient = finder
    item = _build_random_loot(recipient, world_pack, critical_search=critical)
    coins_awarded = 2 + recipient.level
    recipient.coins = int(recipient.coins or 0) + coins_awarded
    resolution.new_items.append(item)
    session.last_loot_character_id = recipient.id
    resolution.events.append({
        "type": "item_found",
        "source": "exploration",
        "location_id": node_id,
        "found_by": finder.name,
        "actor": recipient.name,
        "item": item.name,
        "stat_bonus": item.stat_bonus,
        "curse_stat": item.curse_stat,
        "curse_penalty": int(item.curse_penalty or 0),
        "coins_awarded": coins_awarded,
    })
    return resolution


def strip_loot_claims(
    narration: str, world_pack: WorldPack, events: list[dict] | None = None
) -> str:
    """Remove model-written acquisition claims; events supply authoritative ones."""
    labels = {
        normalize_game_text(entry.label)
        for table in world_pack.loot_tables for entry in table.entries
    }
    labels.add(normalize_game_text(world_pack.consumable_loot.name))
    acquisition = re.compile(
        r"\b(?:znalaz\w*|znajd\w*|wygrzeb\w*|zdobyl\w*|zdobyw\w*|"
        r"podnios\w*|wyciagn\w*|otrzym\w*|zabral\w*|trafil\w*|"
        r"wzial\w*|schowal\w*|przygarn\w*)\b",
    )
    empty_search = any(
        event.get("type") == "loot_search_empty" for event in (events or [])
    )
    clue = re.compile(r"\b(?:slad|wskazowk|trop|informacj)\w*\b")
    item_word = re.compile(
        r"\b(?:przedmiot|artefakt|amulet|bron|miecz|sztylet|pierscien|"
        r"zbroj|kula|rekwizyt|ekwipun|skar[bc]|relikw)\w*\b"
    )
    kept = []
    for sentence in re.split(r"(?<=[.!?])\s+", narration):
        lowered = normalize_game_text(sentence)
        if acquisition.search(lowered) and (
            any(label in lowered for label in labels)
            or item_word.search(lowered)
            or (empty_search and not clue.search(lowered))
        ):
            continue
        kept.append(sentence)
    return " ".join(part.strip() for part in kept if part.strip())


def reconcile_loot_narration(
    narration: str, events: list[dict], world_pack: WorldPack
) -> str:
    """Keep acquisition claims in generated prose aligned with persisted loot events."""
    loot_events = [event for event in events if event.get("type") == "item_found"]
    empty_events = [event for event in events if event.get("type") == "loot_search_empty"]
    authoritative = []
    for event in loot_events:
        money = f" i {event['coins_awarded']} monet" if event.get("coins_awarded") else ""
        curse_abbreviation = next(
            (attribute.abbreviation for attribute in world_pack.attributes
             if attribute.id == event.get("curse_stat")),
            event.get("curse_stat") or "",
        )
        curse = (
            f" Po założeniu klątwa daje {event['curse_penalty']} {curse_abbreviation}."
            if event.get("curse_stat") and int(event.get("curse_penalty") or 0) < 0 else ""
        )
        authoritative.append(
            f"{event['actor']} otrzymuje „{event['item']}”{money}; "
            f"przedmiot zapisano w ekwipunku.{curse}"
        )
    for event in empty_events:
        authoritative.append(
            "Przeszukanie nie przynosi łupu." if event.get("reason") == "empty"
            else "Przeszukanie kończy się niepowodzeniem; w tej lokacji nie można ponowić próby."
        )
    return strip_loot_claims(narration, world_pack, events) + (
        "\n\n" + " ".join(authoritative) if authoritative else ""
    )


def _choose_recipient(
    candidates: list[Character],
    last_loot_character_id: int | None,
) -> Character | None:
    unique = list({character.id: character for character in candidates}.values())
    if len(unique) > 1:
        without_last = [character for character in unique if character.id != last_loot_character_id]
        if without_last:
            unique = without_last
    if not unique:
        return None
    return unique[secrets.randbelow(len(unique))]


def _preferred_stat(character: Character, world_pack: WorldPack) -> str:
    class_value = character.class_id or character.character_class
    try:
        class_definition = WORLD_PACK_REGISTRY.get_class(world_pack, class_value)
    except LookupError:
        class_definition = WORLD_PACK_REGISTRY.resolve_class(world_pack, class_value)
    return class_definition.primary_stat


def _roll_rarity(
    world_pack: WorldPack,
    *,
    boss_reward: bool,
    critical_search: bool,
) -> LootRarityDefinition:
    roll = secrets.randbelow(100)
    cumulative = 0
    reward = boss_reward or critical_search
    for rarity in world_pack.loot_rarities:
        cumulative += rarity.reward_weight if reward else rarity.normal_weight
        if roll < cumulative:
            return rarity
    return world_pack.loot_rarities[-1]


def _build_random_loot(
    recipient: Character,
    world_pack: WorldPack,
    *,
    boss_reward: bool = False,
    critical_search: bool = False,
) -> InventoryItem:
    rarity = _roll_rarity(
        world_pack,
        boss_reward=boss_reward,
        critical_search=critical_search,
    )
    # Mikstury pozostają użytecznym, lecz rzadszym wynikiem losowania.
    consumable = world_pack.consumable_loot
    if secrets.randbelow(consumable.chance_denominator) == 0:
        healing = min(
            consumable.healing_cap,
            consumable.base_healing
            + recipient.level * consumable.healing_per_level
            + rarity.rank * consumable.healing_per_rarity,
        )
        return InventoryItem(
            character_id=recipient.id,
            name=f"{consumable.name} {rarity.suffix}",
            description=consumable.description_template.format(healing=healing),
            item_type="consumable",
            target_stat="none",
            stat_bonus=healing,
            damage_power=0,
            hands_required=1,
            is_equipped=False,
            quantity=1,
        )

    target_stat = _preferred_stat(recipient, world_pack)
    table = next(table for table in world_pack.loot_tables if table.id == target_stat)
    template = table.entries[secrets.randbelow(len(table.entries))]
    level_cap = min(5, 2 + max(0, recipient.level - 1) // 5)
    stat_bonus = min(rarity.rank, level_cap)
    cursed = secrets.randbelow(12) == 0
    if cursed:
        stat_bonus = max(2, stat_bonus)
    curse_stat = ("charisma" if target_stat != "charisma" else "strength") if cursed else None
    curse_abbreviation = next(
        (attribute.abbreviation for attribute in world_pack.attributes
         if attribute.id == curse_stat),
        "",
    )
    damage_power = 0
    if template.item_type == "weapon":
        damage_bonus_cap = min(3, max(0, recipient.level - 1) // 5)
        damage_power = (
            (6 if template.hands_required == 2 else 4)
            + min(max(0, rarity.rank - 1), damage_bonus_cap)
        )
    return InventoryItem(
        character_id=recipient.id,
        name=f"{template.label} {rarity.suffix}" + (" (przeklęty)" if cursed else ""),
        description=template.description + (
            f" Klątwa: -1 {curse_abbreviation} podczas noszenia." if cursed else ""
        ),
        item_type=template.item_type,
        target_stat=target_stat,
        stat_bonus=stat_bonus,
        curse_stat=curse_stat,
        curse_penalty=-1 if cursed else 0,
        damage_power=damage_power,
        hands_required=template.hands_required,
        is_equipped=False,
        quantity=1,
    )


def _build_crafted_item(
    character: Character,
    sources: list[InventoryItem],
    world_pack: WorldPack,
) -> InventoryItem:
    best = max(sources, key=lambda item: (int(item.stat_bonus or 0), int(item.id or 0)))
    target_stats = [item.target_stat for item in sources if item.target_stat != "none"]
    target_stat = Counter(target_stats).most_common(1)[0][0] if target_stats else _preferred_stat(character, world_pack)
    source_bonus = max(int(item.stat_bonus or 0) for item in sources)
    level_cap = min(5, 2 + max(0, character.level - 1) // 5)
    stat_bonus = min(source_bonus + 1, max(source_bonus, level_cap))
    hands_required = max(int(item.hands_required or 1) for item in sources) if best.item_type == "weapon" else 1
    damage_power = 0
    if best.item_type == "weapon":
        source_power = max(_item_damage_power(item) for item in sources)
        damage_cap = (6 if hands_required == 2 else 4) + min(3, max(0, character.level - 1) // 5)
        damage_power = min(source_power + 1, max(source_power, damage_cap))
    stat_labels = {attribute.id: attribute.label.casefold() for attribute in world_pack.attributes}
    stat_labels.update({"hp_max": "żywotność", "none": "skuteczność"})
    crafting_profile = world_pack.crafting_profile
    return InventoryItem(
        character_id=character.id,
        name=f"{crafting_profile.result_prefix}: {best.name}",
        description=crafting_profile.description_template.format(
            stat_label=stat_labels.get(target_stat, "skuteczność")
        ),
        item_type=best.item_type,
        target_stat=target_stat,
        stat_bonus=stat_bonus,
        damage_power=damage_power,
        hands_required=hands_required,
        is_equipped=False,
        quantity=1,
    )


def _item_damage_power(item: InventoryItem) -> int:
    configured = int(item.damage_power or 0)
    if configured > 0:
        return configured
    if item.item_type == "weapon":
        return 6 if int(item.hands_required or 1) == 2 else 4
    return 0
