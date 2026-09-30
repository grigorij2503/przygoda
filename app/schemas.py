from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


StatId = Literal["strength", "agility", "intellect", "charisma", "perception"]
NarrativeForm = Literal["masculine", "feminine", "neutral"]

# --- Auth & Session ---
class VerifyPasswordRequest(BaseModel):
    room_code: str = Field(default="kampania-1", min_length=3, max_length=50)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("room_code")
    @classmethod
    def normalize_room_code(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789-"
            for character in normalized
        ):
            raise ValueError("Kod pokoju może zawierać małe litery, cyfry i myślniki")
        return normalized


class CreateRoomRequest(BaseModel):
    room_code: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)
    title: str = Field(default="", max_length=200)
    gm_pin: str = Field(min_length=1, max_length=128)
    world_pack_id: Optional[str] = Field(default=None, max_length=80)
    world_pack_version: Optional[int] = Field(default=None, ge=1)
    scenario_type: str = Field(default="", max_length=200)
    tone: str = Field(default="", max_length=200)

    @field_validator("room_code")
    @classmethod
    def normalize_room_code(cls, value: str) -> str:
        return VerifyPasswordRequest.normalize_room_code(value)

    @model_validator(mode="after")
    def validate_world_reference(self) -> "CreateRoomRequest":
        if (self.world_pack_id is None) != (self.world_pack_version is None):
            raise ValueError("world_pack_id and world_pack_version must be provided together")
        return self

class VerifyGmPinRequest(BaseModel):
    pin: str = Field(min_length=1, max_length=128)

class WebPushKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=512)
    auth: str = Field(min_length=1, max_length=256)

class BrowserPushSubscription(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2048)
    keys: WebPushKeys

class SavePushSubscriptionRequest(BaseModel):
    room_code: str = Field(min_length=1, max_length=50)
    password: str = ""
    character_id: int
    subscription: BrowserPushSubscription

class DeletePushSubscriptionRequest(BaseModel):
    room_code: str = Field(default="kampania-1", min_length=1, max_length=50)
    password: str = ""
    endpoint: str = Field(min_length=1, max_length=2048)

class CreateSessionRequest(BaseModel):
    room_code: str
    password: str = ""
    title: Optional[str] = None
    setting_theme: Optional[str] = None
    campaign_intro: Optional[str] = ""


class FinishCampaignRequest(BaseModel):
    room_code: str = Field(min_length=1, max_length=50)
    epilogue: str = Field(min_length=20, max_length=5000)


class GenerateCampaignEndingRequest(BaseModel):
    room_code: str = Field(min_length=1, max_length=50)


class CampaignHistoryChunkSummary(BaseModel):
    summary: str = Field(min_length=20, max_length=6000)


class CampaignEndingDraftResponse(BaseModel):
    history_summary: str = Field(min_length=50, max_length=5000)
    epilogue: str = Field(min_length=20, max_length=5000)


class GenerateIntroRequest(BaseModel):
    scenario_type: str = Field(
        ...,
        description="Typ scenariusza, np. 'Krypta Pradawnego Króla', 'Nawiedzony Las Cieni', 'Krasnoludzka Twierdza opanowana przez demony'"
    )
    tone: Optional[str] = None
    world_pack_id: Optional[str] = Field(default=None, max_length=80)
    world_pack_version: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_world_reference(self) -> "GenerateIntroRequest":
        if (self.world_pack_id is None) != (self.world_pack_version is None):
            raise ValueError("world_pack_id and world_pack_version must be provided together")
        return self

class GenerateIntroResponse(BaseModel):
    title: str
    setting_theme: str
    campaign_intro: str
    first_challenge: str

# --- Character & Inventory ---
class CreateCharacterRequest(BaseModel):
    player_name: str
    name: str
    character_class: str = ""
    class_id: Optional[str] = Field(default=None, max_length=80)
    narrative_form: NarrativeForm = "neutral"
    strength: int = Field(ge=0, le=4, default=2)
    agility: int = Field(ge=0, le=4, default=1)
    intellect: int = Field(ge=0, le=4, default=1)
    charisma: int = Field(ge=0, le=4, default=0)
    perception: int = Field(ge=0, le=4, default=0)

class UpdatePersonalNoteRequest(BaseModel):
    content: str = Field(default="", max_length=20000)

class SpendStatPointRequest(BaseModel):
    stat: StatId

class TransferInventoryItemRequest(BaseModel):
    recipient_character_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=1000000000)


class MarketTransactionRequest(BaseModel):
    character_id: int = Field(gt=0)
    operation: Literal["buy", "sell", "haggle"]
    offer_id: Optional[str] = Field(default=None, max_length=30)
    item_id: Optional[int] = Field(default=None, gt=0)


class MarketInteractionRequest(BaseModel):
    character_id: int = Field(gt=0)
    text: str = Field(min_length=3, max_length=500)

class AdminUpdateCharacterStatsRequest(BaseModel):
    room_code: str = Field(min_length=1, max_length=50)
    strength: int = Field(ge=0, le=12)
    agility: int = Field(ge=0, le=12)
    intellect: int = Field(ge=0, le=12)
    charisma: int = Field(ge=0, le=12)
    perception: Optional[int] = Field(default=None, ge=0, le=12)

class AdminAdjustCoinsRequest(BaseModel):
    room_code: str = Field(min_length=1, max_length=50)
    amount: int = Field(ge=-1000000, le=1000000)

class AdminSetCharacterHealthRequest(BaseModel):
    room_code: str = Field(min_length=1, max_length=50)
    current_hp: int = Field(ge=0, le=1000000)

class AdminGrantConsumableRequest(BaseModel):
    room_code: str = Field(min_length=1, max_length=50)
    quantity: int = Field(default=1, ge=1, le=20)

class AdminSetParticipationRequest(BaseModel):
    room_code: str = Field(min_length=1, max_length=50)
    participation_status: Literal["active", "on_break"]

class AdminGrantWearableRequest(BaseModel):
    room_code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=2, max_length=150)
    description: str = Field(default="", max_length=300)
    item_type: Literal["helmet", "boots"]
    target_stat: StatId | Literal["none"] = "none"
    stat_bonus: int = Field(default=0, ge=0, le=1)

class InventoryItemDto(BaseModel):
    id: int
    name: str
    description: str
    item_type: str
    target_stat: str
    stat_bonus: int
    curse_stat: Optional[str] = None
    curse_penalty: int = 0
    damage_power: int = 0
    hands_required: int = 1
    is_equipped: bool
    quantity: int

    model_config = ConfigDict(from_attributes=True)

class CharacterDto(BaseModel):
    id: int
    player_name: str
    name: str
    character_class: str
    class_id: str
    narrative_form: NarrativeForm = "neutral"
    level: int
    xp: int
    coins: int = 0
    current_hp: int
    max_hp: int
    strength: int
    agility: int
    intellect: int
    charisma: int
    perception: int
    unspent_stat_points: int = 0
    is_alive: bool
    death_state: str = "alive"
    death_failures: int = 0
    participation_status: Literal["active", "on_break"] = "active"
    break_started_turn: Optional[int] = None
    is_ready: bool = False
    status_effects: List[dict] = []
    ability_book: Optional[dict] = None
    magic_book: Optional[dict] = None
    quick_actions: List[dict] = []
    learned_attacks: List[dict] = []
    inventory: List[InventoryItemDto] = []

    model_config = ConfigDict(from_attributes=True)

# --- Actions & Turns ---
class ResolveTurnRequest(BaseModel):
    room_code: str = "kampania-1"

class SubmitActionRequest(BaseModel):
    character_id: int
    action_text: str
    magic_ability_id: Optional[str] = Field(default=None, max_length=80)
    ability_id: Optional[str] = Field(default=None, max_length=80)
    named_attack_id: Optional[int] = Field(default=None, gt=0)
    intent: Optional[Literal["attack", "defend", "interact", "support", "other"]] = None
    tested_stat: Optional[StatId] = None
    target_ref: Optional[str] = None
    craft_item_ids: Optional[List[int]] = Field(default=None, min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_ability_alias(self) -> "SubmitActionRequest":
        if self.ability_id and self.magic_ability_id and self.ability_id != self.magic_ability_id:
            raise ValueError("ability_id and magic_ability_id must identify the same ability")
        if self.named_attack_id and self.selected_ability_id:
            raise ValueError("Named attack cannot be combined with a class ability")
        return self

    @property
    def selected_ability_id(self) -> str | None:
        return self.ability_id or self.magic_ability_id

class InterpretActionRequest(BaseModel):
    character_id: int
    action_text: str = Field(min_length=1, max_length=2000)
    magic_ability_id: Optional[str] = Field(default=None, max_length=80)
    ability_id: Optional[str] = Field(default=None, max_length=80)
    named_attack_id: Optional[int] = Field(default=None, gt=0)
    intent: Optional[Literal["attack", "defend", "interact", "support", "other"]] = None
    tested_stat: Optional[StatId] = None
    target_ref: Optional[str] = None

    @model_validator(mode="after")
    def validate_ability_alias(self) -> "InterpretActionRequest":
        if self.ability_id and self.magic_ability_id and self.ability_id != self.magic_ability_id:
            raise ValueError("ability_id and magic_ability_id must identify the same ability")
        if self.named_attack_id and self.selected_ability_id:
            raise ValueError("Named attack cannot be combined with a class ability")
        return self

    @property
    def selected_ability_id(self) -> str | None:
        return self.ability_id or self.magic_ability_id

class ActionInterpretationResponse(BaseModel):
    intent: Literal["attack", "defend", "interact", "support", "other"]
    tested_stat: StatId
    intent_confidence: float
    stat_confidence: float
    reason: str

class ProxyActionVoteRequest(BaseModel):
    voter_character_id: int
    option_id: str = Field(min_length=1, max_length=50)

class PlayerActionDto(BaseModel):
    id: int
    character_id: int
    character_name: str
    action_text: str
    magic_ability_id: Optional[str] = None
    ability_id: Optional[str] = None
    named_attack_id: Optional[int] = None
    ability: Optional[dict] = None
    magic_ability: Optional[dict] = None
    intent: Optional[str] = None
    target_ref: Optional[str] = None
    tested_stat: Optional[str] = None
    dice_roll_raw: Optional[int] = None
    stat_modifier: Optional[int] = None
    item_modifier: Optional[int] = None
    status_modifier: int = 0
    dice_total: Optional[int] = None
    dc: Optional[int] = None
    outcome_tier: Optional[str] = None
    gm_individual_summary: Optional[str] = ""
    damage_dealt: int = 0
    damage_roll: int = 0
    damage_base: int = 0
    damage_reduction: int = 0
    hp_delta: int = 0
    xp_gained: int = 0
    submission_source: str = "player"

    model_config = ConfigDict(from_attributes=True)

class TurnDto(BaseModel):
    id: int
    turn_number: int
    status: str
    gm_narration: str
    next_turn_prompt: str
    suggested_actions: List[str] = []
    image_url: Optional[str] = None
    is_generating_image: bool
    actions: List[PlayerActionDto] = []
    created_at: datetime
    resolved_at: Optional[datetime] = None
    mechanics_resolved_at: Optional[datetime] = None
    combat_events: List[dict] = []

    model_config = ConfigDict(from_attributes=True)

# --- Gemini Structured Output Schemas ---
class NewItemSchema(BaseModel):
    name: str = Field(description="Nazwa znalezionego przedmiotu")
    description: str = Field(
        description=(
            "Jedno krótkie zdanie po polsku, które jasno opisuje działanie przedmiotu, "
            "np. 'Wzbudza respekt u rozmówców' albo 'Odnawia 10 punktów życia'"
        )
    )
    item_type: Literal["weapon", "shield", "armor", "helmet", "boots", "accessory", "consumable", "misc"]
    target_stat: Literal["strength", "agility", "intellect", "charisma", "perception", "hp_max", "none"]
    stat_bonus: int = Field(description="Bonus do statystyki lub wartość leczenia dla consumable")
    hands_required: int = Field(
        default=1,
        ge=1,
        le=2,
        description="Dla broni: 1 dla jednoręcznej albo 2 dla dwuręcznej. Dla innych typów zawsze 1",
    )
    source_item_names: List[str] = Field(
        default_factory=list,
        description="Nazwy przedmiotów zużytych do stworzenia lub ulepszenia tego przedmiotu",
    )

class PlayerConsequenceSchema(BaseModel):
    character_id: int = Field(description="ID postaci, której dotyczy konsekwencja")
    individual_summary: str = Field(description="Bezpośredni, zwięzły opis tego, co stało się z tą postacią na skutek jej rzutu i akcji")
    hp_delta: int = Field(description="Dokładna zmiana HP przekazana przez silnik; przy wsparciu może dotyczyć celu akcji, narrator nie ustala tej wartości")
    xp_gained: int = Field(description="Dokładna nagroda XP przekazana przez silnik")
    new_items: List[NewItemSchema] = Field(default_factory=list, description="Zawsze puste; przedmioty przyznaje silnik")
    removed_item_names: List[str] = Field(default_factory=list, description="Zawsze puste; utratę przedmiotów rozlicza silnik")

class NamingOpportunitySchema(BaseModel):
    category: Literal["boss", "location", "npc", "weapon", "attack"] = Field(
        description="Kategoria: boss, location (lokacja), npc (napotkana postać), weapon (broń/artefakt) lub attack (zespołowy atak)"
    )
    description: str = Field(description="Opis odkrytego elementu, np. 'Monstrualny demon o płonących rogach', 'Milcząca zielarka z blizną' lub 'Ukryta komnata pełna starych ksiąg'")
    prompt_for_player: str = Field(description="Pytanie zachęcające gracza do nazwania, np. 'Jak nazwiesz tego przerażającego władcę cieni?'")
    scene_evidence: str = Field(default="", description="Krótki dosłowny fragment gm_story_narration pokazujący odkrycie lub spotkanie")
    origin_character_id: Optional[int] = Field(default=None, description="ID bohatera, którego udany atak doprowadził do odkrycia techniki")

class MapLocationUpdateSchema(BaseModel):
    destination_node_id: str = Field(
        description="ID bieżącej albo bezpośrednio sąsiedniej lokacji z przekazanej listy dozwolonych lokacji"
    )
    location_summary: str = Field(
        description="Krótki opis tego, co drużyna zobaczyła i co wydarzyło się w tej lokacji"
    )
    notable_elements: List[str] = Field(
        default_factory=list,
        description="Maksymalnie 5 krótkich nazw istotnych elementów obecnych w lokacji",
    )

class GeminiTurnResolutionSchema(BaseModel):
    gm_story_narration: str = Field(description="Główna, nastrojowa narracja Mistrza Gry łącząca akcje wszystkich graczy i ich rzuty kośćmi")
    player_consequences: List[PlayerConsequenceSchema] = Field(description="Szczegółowe skutki mechaniczne i fabularne dla każdego gracza")
    scene_image_prompt: str = Field(description="Precyzyjny prompt w języku angielskim dla modelu obrazu, zgodny z kierunkiem artystycznym aktywnego świata")
    next_turn_prompt: str = Field(description="Sytuacja wyjściowa i wyzwanie na otwarcie kolejnej tury")
    next_challenge_tier: Literal["standard", "hard", "climactic"] = Field(
        default="standard",
        description="Trudność następnego wyzwania: zwykła, trudna lub kulminacyjna",
    )
    suggested_actions: List[str] = Field(
        default_factory=list,
        description="Dokładnie 3 konkretne, zróżnicowane, niemagiczne ścieżki działania dostępne dla każdej klasy (np. natarcie, spryt/flanka, analiza otoczenia)"
    )
    naming_opportunity: Optional[NamingOpportunitySchema] = Field(default=None, description="Opcjonalna okazja do nazwania nowego bossa, niezwykłej lokacji, napotkanego NPC, potężnej broni lub ataku zespołowego przez gracza")
    map_update: Optional[MapLocationUpdateSchema] = Field(
        default=None,
        description="Aktualizacja kroniki mapy; nie może tworzyć lokacji ani przejść spoza przekazanej mapy",
    )

class GenerateImageRequest(BaseModel):
    turn_id: int

class NameEntityRequest(BaseModel):
    session_id: int
    character_id: int
    custom_name: str = Field(min_length=1, max_length=150)
    npc_disposition: Optional[Literal["gentle", "rough", "vulgar", "reserved"]] = None
    npc_catchphrase: Optional[str] = Field(default=None, max_length=150)
    npc_goal: Optional[str] = Field(default=None, max_length=200)

class TriggerNamingRequest(BaseModel):
    session_id: int
    category: Literal["boss", "location", "npc", "weapon", "attack"]
    description: str
    prompt_for_player: Optional[str] = "Jak nazwiesz to odkrycie?"

class NamedLoreEntityDto(BaseModel):
    id: int
    category: str
    original_description: str
    custom_name: str
    named_by_character_name: Optional[str] = None
    discovered_turn_number: Optional[int] = None
    map_node_id: Optional[str] = None
    npc_disposition: Optional[str] = None
    npc_catchphrase: Optional[str] = None
    npc_goal: Optional[str] = None
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class SetupScenarioRequest(BaseModel):
    room_code: str = "kampania-1"
    world_pack_id: Optional[str] = Field(default=None, max_length=80)
    world_pack_version: Optional[int] = Field(default=None, ge=1)
    scenario_type: str = ""
    tone: Optional[str] = None

    @model_validator(mode="after")
    def validate_world_reference(self) -> "SetupScenarioRequest":
        if (self.world_pack_id is None) != (self.world_pack_version is None):
            raise ValueError("world_pack_id and world_pack_version must be provided together")
        return self

class PrologueRequest(BaseModel):
    room_code: str = "kampania-1"
    scenario_type: str = ""
    tone: Optional[str] = None

class PrologueResponse(BaseModel):
    title: str
    setting_theme: str
    prologue_story: str
    suggested_actions: List[str] = Field(description="Trzy konkretne, niemagiczne ścieżki działania dostępne dla każdej klasy na start")
    first_challenge: str
