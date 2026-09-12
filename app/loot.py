import re
import secrets
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from app.models import CampaignMap, Character, GameSession, InventoryItem, Turn


CRAFTING_KEYWORDS = (
    "scal", "ulepsz", "przekuw", "przerab", "wytwarz",
)
AMBIGUOUS_CRAFTING_KEYWORDS = ("lacz", "polacz", "wzmacn")
CRAFTING_OBJECT_KEYWORDS = (
    "przedmiot", "skladnik", "ekwipun", "bron", "miecz", "sztylet", "topor", "luk",
    "kostur", "zbroj", "pancerz", "tarc", "amulet", "piersc", "relik", "helm", "but",
)
LOOT_SEARCH_KEYWORDS = (
    "przeszuk", "pladruj", "ograb", "szukam lupu", "szukam przedmiot", "zbieram lup",
    "sprawdzam cial", "przegladam cial", "otwieram skrzyn", "przeswietlam skrzyn",
)
COMBAT_ACTION_KEYWORDS = (
    "atak", "uderz", "strzel", "tne", "cios", "bronie", "oslaniam", "lecze", "wspieram",
)
MOVEMENT_ACTION_KEYWORDS = (
    "ide", "idziemy", "wchodze", "przechodze", "ruszam", "uciekam", "odwrot",
)
CRAFTABLE_ITEM_TYPES = {"weapon", "shield", "armor", "accessory", "misc"}
CRAFTING_SUCCESS_TIERS = {"partial_success", "success", "critical_success"}
LOOT_SUCCESS_TIERS = {"success", "critical_success"}


@dataclass
class InventoryResolution:
    new_items: list[InventoryItem] = field(default_factory=list)
    consumed_items: list[InventoryItem] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)


LOOT_TEMPLATES = {
    "strength": (
        ("weapon", "Miecz Najemnika", "Dobrze wyważone ostrze nie cofa się przed pancerzem.", 1),
        ("weapon", "Topór Strażnika", "Ciężkie ostrze pomaga przełamywać obronę przeciwnika.", 2),
        ("armor", "Pancerz Łuskowy", "Nachodzące na siebie płytki rozpraszają siłę uderzeń.", 1),
        ("accessory", "Karwasz Siłacza", "Usztywnia nadgarstek podczas mocnych cięć i pchnięć.", 1),
    ),
    "agility": (
        ("weapon", "Sztylet Zwiadowcy", "Lekkie ostrze błyskawicznie odnajduje luki w obronie.", 1),
        ("weapon", "Łuk Popielnego Gaju", "Sprężyste ramiona łuku pomagają posyłać celne strzały.", 2),
        ("armor", "Płaszcz Cichego Kroku", "Miękki materiał tłumi ruch i nie krępuje uników.", 1),
        ("accessory", "Pierścień Refleksu", "Chłodny metal wyostrza reakcję w chwili zagrożenia.", 1),
    ),
    "intellect": (
        ("weapon", "Kostur Zgaszonej Runy", "Przewodzi skupioną energię przez wyryte w drewnie znaki.", 2),
        ("accessory", "Soczewka Arkanisty", "Ułatwia dostrzeganie wzorów ukrytych w magii i materii.", 1),
        ("accessory", "Amulet Szeptów", "Pomaga zachować jasność myśli pośród nadnaturalnego chaosu.", 1),
        ("misc", "Kodeks Popiołów", "Zapisane marginesy podpowiadają rozwiązania dawnych zagadek.", 1),
    ),
    "charisma": (
        ("weapon", "Buława Pielgrzyma", "Ceremonialny oręż dodaje powagi słowom właściciela.", 1),
        ("accessory", "Sygnet Poselstwa", "Stary herb wzbudza respekt nawet u nieufnych rozmówców.", 1),
        ("armor", "Płaszcz Chorążego", "Wyprostowana sylwetka przyciąga wzrok sprzymierzeńców.", 1),
        ("misc", "Relikwiarz Przysięgi", "Przypomina słuchaczom, że wypowiedziane obietnice mają wagę.", 1),
    ),
}


def normalize_game_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _has_token_stem(value: str, stems: Iterable[str]) -> bool:
    tokens = re.findall(r"[a-z0-9]+", normalize_game_text(value))
    return any(token.startswith(stem) for token in tokens for stem in stems)


def has_crafting_intent(action_text: str) -> bool:
    if _has_token_stem(action_text, CRAFTING_KEYWORDS):
        return True
    return (
        _has_token_stem(action_text, AMBIGUOUS_CRAFTING_KEYWORDS)
        and _has_token_stem(action_text, CRAFTING_OBJECT_KEYWORDS)
    )


def has_loot_search_intent(action_text: str) -> bool:
    normalized = normalize_game_text(action_text)
    return (
        _has_token_stem(action_text, ("przeszuk", "pladruj", "ograb"))
        or any(keyword in normalized for keyword in LOOT_SEARCH_KEYWORDS)
    )


def infer_crafting_source_items(
    action_text: str,
    inventory: Iterable[InventoryItem],
) -> list[InventoryItem]:
    """Rozpoznaje konkretne, trwałe przedmioty wymienione w deklaracji craftingu."""
    if not has_crafting_intent(action_text):
        return []

    normalized_action = normalize_game_text(action_text)
    inventory_items = [item for item in inventory if item.item_type in CRAFTABLE_ITEM_TYPES]
    ignored_name_parts = {
        "magicz", "runicz", "starozy", "wzmocn", "krasnol", "mistrz", "ognia", "cienia",
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
) -> str | None:
    crafting = has_crafting_intent(action_text)
    searching = has_loot_search_intent(action_text)

    if crafting and searching:
        return "Jedna tura obejmuje jeden główny zamiar. Wybierz crafting albo przeszukiwanie."
    if uses_magic and (crafting or searching):
        return "Rzucenie zdolności, crafting i przeszukiwanie są osobnymi akcjami. Wybierz jedną z nich."
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
        if int(session.crafting_available_until_turn or 0) != current_turn_number:
            return "Warsztat jest niedostępny. Crafting otwiera się na jedną turę po pokonaniu bossa."
        sources = infer_crafting_source_items(action_text, inventory)
        if len(sources) != 3:
            return "Crafting wymaga wskazania w akcji dokładnie trzech posiadanych przedmiotów."
        item_types = {item.item_type for item in sources}
        if len(item_types) != 1:
            return "Scalić można tylko trzy przedmioty tego samego typu."
    return None


def resolve_inventory_mechanics(
    session: GameSession,
    turn: Turn,
    characters: list[Character],
    campaign_map: CampaignMap | None,
) -> InventoryResolution:
    resolution = InventoryResolution()
    boss_defeated = any(
        isinstance(event, dict) and event.get("type") == "boss_defeated"
        for event in (turn.combat_events or [])
    )

    for action in turn.actions:
        if not has_crafting_intent(action.action_text):
            continue
        if (
            boss_defeated
            or (session.active_boss_name and (session.active_boss_hp or 0) > 0)
            or int(session.crafting_available_until_turn or 0) != turn.turn_number
        ):
            continue
        character = next((item for item in characters if item.id == action.character_id), None)
        if not character or action.outcome_tier not in CRAFTING_SUCCESS_TIERS:
            continue
        sources = infer_crafting_source_items(action.action_text, character.inventory)
        if len(sources) != 3 or len({item.item_type for item in sources}) != 1:
            continue
        crafted = _build_crafted_item(character, sources)
        resolution.new_items.append(crafted)
        for source in sources:
            if source.quantity > 1:
                source.quantity -= 1
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
        session.crafting_available_until_turn = turn.turn_number + 1
        recipient = _choose_recipient(
            [character for character in characters if character.is_alive],
            session.last_loot_character_id,
        )
        if recipient:
            item = _build_random_loot(recipient, boss_reward=True)
            resolution.new_items.append(item)
            session.last_loot_character_id = recipient.id
            resolution.events.append({
                "type": "item_found",
                "source": "boss",
                "actor": recipient.name,
                "item": item.name,
                "stat_bonus": item.stat_bonus,
            })
        return resolution

    search_actions = [
        action for action in turn.actions if has_loot_search_intent(action.action_text)
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

    successful_characters = [
        character
        for action in search_actions
        for character in characters
        if character.id == action.character_id
        and character.is_alive
        and action.outcome_tier in LOOT_SUCCESS_TIERS
    ]
    finder = _choose_recipient(successful_characters, None)
    if not finder:
        resolution.events.append({"type": "loot_search_empty", "location_id": node_id})
        return resolution

    critical = any(
        action.character_id == finder.id and action.outcome_tier == "critical_success"
        for action in search_actions
    )
    recipient = _choose_recipient(
        [character for character in characters if character.is_alive],
        session.last_loot_character_id,
    )
    if not recipient:
        return resolution
    item = _build_random_loot(recipient, critical_search=critical)
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
    })
    return resolution


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


def _preferred_stat(character: Character) -> str:
    class_name = normalize_game_text(character.character_class)
    if any(label in class_name for label in ("lotr", "zaboj", "zlodziej", "lucz")):
        return "agility"
    if any(label in class_name for label in ("mag", "czaro", "druid")):
        return "intellect"
    if any(label in class_name for label in ("kapl", "klery", "bard", "palad")):
        return "charisma"
    return "strength"


def _roll_rarity(*, boss_reward: bool, critical_search: bool) -> tuple[str, int]:
    roll = secrets.randbelow(100)
    if boss_reward or critical_search:
        if roll < 15:
            return "z Echem Reliktu", 3
        if roll < 70:
            return "z Runicznym Splotem", 2
        return "z Żelaznego Szlaku", 1
    if roll < 5:
        return "z Echem Reliktu", 3
    if roll < 30:
        return "z Runicznym Splotem", 2
    return "z Żelaznego Szlaku", 1


def _build_random_loot(
    recipient: Character,
    *,
    boss_reward: bool = False,
    critical_search: bool = False,
) -> InventoryItem:
    rarity_suffix, rarity_rank = _roll_rarity(
        boss_reward=boss_reward,
        critical_search=critical_search,
    )
    # Mikstury pozostają użytecznym, lecz rzadszym wynikiem losowania.
    if secrets.randbelow(7) == 0:
        healing = min(30, 8 + recipient.level * 2 + rarity_rank * 2)
        return InventoryItem(
            character_id=recipient.id,
            name=f"Eliksir Żywotności {rarity_suffix}",
            description=f"Odnawia {healing} punktów życia.",
            item_type="consumable",
            target_stat="none",
            stat_bonus=healing,
            damage_power=0,
            hands_required=1,
            is_equipped=False,
            quantity=1,
        )

    target_stat = _preferred_stat(recipient)
    templates = LOOT_TEMPLATES[target_stat]
    item_type, base_name, description, hands_required = templates[secrets.randbelow(len(templates))]
    level_cap = min(5, 2 + max(0, recipient.level - 1) // 5)
    stat_bonus = min(rarity_rank, level_cap)
    damage_power = 0
    if item_type == "weapon":
        damage_bonus_cap = min(3, max(0, recipient.level - 1) // 5)
        damage_power = (
            (6 if hands_required == 2 else 4)
            + min(max(0, rarity_rank - 1), damage_bonus_cap)
        )
    return InventoryItem(
        character_id=recipient.id,
        name=f"{base_name} {rarity_suffix}",
        description=description,
        item_type=item_type,
        target_stat=target_stat,
        stat_bonus=stat_bonus,
        damage_power=damage_power,
        hands_required=hands_required,
        is_equipped=False,
        quantity=1,
    )


def _build_crafted_item(character: Character, sources: list[InventoryItem]) -> InventoryItem:
    best = max(sources, key=lambda item: (int(item.stat_bonus or 0), int(item.id or 0)))
    target_stats = [item.target_stat for item in sources if item.target_stat != "none"]
    target_stat = Counter(target_stats).most_common(1)[0][0] if target_stats else _preferred_stat(character)
    source_bonus = max(int(item.stat_bonus or 0) for item in sources)
    level_cap = min(5, 2 + max(0, character.level - 1) // 5)
    stat_bonus = min(source_bonus + 1, max(source_bonus, level_cap))
    hands_required = max(int(item.hands_required or 1) for item in sources) if best.item_type == "weapon" else 1
    damage_power = 0
    if best.item_type == "weapon":
        source_power = max(_item_damage_power(item) for item in sources)
        damage_cap = (6 if hands_required == 2 else 4) + min(3, max(0, character.level - 1) // 5)
        damage_power = min(source_power + 1, max(source_power, damage_cap))
    stat_labels = {
        "strength": "siłę",
        "agility": "zręczność",
        "intellect": "intelekt",
        "charisma": "charyzmę",
        "hp_max": "żywotność",
        "none": "skuteczność",
    }
    return InventoryItem(
        character_id=character.id,
        name=f"Ulepszenie: {best.name}",
        description=f"Rzemieślnicze wzmocnienie poprawia {stat_labels.get(target_stat, 'skuteczność')} przedmiotu.",
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
