"""Immutable, declarative contracts for versioned campaign worlds."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


Identifier = str
AttributeId = Literal[
    "strength",
    "agility",
    "intellect",
    "charisma",
    "perception",
]
ActionIntent = Literal["attack", "defend", "support", "interact", "other"]
MechanicKey = Literal[
    "damage",
    "heal",
    "revive",
    "scan",
    "jam",
    "protect",
    "cleanse",
    "move",
    "support",
]
ItemType = Literal["weapon", "shield", "armor", "accessory", "consumable", "misc"]
ItemTargetStat = AttributeId | Literal["none", "hp_max", "all"]
ThemeTokenId = Literal[
    "background", "surface", "surface_raised", "primary", "danger", "text",
    "text_muted", "border", "focus", "success", "accent", "hp", "xp",
]
StatusId = Literal[
    "burning", "poisoned", "frozen", "stunned", "exposed", "guarded", "enraged"
]


class WorldModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AttributeDefinition(WorldModel):
    id: AttributeId
    label: str = Field(min_length=1)
    abbreviation: str = Field(min_length=2, max_length=4)
    description: str = Field(min_length=1)


class ActionStatCue(WorldModel):
    marker: str = Field(min_length=2)
    stat: AttributeId
    weight: int = Field(ge=1, le=4)


class StarterItemDefinition(WorldModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    item_type: ItemType
    target_stat: ItemTargetStat
    stat_bonus: int = 0
    damage_power: int = Field(default=0, ge=0)
    hands_required: int = Field(default=1, ge=0, le=2)
    is_equipped: bool = False


class QuickActionDefinition(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    label: str = Field(min_length=1)
    icon: str = Field(min_length=1)
    action_text: str = Field(min_length=1)
    intent: ActionIntent
    tested_stat: AttributeId
    target_ref: str | None = None


class AbilityBookDefinition(WorldModel):
    kind: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    title: str = Field(min_length=1)
    icon: str = Field(min_length=1)
    resource_label: str = Field(min_length=1)
    casting_stat: AttributeId
    ability_ids: tuple[Identifier, ...]
    action_markers: tuple[str, ...] = ()


class WorldClassDefinition(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    icon: str = Field(min_length=1)
    primary_stat: AttributeId
    starter_items: tuple[StarterItemDefinition, ...]
    quick_actions: tuple[QuickActionDefinition, ...]
    ability_book: AbilityBookDefinition | None = None


class MechanicParameter(WorldModel):
    key: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    value: str | int | float | bool


class AbilityDefinition(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    required_level: int = Field(ge=1, le=25)
    icon: str = Field(min_length=1)
    description: str = Field(min_length=1)
    action_text: str = Field(min_length=1)
    intent: ActionIntent
    tested_stat: AttributeId
    target_ref: str | None = None
    mechanic_key: MechanicKey
    mechanic_params: tuple[MechanicParameter, ...] = ()
    aliases: tuple[str, ...] = ()


class TerminologyDefinition(WorldModel):
    campaign: str
    hero: str
    party: str
    ability_book: str
    enemy: str
    location: str


class ThemeToken(WorldModel):
    id: ThemeTokenId
    value: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class ThemeProfile(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    color_scheme: Literal["dark", "light"]
    typography_id: Literal["classic", "modern"]
    texture_id: Literal["runes", "grid", "none"]
    icon_set_id: Literal["classic", "neutral"]
    shape_id: Literal["rounded", "cut_corner"] = "rounded"
    tokens: tuple[ThemeToken, ...]


class StatusPresentationDefinition(WorldModel):
    id: StatusId
    label: str = Field(min_length=1)
    icon: str = Field(min_length=1)
    description: str = Field(min_length=1)
    tone: Literal["orange", "green", "cyan", "yellow", "rose", "blue", "neutral"]


class LootTableEntry(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    item_type: ItemType
    target_stat: ItemTargetStat
    hands_required: int = Field(default=1, ge=0, le=2)


class LootTableDefinition(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    entries: tuple[LootTableEntry, ...]


class LootRarityDefinition(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    suffix: str = Field(min_length=1)
    rank: int = Field(ge=1, le=5)
    normal_weight: int = Field(ge=0, le=100)
    reward_weight: int = Field(ge=0, le=100)


class ConsumableLootDefinition(WorldModel):
    name: str = Field(min_length=1)
    description_template: str = Field(min_length=1)
    chance_denominator: int = Field(ge=1, le=100)
    base_healing: int = Field(ge=1)
    healing_per_level: int = Field(ge=0)
    healing_per_rarity: int = Field(ge=0)
    healing_cap: int = Field(ge=1)


class CraftingProfile(WorldModel):
    result_prefix: str = Field(min_length=1)
    description_template: str = Field(min_length=1)
    workshop_unavailable_message: str = Field(min_length=1)
    ignored_name_parts: tuple[str, ...] = ()
    object_markers: tuple[str, ...] = ()


class ItemVocabularyRule(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    aliases: tuple[str, ...]
    item_types: tuple[ItemType, ...]


class EncounterFeatureDefinition(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    icon: str = Field(min_length=1)
    description: str = Field(min_length=1)
    required_stat: AttributeId
    dc_offset: int = Field(ge=-5, le=10)
    damage_percent: int = Field(ge=0, le=100)
    effect: Literal["stunned", "exposed", "guarded"]
    reusable: bool = False


class EncounterAttackDefinition(WorldModel):
    phase: int = Field(ge=1, le=3)
    name: str = Field(min_length=1)
    icon: str = Field(min_length=1)
    description: str = Field(min_length=1)


class EncounterStatusCue(WorldModel):
    markers: tuple[str, ...]
    status_effect: Literal["burning", "poisoned", "frozen"]
    duration: int = Field(default=2, ge=1, le=25)


class EnemyProfile(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    role_label: str = Field(min_length=1)
    role_label_plural: str = Field(min_length=1)
    icon: str = Field(min_length=1)
    lore_category_id: Literal["boss"]
    defeated_label: str = Field(min_length=1)
    active_label: str = Field(min_length=1)
    next_attack_label: str = Field(min_length=1)
    manual_trigger_description: str = Field(min_length=1)
    status_labels: tuple[str, ...]
    default_status_effect: Literal["burning", "poisoned", "frozen"]
    status_cues: tuple[EncounterStatusCue, ...] = ()
    features: tuple[EncounterFeatureDefinition, ...]
    attacks: tuple[EncounterAttackDefinition, ...]


class MapRoomDefinition(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    icon: str | None = Field(default=None, min_length=1, max_length=2)
    names: tuple[str, ...] = Field(min_length=1)
    description: str = Field(min_length=1)
    contents: tuple[str, ...] = ()
    branch: bool = False
    branch_names: tuple[str, ...] = ()


class MapProfile(WorldModel):
    generator_id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    generator_version: int = Field(ge=1)
    start_location_name: str = Field(min_length=1)
    finale_location_name: str = Field(min_length=1)
    hidden_location_name: str = Field(min_length=1)
    undiscovered_location_name: str = Field(min_length=1)
    room_types: tuple[MapRoomDefinition, ...]


class NarrativeProfile(WorldModel):
    default_title: str = Field(min_length=1)
    setting_theme: str = Field(min_length=1)
    lobby_empty_message: str = Field(default="Karczma jest pusta – nikt jeszcze nie dołączył do zbiórki.", min_length=1, max_length=180)
    lobby_ready_message: str = Field(default="Cała drużyna jest gotowa! Możecie wyruszyć na wyprawę.", min_length=1, max_length=180)
    character_selection_heading: str = Field(default="WYBIERZ SWOJEGO BOHATERA", min_length=1, max_length=90)
    first_character_message: str = Field(default="Stwórz pierwszego bohatera, by poprowadzić drużynę!", min_length=1, max_length=180)
    lobby_create_first_message: str = Field(default="Stwórz pierwszego bohatera, by zacząć!", min_length=1, max_length=180)
    lobby_title_template: str = Field(min_length=1)
    lobby_prompt: str = Field(min_length=1)
    scenario_options: tuple[str, ...]
    named_weapon_description_template: str = Field(min_length=1)
    named_weapon_target_stat: AttributeId = "strength"
    party_presence_prefix: str = Field(default="W wyprawie uczestniczą:", min_length=1, max_length=90)
    prologue_party_noun: str = Field(default="drużyny", min_length=1, max_length=40)
    prologue_character_noun: str = Field(default="bohatera", min_length=1, max_length=40)
    prologue_action_qualifier: str = Field(default="niemagiczne", min_length=1, max_length=60)
    loot_search_action: QuickActionDefinition
    loot_search_markers: tuple[str, ...]
    campaign_intro: str = Field(min_length=1)
    first_challenge: str = Field(min_length=1)
    suggested_actions: tuple[str, ...]
    image_art_direction: str = Field(min_length=1)
    initial_image_prompt: str = Field(min_length=1)
    narrator_instructions: str = Field(min_length=1)
    offline_resolution_close: str = Field(min_length=1)
    offline_next_challenge: str = Field(min_length=1)
    offline_suggested_actions: tuple[str, ...]
    offline_enemy_description: str = Field(min_length=1)
    offline_enemy_naming_prompt: str = Field(min_length=1)
    offline_auto_enemy_naming: bool = True


class LoreCategoryDefinition(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    icon: str = Field(min_length=1)


class WorldPack(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: int = Field(ge=1)
    display_name: str = Field(min_length=1)
    ruleset_id: Literal["d20_v1"]
    terminology: TerminologyDefinition
    attributes: tuple[AttributeDefinition, ...]
    action_stat_cues: tuple[ActionStatCue, ...]
    theme_id: Identifier
    theme: ThemeProfile
    classes: tuple[WorldClassDefinition, ...]
    fallback_class_id: Identifier
    abilities: tuple[AbilityDefinition, ...]
    loot_tables: tuple[LootTableDefinition, ...]
    loot_rarities: tuple[LootRarityDefinition, ...]
    consumable_loot: ConsumableLootDefinition
    crafting_profile: CraftingProfile
    item_vocabulary: tuple[ItemVocabularyRule, ...]
    attack_status_cues: tuple[EncounterStatusCue, ...]
    status_presentations: tuple[StatusPresentationDefinition, ...]
    enemy_profile: EnemyProfile
    map_profile: MapProfile
    lore_categories: tuple[LoreCategoryDefinition, ...]
    narrative_profile: NarrativeProfile

    @property
    def key(self) -> str:
        return f"{self.id}@{self.version}"

    @model_validator(mode="after")
    def validate_references(self) -> "WorldPack":
        def require_unique(values: tuple[str, ...], label: str) -> None:
            if len(values) != len(set(values)):
                raise ValueError(f"{label} must be unique")

        expected_attributes = (
            "strength",
            "agility",
            "intellect",
            "charisma",
            "perception",
        )
        attribute_ids = tuple(attribute.id for attribute in self.attributes)
        if attribute_ids != expected_attributes:
            raise ValueError(
                "d20_v1 requires attributes in canonical order: "
                + ", ".join(expected_attributes)
            )
        require_unique(
            tuple(cue.marker.casefold() for cue in self.action_stat_cues),
            "action stat cue markers",
        )
        if self.theme_id != self.theme.id:
            raise ValueError("theme_id must reference theme.id")
        if not self.narrative_profile.scenario_options:
            raise ValueError("narrative profile must provide scenario options")
        if not self.narrative_profile.loot_search_markers:
            raise ValueError("narrative profile must provide loot search markers")

        class_ids = tuple(class_definition.id for class_definition in self.classes)
        require_unique(class_ids, "class ids")
        if self.fallback_class_id not in class_ids:
            raise ValueError("fallback_class_id must reference a declared class")

        ability_ids = tuple(ability.id for ability in self.abilities)
        require_unique(ability_ids, "ability ids")
        ability_id_set = set(ability_ids)

        require_unique(tuple(token.id for token in self.theme.tokens), "theme token ids")
        if {token.id for token in self.theme.tokens} != {
            "background", "surface", "surface_raised", "primary", "danger",
            "text", "text_muted", "border", "focus", "success", "accent",
            "hp", "xp",
        }:
            raise ValueError("theme must declare the complete controlled color token set")
        require_unique(
            tuple(table.id for table in self.loot_tables),
            "loot table ids",
        )
        require_unique(
            tuple(rule.id for rule in self.item_vocabulary),
            "item vocabulary ids",
        )
        if {status.id for status in self.status_presentations} != {
            "burning", "poisoned", "frozen", "stunned", "exposed", "guarded", "enraged"
        }:
            raise ValueError("world pack must provide all controlled status presentations")
        require_unique(
            tuple(status.id for status in self.status_presentations),
            "status presentation ids",
        )
        require_unique(
            tuple(room.id for room in self.map_profile.room_types),
            "map room ids",
        )
        map_room_ids = {room.id for room in self.map_profile.room_types}
        if not {"entrance", "finale"}.issubset(map_room_ids):
            raise ValueError("map profile must define entrance and finale room types")
        main_room_names = sum(
            len(room.names) for room in self.map_profile.room_types
            if room.id not in {"entrance", "finale"} and not room.branch
        )
        if main_room_names < 6 or not any(
            room.branch or room.branch_names
            for room in self.map_profile.room_types
        ):
            raise ValueError("map profile must define enough main and branch rooms")
        for table in self.loot_tables:
            require_unique(
                tuple(entry.id for entry in table.entries),
                f"loot entry ids in {table.id}",
            )
        for ability in self.abilities:
            require_unique(
                tuple(parameter.key for parameter in ability.mechanic_params),
                f"mechanic parameter keys in {ability.id}",
            )
            allowed_parameters = {
                "damage": {"status_type", "status_duration", "status_potency"},
                "heal": {"base_healing", "stat_scale"},
                "revive": {"success_percent", "critical_percent"},
                "scan": {"duration", "potency"},
                "jam": {"duration", "potency"},
                "protect": {"ignore_item_claim", "duration", "potency"},
                "cleanse": {"status_types"},
                "move": set(),
                "support": {"duration", "potency"},
            }[ability.mechanic_key]
            parameter_keys = {parameter.key for parameter in ability.mechanic_params}
            unknown_parameters = parameter_keys - allowed_parameters
            if unknown_parameters:
                raise ValueError(
                    f"ability {ability.id} has unsupported parameters for "
                    f"{ability.mechanic_key}: {', '.join(sorted(unknown_parameters))}"
                )
            if ability.mechanic_key == "revive" and not {
                "success_percent",
                "critical_percent",
            }.issubset(parameter_keys):
                raise ValueError(
                    f"revive ability {ability.id} must declare success_percent and critical_percent"
                )
            if ability.mechanic_key == "damage" and ability.intent != "attack":
                raise ValueError(f"damage ability {ability.id} must use attack intent")
            if ability.mechanic_key in {"heal", "revive", "cleanse", "support"} and ability.intent != "support":
                raise ValueError(f"{ability.mechanic_key} ability {ability.id} must use support intent")
            if ability.mechanic_key == "protect" and ability.intent != "defend":
                raise ValueError(f"protect ability {ability.id} must use defend intent")
            if ability.mechanic_key in {"scan", "jam"} and ability.intent != "interact":
                raise ValueError(f"{ability.mechanic_key} ability {ability.id} must use interact intent")
            for parameter in ability.mechanic_params:
                value = parameter.value
                if parameter.key in {"duration", "status_duration"} and (
                    not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 25
                ):
                    raise ValueError(f"ability {ability.id} has invalid duration")
                if parameter.key in {"potency", "status_potency", "base_healing"} and (
                    not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 30
                ):
                    raise ValueError(f"ability {ability.id} has invalid potency or healing")
                if parameter.key in {"success_percent", "critical_percent"} and (
                    not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 100
                ):
                    raise ValueError(f"ability {ability.id} has invalid revive percentage")
                if parameter.key == "stat_scale" and (
                    not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 10
                ):
                    raise ValueError(f"ability {ability.id} has invalid stat scale")
                if parameter.key == "status_type" and value not in {
                    "burning", "poisoned", "frozen", "stunned", "exposed", "guarded"
                }:
                    raise ValueError(f"ability {ability.id} has unknown status type")
                if parameter.key == "status_types" and (
                    not isinstance(value, str)
                    or not {part.strip() for part in value.split(",") if part.strip()}
                    <= {"burning", "poisoned", "frozen", "stunned", "exposed", "guarded"}
                ):
                    raise ValueError(f"ability {ability.id} has unknown cleanse statuses")
                if parameter.key == "ignore_item_claim" and (
                    not isinstance(value, str) or not value.strip()
                ):
                    raise ValueError(f"ability {ability.id} has invalid item-claim exemption")

        quick_action_ids: set[str] = set()
        for class_definition in self.classes:
            for action in class_definition.quick_actions:
                if action.id in quick_action_ids:
                    raise ValueError(f"duplicate quick action id: {action.id}")
                quick_action_ids.add(action.id)
            if class_definition.ability_book:
                missing = set(class_definition.ability_book.ability_ids) - ability_id_set
                if missing:
                    raise ValueError(
                        f"class {class_definition.id} references unknown abilities: "
                        + ", ".join(sorted(missing))
                    )

        require_unique(
            tuple(category.id for category in self.lore_categories),
            "lore categories",
        )
        if {category.id for category in self.lore_categories} != {
            "boss", "location", "npc", "weapon", "attack"
        }:
            raise ValueError("d20_v1 requires the five canonical lore category ids")
        if self.enemy_profile.lore_category_id not in {
            category.id for category in self.lore_categories
        }:
            raise ValueError("enemy profile must reference a declared lore category")
        require_unique(
            tuple(feature.id for feature in self.enemy_profile.features),
            "enemy feature ids",
        )
        if {attack.phase for attack in self.enemy_profile.attacks} != {1, 2, 3}:
            raise ValueError("enemy profile must define attacks for phases 1, 2 and 3")
        require_unique(
            tuple(rarity.id for rarity in self.loot_rarities),
            "loot rarity ids",
        )
        if sum(rarity.normal_weight for rarity in self.loot_rarities) != 100:
            raise ValueError("normal loot rarity weights must sum to 100")
        if sum(rarity.reward_weight for rarity in self.loot_rarities) != 100:
            raise ValueError("reward loot rarity weights must sum to 100")
        loot_table_ids = {table.id for table in self.loot_tables}
        missing_stat_tables = set(expected_attributes) - loot_table_ids
        if missing_stat_tables:
            raise ValueError(
                "loot tables missing canonical attributes: "
                + ", ".join(sorted(missing_stat_tables))
            )
        return self


class WorldClassSummary(WorldModel):
    id: str
    name: str
    icon: str
    primary_stat: AttributeId
    ability_book_title: str | None


class WorldPackSummary(WorldModel):
    id: str
    version: int
    key: str
    display_name: str
    ruleset_id: str
    theme_id: str
    theme: ThemeProfile
    scenario_options: tuple[str, ...]
    setting_theme: str
    attributes: tuple[AttributeDefinition, ...]
    classes: tuple[WorldClassSummary, ...]

    @classmethod
    def from_pack(cls, pack: WorldPack) -> "WorldPackSummary":
        return cls(
            id=pack.id,
            version=pack.version,
            key=pack.key,
            display_name=pack.display_name,
            ruleset_id=pack.ruleset_id,
            theme_id=pack.theme_id,
            theme=pack.theme,
            scenario_options=pack.narrative_profile.scenario_options,
            setting_theme=pack.narrative_profile.setting_theme,
            attributes=pack.attributes,
            classes=tuple(
                WorldClassSummary(
                    id=class_definition.id,
                    name=class_definition.name,
                    icon=class_definition.icon,
                    primary_stat=class_definition.primary_stat,
                    ability_book_title=(
                        class_definition.ability_book.title
                        if class_definition.ability_book
                        else None
                    ),
                )
                for class_definition in pack.classes
            ),
        )


class WorldPackReference(WorldModel):
    id: str
    version: int
    key: str


class WorldCatalogResponse(WorldModel):
    default_world: WorldPackReference
    worlds: tuple[WorldPackSummary, ...]
