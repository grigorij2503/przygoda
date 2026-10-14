"""Local validation and retrieval of hints bundled with narration, without AI calls."""

import hashlib
import json
from collections import Counter

from app.combat import status_list
from app.models import Character, GameSession, Turn
from app.schemas import CharacterTacticalHintsSchema, TacticalHintsSchema
from app.services.world_service import get_ability_action_phrases, get_session_world_pack


TACTICAL_HINTS_INSTRUCTION = (
    "character_suggested_actions: W TEJ SAMEJ odpowiedzi zwróć osobną grupę dla każdego "
    "bohatera z can_act=true, podając dokładnie jego character_id. Każda grupa zawiera "
    "dokładnie trzy krótkie i różne deklaracje do nowego wyzwania, po jednym zdaniu, "
    "od 12 do 280 znaków. Zacznij od czasownika w pierwszej osobie liczby pojedynczej "
    "i czasie teraźniejszym, np. 'Rzucam…', 'Wiosłuję…', 'Chwytam…', 'Próbuję…'. "
    "Bez bezokolicznika, drugiej osoby, liczby mnogiej, '[imię] może…', ikon i Markdown. "
    "Opisuj zamiar, bez obietnicy sukcesu ani gotowego wyniku rzutu. "
    "Dla każdej grupy JEDYNYM wykonawcą jest postać o podanym character_id. "
    "Uwzględnij jej położenie w nowej opublikowanej scenie, stan po rozstrzygnięciu, "
    "statusy oraz własny inventory z quantity > 0 lub wyraźnie widoczny i osiągalny sprzęt. "
    "Rozróżniaj wybraną postać, jej towarzyszy i NPC. Słowo 'kapitan' może wskazywać "
    "bohatera klasy Kapitan; nie traktuj go automatycznie jako oddzielnego NPC. "
    "Tonącemu kapitanowi proponuj np. utrzymanie się na wodzie, chwytanie osiągalnej "
    "podpory lub wołanie o pomoc, zamiast rzucania liny kapitanowi albo wiosłowania "
    "z łodzi, w której go nie ma. Pozostali pomagają ze swoich pozycji. "
    "Nie wymyślaj liny, bosaka, łodzi ani innych przedmiotów, których nie ma w scenie "
    "lub inventory. Nie pożyczaj automatycznie sprzętu innych bohaterów. "
    "Przy niejasnej tożsamości lub pozycji wybierz działanie niewymagające ich dopowiadania. "
    "Uwzględnij też uwięzienie, oddzielenie od drużyny i samodzielne usuwanie szkodliwego "
    "statusu. Nie proponuj magii, zdolności klasowych, poznanych ataków, automatycznego "
    "leczenia, sekretów ani przyszłych zdarzeń. Nie wymuszaj walki w spokojnej scenie. "
    "Dla can_act=false nie zwracaj grupy. Brak propozycji nie wymaga osobnego zapytania.\n"
)


def _character_state(character: Character) -> dict:
    return {
        "id": character.id,
        "name": character.name,
        "class": character.character_class,
        "narrative_form": character.narrative_form or "neutral",
        "hp": character.current_hp,
        "max_hp": character.max_hp,
        "is_alive": bool(character.is_alive),
        "death_state": character.death_state or "alive",
        "participation_status": character.participation_status or "active",
        "status_effects": status_list(character.status_effects),
    }


def _hint_state_key(
    session: GameSession,
    turn: Turn,
    character: Character,
    characters: list[Character],
) -> str:
    world_pack = get_session_world_pack(session)
    state = {
        "world_pack": world_pack.key,
        "scene": [turn.gm_narration or "", turn.next_turn_prompt or ""],
        "active_enemy": [session.active_boss_name, session.active_boss_title, session.active_boss_hp],
        "character": _character_state(character),
        "attributes": [int(getattr(character, stat.id, 0) or 0) for stat in world_pack.attributes],
        "inventory": [
            [item.id, item.name, item.description, item.item_type,
             1 if item.quantity is None else item.quantity, bool(item.is_equipped)]
            for item in sorted(character.inventory, key=lambda item: item.id or 0)
            if item.quantity is None or item.quantity > 0
        ],
        "party": [
            _character_state(member)
            for member in sorted(characters, key=lambda member: member.id)
            if member.is_participating and (member.death_state or "alive") != "dead"
        ],
    }
    return hashlib.sha256(json.dumps(state, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _validated_actions(actions: object, session: GameSession) -> list[str] | None:
    try:
        validated = TacticalHintsSchema(suggested_actions=actions).suggested_actions
    except ValueError:
        return None
    phrases = get_ability_action_phrases(get_session_world_pack(session))
    if any(
        phrase.casefold() in action.casefold()
        for action in validated
        for phrase in phrases if phrase.strip()
    ):
        return None
    return validated


def build_saved_tactical_hints(
    session: GameSession,
    turn: Turn,
    characters: list[Character],
    generated: list[CharacterTacticalHintsSchema],
) -> dict:
    """Ignore invalid/duplicate groups without rejecting the narration or retrying AI."""
    counts = Counter(entry.character_id for entry in generated)
    eligible = {
        member.id: member for member in characters
        if member.is_participating and member.is_alive and (member.death_state or "alive") == "alive"
    }
    saved = {}
    for entry in generated:
        character = eligible.get(entry.character_id)
        if character is None or counts[entry.character_id] != 1:
            continue
        actions = _validated_actions(entry.suggested_actions, session)
        if actions:
            saved[str(character.id)] = {
                "suggested_actions": actions,
                "state_key": _hint_state_key(session, turn, character, characters),
            }
    return saved


def fallback_tactical_hints(character: Character) -> list[str]:
    statuses = {effect["type"] for effect in status_list(character.status_effects)}
    actions = []
    if "burning" in statuses:
        actions.append("Próbuję zdusić płomienie na sobie, aby ugasić ogień.")
    if "frozen" in statuses:
        actions.append("Próbuję rozbić krępujący mnie lód i uwolnić się z zamrożenia.")
    actions.extend([
        "Rozglądam się i szukam czegoś, co może pomóc mi pokonać obecną przeszkodę.",
        "Szukam bezpieczniejszej pozycji, z której mogę podjąć kolejne działanie.",
        "Oceniam sytuację i próbuję znaleźć najprostszy sposób rozwiązania problemu.",
    ])
    return actions[:3]


def get_saved_tactical_hints(
    session: GameSession,
    turn: Turn,
    character: Character,
    characters: list[Character],
) -> tuple[list[str], bool]:
    groups = turn.character_suggested_actions
    saved = groups.get(str(character.id)) if isinstance(groups, dict) else None
    if isinstance(saved, dict) and saved.get("state_key") == _hint_state_key(session, turn, character, characters):
        actions = _validated_actions(saved.get("suggested_actions"), session)
        if actions:
            return actions, True
    return fallback_tactical_hints(character), False
