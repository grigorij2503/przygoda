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
ActionIntent = Literal["attack", "defend", "support", "explore", "interact", "other"]
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
ThemeTokenId = Literal["background", "surface", "primary", "danger", "text"]


class WorldModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AttributeDefinition(WorldModel):
    id: AttributeId
    label: str = Field(min_length=1)
    abbreviation: str = Field(min_length=2, max_length=4)
    description: str = Field(min_length=1)


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
    tokens: tuple[ThemeToken, ...]


class LootTableEntry(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    item_type: ItemType
    target_stat: ItemTargetStat


class LootTableDefinition(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    entries: tuple[LootTableEntry, ...]


class ItemVocabularyRule(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)
    aliases: tuple[str, ...]


class EnemyProfile(WorldModel):
    role_label: str = Field(min_length=1)
    defeated_label: str = Field(min_length=1)
    status_labels: tuple[str, ...]


class MapRoomDefinition(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1)


class MapProfile(WorldModel):
    generator_id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    generator_version: int = Field(ge=1)
    start_location_name: str = Field(min_length=1)
    finale_location_name: str = Field(min_length=1)
    hidden_location_name: str = Field(min_length=1)
    room_types: tuple[MapRoomDefinition, ...]


class NarrativeProfile(WorldModel):
    default_title: str = Field(min_length=1)
    setting_theme: str = Field(min_length=1)
    campaign_intro: str = Field(min_length=1)
    first_challenge: str = Field(min_length=1)
    suggested_actions: tuple[str, ...]
    image_art_direction: str = Field(min_length=1)
    initial_image_prompt: str = Field(min_length=1)


class WorldPack(WorldModel):
    id: Identifier = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: int = Field(ge=1)
    display_name: str = Field(min_length=1)
    ruleset_id: Literal["d20_v1"]
    terminology: TerminologyDefinition
    attributes: tuple[AttributeDefinition, ...]
    theme_id: Identifier
    theme: ThemeProfile
    classes: tuple[WorldClassDefinition, ...]
    fallback_class_id: Identifier
    abilities: tuple[AbilityDefinition, ...]
    loot_tables: tuple[LootTableDefinition, ...]
    item_vocabulary: tuple[ItemVocabularyRule, ...]
    enemy_profile: EnemyProfile
    map_profile: MapProfile
    lore_categories: tuple[str, ...]
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
        if self.theme_id != self.theme.id:
            raise ValueError("theme_id must reference theme.id")

        class_ids = tuple(class_definition.id for class_definition in self.classes)
        require_unique(class_ids, "class ids")
        if self.fallback_class_id not in class_ids:
            raise ValueError("fallback_class_id must reference a declared class")

        ability_ids = tuple(ability.id for ability in self.abilities)
        require_unique(ability_ids, "ability ids")
        ability_id_set = set(ability_ids)

        require_unique(tuple(token.id for token in self.theme.tokens), "theme token ids")
        if {token.id for token in self.theme.tokens} != {
            "background",
            "surface",
            "primary",
            "danger",
            "text",
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
        require_unique(
            tuple(room.id for room in self.map_profile.room_types),
            "map room ids",
        )
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

        require_unique(self.lore_categories, "lore categories")
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
