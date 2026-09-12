from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, ConfigDict, Field

# --- Auth & Session ---
class VerifyPasswordRequest(BaseModel):
    password: str

class VerifyGmPinRequest(BaseModel):
    pin: str = Field(min_length=1, max_length=128)

class CreateSessionRequest(BaseModel):
    room_code: str
    password: str = ""
    title: Optional[str] = "Wyprawa do Przeklętej Twierdzy"
    setting_theme: Optional[str] = "Mroczne Podziemia"
    campaign_intro: Optional[str] = ""

class GenerateIntroRequest(BaseModel):
    scenario_type: str = Field(
        ...,
        description="Typ scenariusza, np. 'Krypta Pradawnego Króla', 'Nawiedzony Las Cieni', 'Krasnoludzka Twierdza opanowana przez demony'"
    )
    tone: Optional[str] = "Dark Fantasy, brutalne i tajemnicze"

class GenerateIntroResponse(BaseModel):
    title: str
    setting_theme: str
    campaign_intro: str
    first_challenge: str

# --- Character & Inventory ---
class CreateCharacterRequest(BaseModel):
    player_name: str
    name: str
    character_class: str = "Wojownik"
    strength: int = Field(ge=0, le=4, default=2)
    agility: int = Field(ge=0, le=4, default=1)
    intellect: int = Field(ge=0, le=4, default=1)
    charisma: int = Field(ge=0, le=4, default=0)

class UpdatePersonalNoteRequest(BaseModel):
    content: str = Field(default="", max_length=20000)

class SpendStatPointRequest(BaseModel):
    stat: Literal["strength", "agility", "intellect", "charisma"]

class InventoryItemDto(BaseModel):
    id: int
    name: str
    description: str
    item_type: str
    target_stat: str
    stat_bonus: int
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
    level: int
    xp: int
    current_hp: int
    max_hp: int
    strength: int
    agility: int
    intellect: int
    charisma: int
    unspent_stat_points: int = 0
    is_alive: bool
    is_ready: bool = False
    status_effects: List[dict] = []
    inventory: List[InventoryItemDto] = []

    model_config = ConfigDict(from_attributes=True)

# --- Actions & Turns ---
class ResolveTurnRequest(BaseModel):
    room_code: str = "kampania-1"

class MoveMapRequest(BaseModel):
    room_code: str = "kampania-1"
    destination_node_id: str = Field(min_length=1, max_length=50)
    character_id: Optional[int] = None

class SubmitActionRequest(BaseModel):
    character_id: int
    action_text: str
    intent: Optional[Literal["attack", "defend", "interact", "support", "other"]] = None
    target_ref: Optional[str] = None

class PlayerActionDto(BaseModel):
    id: int
    character_id: int
    character_name: str
    action_text: str
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
    item_type: Literal["weapon", "shield", "armor", "accessory", "consumable", "misc"]
    target_stat: Literal["strength", "agility", "intellect", "charisma", "hp_max", "none"]
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
    hp_delta: int = Field(description="Wartość zmiany HP: np. -5 przy ranach, 0 przy braku zmian, +10 przy uleczeniu")
    xp_gained: int = Field(description="Liczba przyznanych punktów XP (np. 50-100 za turę)")
    new_items: List[NewItemSchema] = Field(default_factory=list, description="Nowo zdobyte przedmioty")
    removed_item_names: List[str] = Field(default_factory=list, description="Nazwy zużytych lub utraconych przedmiotów")

class NamingOpportunitySchema(BaseModel):
    category: Literal["boss", "location", "weapon", "attack"] = Field(description="Kategoria: boss, location (lokacja), weapon (broń/artefakt) lub attack (zespołowy atak)")
    description: str = Field(description="Opis odkrytego elementu, np. 'Monstrualny demon o płonących rogach' lub 'Ukryta komnata pełna starych ksiąg'")
    prompt_for_player: str = Field(description="Pytanie zachęcające gracza do nazwania, np. 'Jak nazwiesz tego przerażającego władcę cieni?'")

class GeminiTurnResolutionSchema(BaseModel):
    gm_story_narration: str = Field(description="Główna, nastrojowa narracja Mistrza Gry łącząca akcje wszystkich graczy i ich rzuty kośćmi")
    player_consequences: List[PlayerConsequenceSchema] = Field(description="Szczegółowe skutki mechaniczne i fabularne dla każdego gracza")
    scene_image_prompt: str = Field(description="Precyzyjny prompt w języku angielskim dla modelu Imagen 3 przedstawiający scenę tury (Dark Fantasy oil painting)")
    next_turn_prompt: str = Field(description="Sytuacja wyjściowa i wyzwanie na otwarcie kolejnej tury")
    suggested_actions: List[str] = Field(
        default_factory=list,
        description="Dokładnie 3 konkretne, zróżnicowane podpowiedzi taktyczne lub ścieżki działania dla drużyny na kolejną turę (np. natarcie/siła, spryt/flanka, wiedza/magia)"
    )
    naming_opportunity: Optional[NamingOpportunitySchema] = Field(default=None, description="Opcjonalna okazja do nazwania nowego bossa, niezwykłej lokacji, potężnej broni lub ataku zespołowego przez gracza")

class GenerateImageRequest(BaseModel):
    turn_id: int

class NameEntityRequest(BaseModel):
    session_id: int
    character_id: int
    custom_name: str

class TriggerNamingRequest(BaseModel):
    session_id: int
    category: str
    description: str
    prompt_for_player: Optional[str] = "Jak nazwiesz to odkrycie?"

class NamedLoreEntityDto(BaseModel):
    id: int
    category: str
    original_description: str
    custom_name: str
    named_by_character_name: Optional[str] = None
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class SetupScenarioRequest(BaseModel):
    room_code: str = "kampania-1"
    scenario_type: str = "Krasnoludzka Twierdza opanowana przez demony ognia"
    tone: Optional[str] = "Dark Fantasy, brutalne i tajemnicze"

class PrologueRequest(BaseModel):
    room_code: str = "kampania-1"
    scenario_type: str = "Krasnoludzka Twierdza opanowana przez demony ognia"
    tone: Optional[str] = "Dark Fantasy, brutalne i tajemnicze"

class PrologueResponse(BaseModel):
    title: str
    setting_theme: str
    prologue_story: str
    suggested_actions: List[str] = Field(description="Trzy konkretne ścieżki działania dla drużyny na start")
    first_challenge: str
