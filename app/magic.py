import re
import unicodedata
from typing import Any


MAGIC_CLASS_CONFIG = {
    "czarodziej": {
        "kind": "spellbook",
        "title": "Księga czarów",
        "icon": "📖",
        "resource_label": "Zaklęcia",
        "casting_stat": "intellect",
    },
    "kleryk": {
        "kind": "prayers_and_miracles",
        "title": "Modlitwy i cuda",
        "icon": "☀️",
        "resource_label": "Święte moce",
        "casting_stat": "charisma",
    },
}


MAGIC_ABILITIES = {
    "czarodziej": (
        {
            "id": "arcane_bolt",
            "name": "Pocisk arkanów",
            "category": "Czar ofensywny",
            "required_level": 1,
            "icon": "✨",
            "description": "Skupiony pocisk energii uderza jeden widoczny cel.",
            "action_text": "Rzucam Pocisk arkanów i kieruję skupioną energię w przeciwnika.",
            "intent": "attack",
            "target_ref": "boss",
        },
        {
            "id": "spectral_shield",
            "name": "Widmowa tarcza",
            "category": "Czar ochronny",
            "required_level": 1,
            "icon": "🔷",
            "description": "Magiczna osłona pomaga odeprzeć nadchodzący atak.",
            "action_text": "Rzucam Widmową tarczę, tworząc magiczną osłonę przed nadchodzącym atakiem.",
            "intent": "defend",
            "target_ref": None,
        },
        {
            "id": "detect_magic",
            "name": "Wykrycie magii",
            "category": "Czar poznania",
            "required_level": 1,
            "icon": "👁️",
            "description": "Ujawnia obecność aktywnej magii, klątw i zaklętych przedmiotów.",
            "action_text": "Rzucam Wykrycie magii i badam otoczenie pod kątem aur, klątw oraz zaklętych przedmiotów.",
            "intent": "interact",
            "target_ref": None,
        },
        {
            "id": "burning_hands",
            "name": "Płonące dłonie",
            "category": "Czar ofensywny",
            "required_level": 2,
            "icon": "🔥",
            "description": "Stożek płomieni razi przeciwników stojących blisko czarodzieja.",
            "action_text": "Rzucam Płonące dłonie, posyłając przed siebie gwałtowny stożek ognia.",
            "intent": "attack",
            "target_ref": "boss",
        },
        {
            "id": "mirror_image",
            "name": "Lustrzane odbicia",
            "category": "Czar ochronny",
            "required_level": 3,
            "icon": "🪞",
            "description": "Zwodnicze kopie utrudniają przeciwnikowi trafienie czarodzieja.",
            "action_text": "Rzucam Lustrzane odbicia, otaczając się zwodniczymi kopiami własnej postaci.",
            "intent": "defend",
            "target_ref": None,
        },
        {
            "id": "lightning_bolt",
            "name": "Błyskawica",
            "category": "Czar ofensywny",
            "required_level": 5,
            "icon": "⚡",
            "description": "Potężne wyładowanie przeszywa cel i wszystko na swojej drodze.",
            "action_text": "Rzucam Błyskawicę, posyłając niszczycielskie wyładowanie w stronę przeciwnika.",
            "intent": "attack",
            "target_ref": "boss",
        },
        {
            "id": "phase_step",
            "name": "Krok przez eter",
            "category": "Czar przemiany",
            "required_level": 7,
            "icon": "🌀",
            "description": "Pozwala natychmiast przemieścić się na niewielką odległość w widoczne miejsce.",
            "action_text": "Rzucam Krok przez eter i przenoszę się w widoczne, bezpieczniejsze miejsce.",
            "intent": "other",
            "target_ref": None,
        },
        {
            "id": "meteor",
            "name": "Gwiezdny meteor",
            "category": "Czar mistrzowski",
            "required_level": 10,
            "icon": "☄️",
            "description": "Przyzywa niszczycielski odłamek niebios na pole walki.",
            "action_text": "Rzucam Gwiezdny meteor, sprowadzając na przeciwnika płonący odłamek niebios.",
            "intent": "attack",
            "target_ref": "boss",
        },
    ),
    "kleryk": (
        {
            "id": "sacred_flame",
            "name": "Święty płomień",
            "category": "Cud ofensywny",
            "required_level": 1,
            "icon": "🔥",
            "description": "Promień świętego ognia spada na jeden widoczny cel.",
            "action_text": "Wzywam Święty płomień, aby boski ogień dosięgnął przeciwnika.",
            "intent": "attack",
            "target_ref": "boss",
        },
        {
            "id": "healing_prayer",
            "name": "Modlitwa uzdrowienia",
            "category": "Modlitwa",
            "required_level": 1,
            "icon": "💚",
            "description": "Prośba o łaskę wspiera rannego członka drużyny.",
            "action_text": "Odmawiam Modlitwę uzdrowienia nad najbardziej rannym członkiem drużyny.",
            "intent": "support",
            "target_ref": None,
        },
        {
            "id": "blessing",
            "name": "Błogosławieństwo",
            "category": "Modlitwa",
            "required_level": 1,
            "icon": "🙏",
            "description": "Dodaje odwagi i wspiera sojuszników w wykonywaniu ich zamiarów.",
            "action_text": "Odmawiam Błogosławieństwo, prosząc o odwagę i siłę dla moich towarzyszy.",
            "intent": "support",
            "target_ref": None,
        },
        {
            "id": "guardian_ward",
            "name": "Opiekuńcza pieczęć",
            "category": "Cud ochronny",
            "required_level": 2,
            "icon": "🛡️",
            "description": "Święty znak osłania kleryka lub zagrożonego sojusznika.",
            "action_text": "Przywołuję Opiekuńczą pieczęć, aby osłonić najbardziej zagrożonego członka drużyny.",
            "intent": "defend",
            "target_ref": None,
        },
        {
            "id": "purification",
            "name": "Rytuał oczyszczenia",
            "category": "Modlitwa",
            "required_level": 3,
            "icon": "💧",
            "description": "Pomaga przełamać klątwę, truciznę albo nieczysty wpływ.",
            "action_text": "Odprawiam Rytuał oczyszczenia, prosząc o usunięcie klątwy, trucizny lub nieczystego wpływu.",
            "intent": "support",
            "target_ref": None,
        },
        {
            "id": "radiant_burst",
            "name": "Wybuch światłości",
            "category": "Cud ofensywny",
            "required_level": 5,
            "icon": "☀️",
            "description": "Fala blasku razi wrogów i rozprasza otaczający mrok.",
            "action_text": "Wzywam Wybuch światłości, zalewając przeciwników falą świętego blasku.",
            "intent": "attack",
            "target_ref": "boss",
        },
        {
            "id": "resurrection",
            "name": "Wskrzeszenie",
            "category": "Rytuał życia",
            "required_level": 7,
            "icon": "🕊️",
            "description": "Przywraca poległego sojusznika do życia; zwykły sukces odnawia 25% HP, krytyczny 50% HP.",
            "action_text": "Odprawiam Wskrzeszenie nad poległym sojusznikiem i wzywam jego duszę z powrotem do ciała.",
            "intent": "support",
            "target_ref": None,
        },
        {
            "id": "divine_intervention",
            "name": "Boska interwencja",
            "category": "Cud mistrzowski",
            "required_level": 8,
            "icon": "🌟",
            "description": "Rozpaczliwa prośba o potężną, lecz ściśle sytuacyjną pomoc bóstwa.",
            "action_text": "Błagam o Boską interwencję w obliczu obecnego zagrożenia dla całej drużyny.",
            "intent": "support",
            "target_ref": None,
        },
        {
            "id": "divine_judgment",
            "name": "Sąd boży",
            "category": "Cud mistrzowski",
            "required_level": 10,
            "icon": "⚖️",
            "description": "Potężna manifestacja wiary uderza w szczególnie groźnego przeciwnika.",
            "action_text": "Wzywam Sąd boży, kierując pełnię świętej mocy przeciw najgroźniejszemu przeciwnikowi.",
            "intent": "attack",
            "target_ref": "boss",
        },
    ),
}


# Wzorce obejmują naturalne odmiany nazw, ale pozostają celowo konkretne, żeby
# zwykłe czynności (np. opatrywanie rany lub badanie run) nie stawały się magią.
MAGIC_ABILITY_ALIASES = {
    "arcane_bolt": (
        r"\bpocisk\w*\s+arkan\w*\b",
        r"\bmagicz\w*\s+pocisk\w*\b",
    ),
    "spectral_shield": (
        r"\bwidmow\w*\s+tarcz\w*\b",
        r"\bmagiczn\w*\s+tarcz\w*\b",
        r"\btarcz\w*\s+magiczn\w*\b",
    ),
    "detect_magic": (
        r"\bwykry\w*\s+magi\w*\b",
        r"\bwyczuw\w*\s+magi\w*\b",
    ),
    "burning_hands": (
        r"\bplonac\w*\s+dlon\w*\b",
        r"\bstoz\w*\s+ognia\b",
    ),
    "mirror_image": (
        r"\blustrzan\w*\s+odbic\w*\b",
        r"\bmagiczn\w*\s+sobowtor\w*\b",
    ),
    "lightning_bolt": (
        r"\bblyskawic\w*\b",
        r"\bpiorun\w*\s+(?:magi\w*|arkan\w*)\b",
    ),
    "phase_step": (
        r"\bkrok\w*\s+przez\s+eter\w*\b",
        r"\bteleport\w*\b",
    ),
    "meteor": (
        r"\bgwiezdn\w*\s+meteor\w*\b",
        r"\bprzyzyw\w*.{0,30}\bmeteor\w*\b",
    ),
    "sacred_flame": (
        r"\bswiet\w*\s+plomien\w*\b",
        r"\bbosk\w*\s+ogien\w*\b",
    ),
    "healing_prayer": (
        r"\bmodlitw\w*\s+uzdrow\w*\b",
        r"\bmodl\w*.{0,40}\b(?:uzdrow|ulecz)\w*\b",
        r"\buzdraw\w*\s+(?:modlitw\w*|moc\w*\s+wiary)\b",
    ),
    "blessing": (
        r"\bblogosl(?:aw|wi)\w*\b",
    ),
    "guardian_ward": (
        r"\bopiekuncz\w*\s+pieczec\w*\b",
        r"\bswiet\w*\s+(?:oslona|pieczec)\w*\b",
    ),
    "purification": (
        r"\brytual\w*\s+oczyszcz\w*\b",
        r"\b(?:modl|bosk)\w*.{0,40}\boczyszcz\w*\b",
    ),
    "radiant_burst": (
        r"\bwybuch\w*\s+swiatlosc\w*\b",
        r"\bfal\w*\s+swiet\w*\s+swiatl\w*\b",
    ),
    "resurrection": (
        r"\bwskrzes\w*\b",
        r"\bprzywrac\w*.{0,30}\bzyc\w*\b",
    ),
    "divine_intervention": (
        r"\bbosk\w*\s+interwenc\w*\b",
    ),
    "divine_judgment": (
        r"\b(?:sad\w*\s+boz\w*|bosk\w*\s+osad\w*)\b",
    ),
}


MAGIC_ACTION_PATTERN = re.compile(
    r"\b(?:czaruj\w*|wyczar\w*|zaklin\w*|inkant\w*|teleport\w*|"
    r"przyzyw\w*|modl\w*|cud\w*|zamraz\w*|wskrzes\w*|lewit\w*|"
    r"niewidzial\w*|uzdraw\w*|bosk\w*\s+(?:moc|interwenc)\w*|"
    r"rzuc\w*\s+(?:czar|zakle)\w*|kula\s+ognia|ognist\w*\s+kula\w*|"
    r"swiet\w*\s+(?:plomien|swiatl|moc)\w*|blyskawic\w*|"
    r"widmow\w*\s+tarcza\w*|wybuch\w*\s+swiatlosc\w*|"
    r"(?:uzyw|splata|kanaliz|uwalni|tworz)\w*.{0,40}\bmagi\w*)\b"
)


def normalize_magic_class(character_class: str) -> str | None:
    normalized = unicodedata.normalize("NFKD", (character_class or "").casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char)).strip()
    return normalized if normalized in MAGIC_CLASS_CONFIG else None


def get_magic_ability(character_class: str, ability_id: str | None) -> dict[str, Any] | None:
    magic_class = normalize_magic_class(character_class)
    if not magic_class or not ability_id:
        return None
    return next(
        (ability for ability in MAGIC_ABILITIES[magic_class] if ability["id"] == ability_id),
        None,
    )


def get_magic_casting_stat(character_class: str) -> str | None:
    magic_class = normalize_magic_class(character_class)
    return MAGIC_CLASS_CONFIG[magic_class]["casting_stat"] if magic_class else None


def normalize_magic_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", (value or "").casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def find_magic_ability_in_text(action_text: str) -> tuple[str, dict[str, Any]] | None:
    normalized = normalize_magic_text(action_text)
    for magic_class, abilities in MAGIC_ABILITIES.items():
        for ability in abilities:
            normalized_name = normalize_magic_text(ability["name"])
            alias_patterns = MAGIC_ABILITY_ALIASES.get(ability["id"], ())
            if normalized_name in normalized or any(
                re.search(pattern, normalized) for pattern in alias_patterns
            ):
                return magic_class, ability
    return None


def get_magic_book(character_class: str, level: int) -> dict[str, Any] | None:
    magic_class = normalize_magic_class(character_class)
    if not magic_class:
        return None

    config = MAGIC_CLASS_CONFIG[magic_class]
    return {
        **config,
        "abilities": [
            {**ability, "unlocked": level >= ability["required_level"]}
            for ability in MAGIC_ABILITIES[magic_class]
        ],
    }


def get_unlocked_magic_abilities(character_class: str, level: int) -> list[dict[str, Any]]:
    book = get_magic_book(character_class, level)
    if not book:
        return []
    return [
        {key: value for key, value in ability.items() if key != "action_text"}
        for ability in book["abilities"]
        if ability["unlocked"]
    ]


def looks_like_magic_action(action_text: str) -> bool:
    normalized = normalize_magic_text(action_text)
    return bool(MAGIC_ACTION_PATTERN.search(normalized) or find_magic_ability_in_text(normalized))


def validate_magic_action(
    character_class: str,
    level: int,
    action_text: str,
    ability_id: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    magic_class = normalize_magic_class(character_class)
    if ability_id:
        if not magic_class:
            return None, "Ta klasa nie ma dostępu do zdolności magicznych."
        ability = get_magic_ability(character_class, ability_id)
        if not ability:
            return None, "Wybrana zdolność nie należy do księgi tej postaci."
        if level < ability["required_level"]:
            return None, f"„{ability['name']}” wymaga poziomu {ability['required_level']}."
        return ability, None

    matched_magic = find_magic_ability_in_text(action_text)
    if matched_magic:
        matched_class, ability = matched_magic
        if not magic_class:
            return None, "Tylko Czarodziej i Kleryk mogą deklarować akcje magiczne."
        if matched_class != magic_class:
            return None, "Rozpoznana zdolność nie należy do księgi tej postaci."
        if level < ability["required_level"]:
            return None, f"„{ability['name']}” wymaga poziomu {ability['required_level']}."
        return ability, None

    if looks_like_magic_action(action_text):
        if magic_class:
            title = MAGIC_CLASS_CONFIG[magic_class]["title"]
            return None, f"Magiczne akcje muszą pochodzić z widoku „{title}”. Wybierz dostępną zdolność."
        return None, "Tylko Czarodziej i Kleryk mogą deklarować akcje magiczne."

    return None, None
