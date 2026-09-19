"""Controlled declarative shorthand expanded into the immutable WorldPack contract."""

from typing import Literal

from pydantic import Field, model_validator

from app.worlds.models import (
    ActionIntent,
    AttributeId,
    TerminologyDefinition,
    WorldModel,
    WorldPack,
)


CANONICAL_STATS = ("strength", "agility", "intellect", "charisma", "perception")
STAT_LABELS = (
    ("Siła", "STR", "Krzepa, wytrzymałość i fizyczny nacisk."),
    ("Zręczność", "AGI", "Refleks, precyzja i skradanie."),
    ("Intelekt", "INT", "Wiedza, analiza i rozwiązywanie problemów."),
    ("Charyzma", "CHA", "Wpływ, rozmowa i przywództwo."),
    ("Percepcja", "PER", "Czujność i wykrywanie śladów, odrębne od ich analizy."),
)
ABILITY_INTENT = {
    "damage": "attack", "heal": "support", "scan": "interact",
    "jam": "interact", "protect": "defend", "move": "other",
    "support": "support",
}
STATUS_PRESENTATIONS = (
    ("burning", "Oparzony", "🔥", "orange", "Obrażenia na początku kolejnej tury."),
    ("poisoned", "Zatruty", "☣", "green", "Obrażenia i kara do testów."),
    ("frozen", "Unieruchomiony", "❄", "cyan", "Obniżona obrona."),
    ("stunned", "Oszołomiony", "✦", "yellow", "Słabsza odpowiedź na kolejny atak."),
    ("exposed", "Odsłonięty", "◎", "rose", "Otrzymuje o 25% więcej obrażeń."),
    ("guarded", "Osłonięty", "▣", "blue", "Redukuje następne obrażenia."),
    ("enraged", "Zdesperowany", "⚠", "rose", "Ataki głównego zagrożenia są silniejsze."),
)


class RecipePalette(WorldModel):
    background: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    surface: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    raised: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    primary: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    danger: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accent: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class RecipeAbility(WorldModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=2)
    description: str = Field(min_length=2)
    mechanic: Literal["damage", "heal", "scan", "jam", "protect", "move", "support"]
    level: int = Field(default=1, ge=1, le=25)
    stat: AttributeId | None = None


class RecipeClass(WorldModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=2)
    icon: str = Field(min_length=1)
    stat: AttributeId
    weapon: str = Field(min_length=2)
    weapon_stat: AttributeId = "agility"
    tool: str = Field(min_length=2)
    book: str = Field(min_length=2)
    quick_action: str = Field(min_length=2)
    quick_intent: ActionIntent = "other"
    abilities: tuple[RecipeAbility, ...] = Field(min_length=2)


class RecipePlace(WorldModel):
    name: str = Field(min_length=2)
    description: str = Field(min_length=2)
    icon: str = Field(min_length=1, max_length=2)


class RecipePlaces(WorldModel):
    start: RecipePlace
    finale: RecipePlace
    main: tuple[RecipePlace, ...] = Field(min_length=6)
    branches: tuple[RecipePlace, ...] = Field(min_length=3)


class RecipeEnemy(WorldModel):
    role: str = Field(min_length=2)
    plural: str = Field(min_length=2)
    icon: str = Field(min_length=1)
    description: str = Field(min_length=2)
    features: tuple[str, str, str]
    attacks: tuple[str, str, str]


class WorldRecipe(WorldModel):
    format: Literal["recipe_v1"]
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: int = Field(ge=1)
    display_name: str = Field(min_length=2)
    terminology: TerminologyDefinition
    palette: RecipePalette
    typography_id: Literal["classic", "modern"]
    texture_id: Literal["runes", "grid", "none"]
    shape_id: Literal["rounded", "cut_corner"] = "rounded"
    setting_theme: str = Field(min_length=2)
    title: str = Field(min_length=2)
    scenarios: tuple[str, ...] = Field(min_length=3)
    intro: str = Field(min_length=30)
    first_challenge: str = Field(min_length=10)
    narrator: str = Field(min_length=30)
    art_direction: str = Field(min_length=10)
    image_prompt: str = Field(min_length=10)
    enemy: RecipeEnemy
    places: RecipePlaces
    classes: tuple[RecipeClass, ...] = Field(min_length=3)
    loot_names: tuple[str, str, str, str, str]
    consumable: str = Field(min_length=2)
    rarity_suffix: str = Field(min_length=2)
    crafting_venue: str = Field(min_length=2)
    peaceful: bool = False

    @model_validator(mode="after")
    def validate_recipe(self) -> "WorldRecipe":
        class_ids = [item.id for item in self.classes]
        if len(class_ids) != len(set(class_ids)):
            raise ValueError("recipe class ids must be unique")
        for item in self.classes:
            ability_ids = [ability.id for ability in item.abilities]
            if len(ability_ids) != len(set(ability_ids)):
                raise ValueError(f"recipe ability ids must be unique in {item.id}")
        return self


def _room(place: RecipePlace, room_id: str, *, branch: bool = False) -> dict:
    return {
        "id": room_id, "label": place.name, "icon": place.icon,
        "names": [place.name], "description": place.description,
        "contents": [place.description], "branch": branch,
    }


def _ability_action(name: str, mechanic: str) -> str:
    ending = {
        "damage": "przeciw głównemu zagrożeniu.",
        "heal": "aby pomóc wskazanemu sojusznikowi.",
        "scan": "aby odkryć ukryte informacje.",
        "jam": "aby zakłócić działanie zagrożenia.",
        "protect": "aby przygotować własną obronę.",
        "move": "aby zmienić pozycję.",
        "support": "aby wesprzeć wskazanego sojusznika.",
    }[mechanic]
    return f"Stosuję zdolność {name} {ending}"


def materialize_recipe(recipe: WorldRecipe) -> WorldPack:
    """Build a complete pack with closed, reusable d20 mechanics; then validate it."""
    palette = recipe.palette
    colors = {
        "background": palette.background, "surface": palette.surface,
        "surface_raised": palette.raised, "primary": palette.primary,
        "danger": palette.danger, "text": "#edf4f5",
        "text_muted": "#b9c9cf", "border": palette.primary,
        "focus": "#ffe188", "success": "#70dcaa",
        "accent": palette.accent, "hp": palette.danger, "xp": "#e9ce70",
    }
    classes = []
    abilities = []
    weapon_nouns: set[str] = set()
    for class_definition in recipe.classes:
        weapon_nouns.add(class_definition.weapon.split()[0].casefold())
        ability_ids = []
        for ability in class_definition.abilities:
            ability_id = f"{class_definition.id}_{ability.id}"
            ability_ids.append(ability_id)
            mechanic = ability.mechanic
            abilities.append({
                "id": ability_id, "name": ability.name,
                "category": class_definition.book,
                "required_level": ability.level, "icon": class_definition.icon,
                "description": ability.description,
                "action_text": _ability_action(ability.name, mechanic),
                "intent": ABILITY_INTENT[mechanic],
                "tested_stat": ability.stat or class_definition.stat,
                "target_ref": "boss" if mechanic == "damage" else None,
                "mechanic_key": mechanic,
            })
        classes.append({
            "id": class_definition.id, "name": class_definition.name,
            "icon": class_definition.icon, "primary_stat": class_definition.stat,
            "aliases": [],
            "starter_items": [
                {"name": class_definition.weapon,
                 "description": f"Podstawowe wyposażenie: {class_definition.weapon}.",
                 "item_type": "weapon", "target_stat": class_definition.weapon_stat,
                 "stat_bonus": 1, "is_equipped": True},
                {"name": class_definition.tool,
                 "description": f"Narzędzie profesji: {class_definition.tool}.",
                 "item_type": "accessory", "target_stat": class_definition.stat,
                 "stat_bonus": 1, "is_equipped": True},
                {"name": recipe.consumable, "description": "Odnawia 10 punktów życia.",
                 "item_type": "consumable", "target_stat": "none", "stat_bonus": 10},
            ],
            "quick_actions": [
                {"id": f"{class_definition.id}-approach", "label": class_definition.name,
                 "icon": class_definition.icon, "action_text": class_definition.quick_action,
                 "intent": class_definition.quick_intent,
                 "tested_stat": class_definition.stat,
                 "target_ref": "boss" if class_definition.quick_intent == "attack" else None},
                {"id": f"{class_definition.id}-observe", "label": "Rozejrzyj się",
                 "icon": "◎", "action_text": "Uważnie obserwuję otoczenie i szukam ukrytych śladów.",
                 "intent": "interact", "tested_stat": "perception"},
            ],
            "ability_book": {
                "kind": f"{class_definition.id}_manual", "title": class_definition.book,
                "icon": class_definition.icon, "resource_label": "Zdolności",
                "casting_stat": class_definition.stat, "ability_ids": ability_ids,
                "action_markers": [ability.name for ability in class_definition.abilities],
            },
        })
    for name in recipe.loot_names[:2]:
        weapon_nouns.add(name.split()[0].casefold())
    loot_tables = [
        {"id": stat, "entries": [{
            "id": f"loot_{stat}", "label": recipe.loot_names[index],
            "description": f"Znalezisko ze świata {recipe.display_name}.",
            "item_type": "weapon" if index < 2 else "accessory",
            "target_stat": stat,
        }]}
        for index, stat in enumerate(CANONICAL_STATS)
    ]
    map_rooms = [
        _room(recipe.places.start, "entrance"),
        _room(recipe.places.finale, "finale"),
        *(_room(place, f"site_{index}") for index, place in enumerate(recipe.places.main, 1)),
        *(_room(place, f"branch_{index}", branch=True)
          for index, place in enumerate(recipe.places.branches, 1)),
    ]
    enemy = recipe.enemy
    feature_stats = ("strength", "intellect", "agility")
    feature_effects = ("stunned", "exposed", "guarded")
    features = [
        {"id": f"feature_{index}", "name": name, "icon": ("⚡", "◎", "▣")[index - 1],
         "description": f"{name} zmienia przebieg starcia.",
         "required_stat": feature_stats[index - 1], "dc_offset": 0,
         "damage_percent": 10 if index == 1 else 0,
         "effect": feature_effects[index - 1], "reusable": index == 3}
        for index, name in enumerate(enemy.features, 1)
    ]
    attacks = [
        {"phase": index, "name": name, "icon": "⚠",
         "description": f"{enemy.role.capitalize()} przygotowuje: {name}."}
        for index, name in enumerate(enemy.attacks, 1)
    ]
    vocabulary = [
        {"id": f"weapon_{index}", "label": noun.capitalize(),
         "aliases": [noun], "item_types": ["weapon"]}
        for index, noun in enumerate(sorted(weapon_nouns), 1)
    ]
    pack_data = {
        "id": recipe.id, "version": recipe.version,
        "display_name": recipe.display_name, "ruleset_id": "d20_v1",
        "terminology": recipe.terminology.model_dump(mode="json"),
        "attributes": [
            {"id": stat, "label": label, "abbreviation": abbreviation,
             "description": description}
            for stat, (label, abbreviation, description) in zip(CANONICAL_STATS, STAT_LABELS)
        ],
        "action_stat_cues": [],
        "theme_id": recipe.id,
        "theme": {"id": recipe.id, "color_scheme": "dark",
                  "typography_id": recipe.typography_id,
                  "texture_id": recipe.texture_id,
                  "icon_set_id": "neutral", "shape_id": recipe.shape_id,
                  "tokens": [{"id": key, "value": value} for key, value in colors.items()]},
        "classes": classes, "fallback_class_id": classes[0]["id"],
        "abilities": abilities, "loot_tables": loot_tables,
        "loot_rarities": [
            {"id": "common", "suffix": recipe.rarity_suffix, "rank": 1,
             "normal_weight": 70, "reward_weight": 30},
            {"id": "rare", "suffix": f"wyjątkowy {recipe.rarity_suffix}", "rank": 2,
             "normal_weight": 25, "reward_weight": 55},
            {"id": "relic", "suffix": f"legendarny {recipe.rarity_suffix}", "rank": 3,
             "normal_weight": 5, "reward_weight": 15},
        ],
        "consumable_loot": {"name": recipe.consumable,
                            "description_template": "Odnawia {healing} punktów życia.",
                            "chance_denominator": 7, "base_healing": 8,
                            "healing_per_level": 2, "healing_per_rarity": 2,
                            "healing_cap": 30},
        "crafting_profile": {
            "result_prefix": "Ulepszenie",
            "description_template": f"Praca w miejscu {recipe.crafting_venue} poprawia {{stat_label}} przedmiotu.",
            "workshop_unavailable_message": "Ulepszanie jest teraz niedostępne. Można je rozpocząć przez jedną turę po pokonaniu głównego zagrożenia.",
            "object_markers": sorted(weapon_nouns),
        },
        "item_vocabulary": vocabulary,
        "attack_status_cues": [
            {"markers": ["ogien", "plomien", "termicz"], "status_effect": "burning"},
            {"markers": ["truciz", "toksyn", "jad"], "status_effect": "poisoned"},
            {"markers": ["mroz", "lod", "chlod"], "status_effect": "frozen"},
        ],
        "status_presentations": [
            {"id": status_id, "label": label, "icon": icon,
             "tone": tone, "description": description}
            for status_id, label, icon, tone, description in STATUS_PRESENTATIONS
        ],
        "enemy_profile": {
            "id": "major_threat", "role_label": enemy.role,
            "role_label_plural": enemy.plural, "icon": enemy.icon,
            "lore_category_id": "boss", "defeated_label": "pokonany",
            "active_label": "aktywny", "next_attack_label": "Następne zagrożenie",
            "manual_trigger_description": enemy.description,
            "status_labels": ["aktywny", "osłabiony", "pokonany"],
            "default_status_effect": "burning",
            "features": features, "attacks": attacks,
        },
        "map_profile": {
            "generator_id": f"{recipe.id}_journey", "generator_version": 1,
            "start_location_name": recipe.places.start.name,
            "finale_location_name": recipe.places.finale.name,
            "hidden_location_name": recipe.places.branches[0].name,
            "undiscovered_location_name": "Nieodkryte miejsce",
            "room_types": map_rooms,
        },
        "lore_categories": [
            {"id": "boss", "label": enemy.plural.capitalize(), "icon": enemy.icon},
            {"id": "location", "label": "Miejsca", "icon": "◇"},
            {"id": "npc", "label": "Spotkane postaci", "icon": "◈"},
            {"id": "weapon", "label": "Przedmioty i znaleziska", "icon": "▸"},
            {"id": "attack", "label": "Akcje grupy", "icon": "⚡"},
        ],
        "narrative_profile": {
            "default_title": recipe.title, "setting_theme": recipe.setting_theme,
            "lobby_title_template": "Przygoda: {scenario_type}",
            "lobby_prompt": recipe.first_challenge,
            "scenario_options": list(recipe.scenarios),
            "lobby_empty_message": "Grupa jeszcze się nie zebrała.",
            "lobby_ready_message": "Wszyscy gotowi. Można rozpocząć przygodę.",
            "character_selection_heading": "WYBIERZ POSTAĆ",
            "first_character_message": "Stwórz pierwszą postać, aby rozpocząć.",
            "lobby_create_first_message": "Stwórz pierwszą postać",
            "named_weapon_description_template": "Przedmiot nazwany przez {character_name}.",
            "named_weapon_target_stat": "agility",
            "party_presence_prefix": "W przygodzie uczestniczą:",
            "prologue_party_noun": "grupy", "prologue_character_noun": "uczestnika",
            "prologue_action_qualifier": "niespecjalne",
            "loot_search_action": {
                "id": "search-supplies", "label": "Szukaj zasobów", "icon": "▤",
                "action_text": "Uważnie przeszukuję okolicę w poszukiwaniu przydatnych rzeczy.",
                "intent": "interact", "tested_stat": "perception"},
            "loot_search_markers": ["przeszuk", "szukam przedmiot", "zbieram lup", "szukam zasob"],
            "campaign_intro": recipe.intro,
            "first_challenge": recipe.first_challenge,
            "suggested_actions": [
                "◎ Rozejrzyj się i wypatrz wskazówki.",
                "◈ Porozmawiaj z kimś, kto zna to miejsce.",
                "▸ Podejmij działanie i zmień sytuację.",
            ],
            "image_art_direction": recipe.art_direction,
            "initial_image_prompt": recipe.image_prompt,
            "narrator_instructions": recipe.narrator,
            "offline_resolution_close": "Otoczenie reaguje na wybory grupy, a sytuacja się zmienia.",
            "offline_next_challenge": recipe.first_challenge,
            "offline_suggested_actions": [
                "◎ Zbadaj nowy ślad.", "◈ Porozmawiaj i poszukaj wsparcia.",
                "▸ Wykorzystaj okazję do działania.",
            ],
            "offline_enemy_description": enemy.description,
            "offline_enemy_naming_prompt": f"Jak nazwiesz zagrożenie: {enemy.description}?",
            "offline_auto_enemy_naming": not recipe.peaceful,
        },
    }
    return WorldPack.model_validate(pack_data)
