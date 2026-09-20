import asyncio
import html
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import List, Optional

import httpx

from google import genai
from google.genai import types

from app.config import settings, UPLOADS_DIR
from app.magic import get_unlocked_abilities
from app.models import Character, GameSession, Turn
from app.schemas import (
    GeminiTurnResolutionSchema,
    GenerateIntroResponse,
    MapLocationUpdateSchema,
    NamingOpportunitySchema,
    PlayerConsequenceSchema,
    PrologueResponse,
)
from app.services.world_service import get_session_world_pack
from app.worlds.models import WorldPack
from app.worlds.registry import get_default_world_pack

logger = logging.getLogger(__name__)
# Wycisz ostrzeżenia AFC biblioteki google-genai
logging.getLogger("google_genai.models").setLevel(logging.ERROR)

def get_genai_client() -> Optional[genai.Client]:
    api_key = settings.GEMINI_API_KEY.strip()
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception as e:
        logger.error(f"Nie udało się zainicjalizować klienta GenAI: {e}")
        return None

def clean_json_text(text: str) -> str:
    """Oczyszcza odpowiedź modelu ze znaczników markdownowych oraz dodatkowego tekstu."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end+1]
    return text

async def call_gemini_with_retry(client: genai.Client, contents: any, config: types.GenerateContentConfig, max_retries: int = 3):
    """Wywołuje Gemini z rotacją modeli kandydatów i ponawianiem próby przy błędach 503 / 429."""
    config.automatic_function_calling = types.AutomaticFunctionCallingConfig(disable=True)
    models_to_try = [settings.GEMINI_MODEL, getattr(settings, "GEMINI_FALLBACK_MODEL", "gemini-3.6-flash"), "gemini-3.8-flash", "gemini-3.6-flash"]
    candidate_models = []
    for m in models_to_try:
        if m and m not in candidate_models:
            candidate_models.append(m)

    last_err = None
    for model_name in candidate_models:
        for attempt in range(1, max_retries + 1):
            try:
                return client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                if "not_found" in err_str or "not found" in err_str or "404" in err_str:
                    logger.warning(f"Model {model_name} nie istnieje lub brak dostępu (404). Próbuję kolejny model...")
                    break  # Przejdź do kolejnego modelu z candidate_models
                if ("503" in err_str or "unavailable" in err_str or "429" in err_str or "resource_exhausted" in err_str) and attempt < max_retries:
                    sleep_time = attempt * 1.5
                    logger.warning(f"Gemini API ({model_name}) chwilowo zajęty (próba {attempt}/{max_retries}). Ponawiam za {sleep_time}s...")
                    await asyncio.sleep(sleep_time)
                else:
                    break
        else:
            continue
        # Jeśli generate_content się powiodło, funkcja już zwróciła wynik. Jeśli wyszliśmy z pętli prób z sukcesem:
    raise last_err

async def generate_party_prologue_ai(
    session: GameSession,
    characters: List[Character],
    scenario_type: str,
    tone: str | None = None,
) -> PrologueResponse:
    """Generate a party prologue using the campaign's pinned world profile."""
    client = get_genai_client()
    world_pack = get_session_world_pack(session)
    profile = world_pack.narrative_profile
    effective_tone = tone or profile.setting_theme

    party_descriptions = []
    for c in characters:
        stats = ", ".join(
            f"{attribute.label} +{getattr(c, attribute.id)}"
            for attribute in world_pack.attributes
        )
        party_descriptions.append(
            f"• {c.name} ({c.character_class}, gracz: {c.player_name}) — {stats}"
        )

    party_text = "\n".join(party_descriptions) if party_descriptions else world_pack.terminology.party

    prompt = (
        f"{profile.narrator_instructions}\n"
        f"Stwórz wciągający prolog dla następującej {profile.prologue_party_noun}:\n"
        f"{party_text}\n\n"
        f"Sceneria / Tematyka kampanii: {scenario_type}\n"
        f"Klimat: {effective_tone}\n"
        f"Świat: {world_pack.display_name}\n\n"
        f"WYMAGANIA DLA PROLOGU:\n"
        f"1. Wymień każdego {profile.prologue_character_noun} z imienia i klasy, bez zmieniania danych postaci.\n"
        f"2. Osadź zdarzenie inicjujące i drogę do pierwszego wyzwania w podanej scenerii.\n"
        f"3. Nie wprowadzaj motywów sprzecznych z instrukcjami aktywnego świata.\n"
        f"4. Zwróć dokładnie 3 {profile.prologue_action_qualifier}, klasowo neutralne suggested_actions, "
        f"które nie zakładają posiadania konkretnego przedmiotu. Zdolności klasowe wybiera się osobno.\n"
        f"5. first_challenge ma bezpośrednio otwierać Turę 1."
    )

    if not client:
        names = ", ".join(c.name for c in characters) or world_pack.terminology.party
        return PrologueResponse(
            title=profile.default_title,
            setting_theme=effective_tone,
            prologue_story=f"{profile.campaign_intro}\n\n{profile.party_presence_prefix} {names}.",
            suggested_actions=list(profile.suggested_actions),
            first_challenge=profile.first_challenge,
        )

    try:
        response = await call_gemini_with_retry(
            client=client,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PrologueResponse,
                temperature=0.8,
            )
        )
        cleaned = clean_json_text(response.text)
        data = json.loads(cleaned)
        return PrologueResponse(**data)
    except Exception as e:
        logger.error(f"Błąd generowania prologu przez Gemini: {e}. Używam generatora awaryjnego.")
        return PrologueResponse(
            title=profile.default_title,
            setting_theme=effective_tone,
            prologue_story=profile.campaign_intro,
            suggested_actions=list(profile.suggested_actions),
            first_challenge=profile.first_challenge,
        )

async def generate_campaign_intro_ai(
    scenario_type: str,
    tone: str | None = None,
    world_pack: WorldPack | None = None,
) -> GenerateIntroResponse:
    """Generate setup copy from an explicitly selected world profile."""
    world_pack = world_pack or get_default_world_pack()
    profile = world_pack.narrative_profile
    effective_tone = tone or profile.setting_theme
    client = get_genai_client()
    if not client:
        return GenerateIntroResponse(
            title=profile.default_title,
            setting_theme=effective_tone,
            campaign_intro=profile.campaign_intro,
            first_challenge=profile.first_challenge,
        )

    prompt = (
        f"{profile.narrator_instructions}\n"
        f"Stwórz klimatyczny wstęp do turowej sesji TTRPG w stylu {effective_tone}.\n"
        f"Aktywny świat: {world_pack.display_name}.\n"
        f"Tematyka/Scenariusz: {scenario_type}.\n"
        f"Wygeneruj tytuł kampanii, zwięzły motyw przewodni (setting_theme), plastyczny i wciągający opis "
        f"początkowej sytuacji dla drużyny (campaign_intro) oraz bezpośrednie pierwsze wyzwanie (first_challenge)."
    )

    try:
        response = await call_gemini_with_retry(
            client=client,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GenerateIntroResponse,
                temperature=0.8,
            )
        )
        cleaned = clean_json_text(response.text)
        data = json.loads(cleaned)
        return GenerateIntroResponse(**data)
    except Exception as e:
        logger.warning(f"Błąd generowania wstępu via Gemini: {e}. Używam szablonu.")
        return GenerateIntroResponse(
            title=profile.default_title,
            setting_theme=effective_tone,
            campaign_intro=profile.campaign_intro,
            first_challenge=profile.first_challenge,
        )

async def resolve_turn_with_gemini(
    session: GameSession,
    turn: Turn,
    actions_with_rolls: List[dict],
    characters: List[Character],
    lore_entities: Optional[List[any]] = None,
    map_context: Optional[dict] = None,
) -> GeminiTurnResolutionSchema:
    """
    Kluczowa funkcja narracyjna:
    Przekazuje akcje graczy wraz z deterministycznymi rzutami kośćmi (wyliczonymi przez backend)
    oraz stanem nazwanych encji świata do modelu Gemini.
    """
    client = get_genai_client()
    world_pack = get_session_world_pack(session)
    narrative_profile = world_pack.narrative_profile
    enemy_profile = world_pack.enemy_profile
    enemy_category = enemy_profile.lore_category_id

    # Przygotowanie kontekstu drużyny
    party_context = []
    for c in characters:
        equipped_items = [f"{it.name} (+{it.stat_bonus} do {it.target_stat})" for it in c.inventory if it.is_equipped]
        party_context.append({
            "character_id": c.id,
            "name": c.name,
            "class": c.character_class,
            "hp": f"{c.current_hp}/{c.max_hp}",
            "death_state": getattr(c, "death_state", "alive") or "alive",
            "death_failures": int(getattr(c, "death_failures", 0) or 0),
            "level": c.level,
            "coins": int(c.coins or 0),
            "status_effects": getattr(c, "status_effects", None) or [],
            "stats": {
                attribute.id: {
                    "label": attribute.label,
                    "abbreviation": attribute.abbreviation,
                    "value": getattr(c, attribute.id),
                }
                for attribute in world_pack.attributes
            },
            "equipped": equipped_items,
            "inventory": [
                {
                    "name": item.name,
                    "description": item.description,
                    "type": item.item_type,
                    "hands_required": item.hands_required,
                    "equipped": item.is_equipped,
                    "bonus_stat": item.target_stat,
                    "bonus": item.stat_bonus,
                    "curse_stat": item.curse_stat,
                    "curse_penalty": int(item.curse_penalty or 0),
                    "quantity": item.quantity,
                }
                for item in c.inventory
            ],
            "available_abilities": get_unlocked_abilities(
                world_pack, c.class_id, c.level
            ),
        })

    actions_context = []
    for a in actions_with_rolls:
        actions_context.append({
            "character_id": a["character_id"],
            "character_name": a["character_name"],
            "action_declared": a["action_text"],
            "ability": a.get("ability") or a.get("magic_ability"),
            "named_attack": a.get("named_attack"),
            "intent": a.get("intent"),
            "target_ref": a.get("target_ref"),
            "tested_attribute": a["tested_stat"],
            "dice_roll_d20": a["dice_roll_raw"],
            "stat_bonus": a["stat_modifier"],
            "item_bonus": a["item_modifier"],
            "status_modifier": a.get("status_modifier", 0),
            "total_score": a["dice_total"],
            "dc_difficulty": a["dc"],
            "outcome_tier": a["outcome_tier"],
            "boss_damage": a.get("boss_damage", 0),
            "character_damage": a.get("character_damage", 0),
            "character_target_name": a.get("character_target_name"),
            "hp_delta_from_combat_engine": a.get("hp_delta", 0),
        })

    combat_events = getattr(turn, "combat_events", None) or []
    boss_defeated_this_turn = any(
        isinstance(event, dict) and event.get("type") == "boss_defeated"
        for event in combat_events
    )
    boss_is_alive = bool(
        session.active_boss_name and (session.active_boss_hp or 0) > 0
    )

    # Kontekst nazwanych przez graczy elementów świata (Lore). Historyczne wpisy
    # bossów nie mogą wyglądać dla narratora jak aktywne zagrożenia.
    lore_context = []
    if lore_entities:
        for ent in lore_entities:
            if not getattr(ent, "is_active", True):
                continue
            category = getattr(ent, "category", "lore")
            if category == enemy_category and not (boss_is_alive or boss_defeated_this_turn):
                continue
            if (
                category == enemy_category
                and session.active_boss_name
                and getattr(ent, "custom_name", "") != session.active_boss_name
            ):
                continue
            npc_identity = ""
            if category == "npc":
                disposition = {
                    "gentle": "łagodny",
                    "rough": "opryskliwy",
                    "vulgar": "wulgarny",
                    "reserved": "powściągliwy",
                }.get(getattr(ent, "npc_disposition", None), "powściągliwy")
                npc_identity = (
                    f", usposobienie: {disposition}"
                    f", powiedzonko: {getattr(ent, 'npc_catchphrase', None) or 'brak'}"
                    f", cel: {getattr(ent, 'npc_goal', None) or 'wynika z opisu'}"
                    f", miejsce pierwszego spotkania: {getattr(ent, 'map_node_id', None) or 'nieznane'}"
                )
            lore_context.append(
                f"[{category.upper()}]: '{getattr(ent, 'custom_name', '')}' "
                f"(opis: {getattr(ent, 'original_description', '')}, nazwany przez: "
                f"{getattr(ent, 'named_by_character_name', 'Bohater')}{npc_identity})"
            )

    boss_info = ""
    if boss_defeated_this_turn:
        boss_state = (
            f"{enemy_profile.role_label.upper()} ZOSTAŁ POKONANY W TEJ TURZE. "
            "Opisz jego upadek i nie przywracaj mu HP."
        )
        boss_info = (
            f"\nGŁÓWNY {enemy_profile.role_label.upper()}: {session.active_boss_title} "
            f"o imieniu '{session.active_boss_name}' (HP po rozliczeniu ataków: "
            f"{session.active_boss_hp}/{session.active_boss_max_hp}). {boss_state} "
            f"Faza: {getattr(session, 'active_boss_phase', 1)}, pancerz: "
            f"{getattr(session, 'active_boss_armor', 0)}, efekty: "
            f"{getattr(session, 'active_boss_effects', None) or []}. "
            "Pola boss_damage, hp_delta_from_combat_engine oraz combat_events są "
            "mechanicznym wynikiem silnika i muszą być dokładnie zgodne z narracją."
        )
    elif boss_is_alive:
        boss_info = (
            f"\nAKTYWNY GŁÓWNY {enemy_profile.role_label.upper()}: {session.active_boss_title} "
            f"o imieniu '{session.active_boss_name}' (HP po rozliczeniu ataków: "
            f"{session.active_boss_hp}/{session.active_boss_max_hp}). Przeciwnik nadal walczy. "
            f"Faza: {getattr(session, 'active_boss_phase', 1)}, pancerz: "
            f"{getattr(session, 'active_boss_armor', 0)}, efekty: "
            f"{getattr(session, 'active_boss_effects', None) or []}. "
            "Pola boss_damage, hp_delta_from_combat_engine oraz combat_events są "
            "mechanicznym wynikiem silnika i muszą być dokładnie zgodne z narracją."
        )

    system_instruction = (
        f"{narrative_profile.narrator_instructions}\n"
        f"Prowadzisz świat „{world_pack.display_name}” w klimacie „{session.setting_theme}”.\n"
        "Twoim najwyższym priorytetem jest tworzenie wciągającej, kinowej fabuły, która bezlitośnie i bezpośrednio reaguje na KAŻDE słowo zadeklarowane przez graczy.\n\n"
        "OTRZYMUJESZ WYNIKI DETERMINISTYCZNYCH RZUTÓW KOŚCIĄ D20 WYKONANYCH PRZEZ SILNIK BACKENDU DLA KAŻDEJ ZADEKLAROWANEJ AKCJI.\n\n"
        "ZASADY FABULARNE MISTRZA GRY:\n"
        "1. KONSEKWENCJE DECYZJI: Ściśle rozwijaj to, co zadeklarował gracz. "
        "Jeśli gracz deklaruje ucieczkę lub odwrót, opisz wynik zerwania kontaktu i zmianę pozycji. "
        "Jeśli gracz atakuje, opisz dynamikę starcia, rany i reakcję wroga zgodnie z aktywnym światem. "
        "Jeśli bada lub używa zdolności, opisz materialny efekt zgodny z profilem świata i definicją zdolności.\n"
        "2. WYNIKI RZUTÓW: Bezwzględnie podporządkuj powodzenie zamiarów rzutom kości (critical_success, success, partial_success, failure, critical_failure).\n"
        "3. STAN ZDROWIA I ZAGROŻENIA: W narracji wspominaj o stanie fizycznym bohaterów – ranach, krwawieniu, zmęczeniu, utracie tchu lub determinacji.\n"
        "4. CIĄGŁOŚĆ OPOWIEŚCI: Nie twórz suchych raportów punktowych. Każda tura to żywy fragment opowieści zgodnej z profilem aktywnego świata.\n\n"
        "Nie streszczaj ponownie zamkniętych wydarzeń z wcześniejszych tur. Pokonanego wcześniej głównego przeciwnika wspominaj tylko wtedy, gdy potwierdzają to bieżące combat_events albo deklaracja gracza bezpośrednio dotyczy jego pozostałości.\n\n"
        "5. PRAWDZIWY EKWIPUNEK: Pole inventory przy postaci jest jedynym źródłem prawdy o posiadanych przedmiotach. Nie pozwalaj użyć ani uzyskać korzyści z przedmiotu, którego tam nie ma. Broń, tarcza, zbroja, hełm, buty i aktywne akcesoria dają korzyść tylko, gdy mają equipped=true. Jeśli deklaracja mimo zabezpieczeń odwołuje się do nieposiadanego przedmiotu, opisz brak przedmiotu i improwizację zgodną z wynikiem rzutu, zamiast materializować wyposażenie.\n"
        "6. ŁUP I CRAFTING: Ekwipunek i saldo rozlicza wyłącznie backend. Zdarzenia item_found, item_crafted i loot_search_empty w combat_events są ostateczne — opisz je dokładnie, w tym coins_awarded, gdy występuje. W item_found pole actor oznacza właściciela przedmiotu; found_by tylko znalazcę. Gdy brak item_found, nie opisuj zdobycia żadnego przedmiotu ani środków, nawet jeśli rzut przeszukania jest udany. W każdym player_consequences ustaw new_items=[]; przedmioty utracone z innych przyczyn nadal wpisuj do removed_item_names.\n\n"
        "6a. ATAK NA POSTAĆ: Zdarzenie character_attack oraz pola character_damage i character_target_name są ostatecznym wynikiem ataku na członka drużyny. Podaj wskazany cel i dokładne obrażenia. Nie kieruj tego ataku na głównego przeciwnika ani nie dopisuj dodatkowych obrażeń.\n"
        "7. ZDOLNOŚCI KLASOWE: Pole ability przy akcji jest jedynym źródłem prawdy o użytej zdolności. Nie rozszerzaj efektu poza jej opis. Puste ability oznacza zwykłą akcję. Pole available_abilities zawiera wyłącznie odblokowane zdolności postaci.\n\n"
        "8. ODKRYTE ATAKI I NPC: Pole named_attack przy akcji wskazuje wybraną, poznaną technikę. Jej +1 obrażenie jest już w boss_damage; opisz użycie po nazwie, bez dodatkowej premii. Nazwany NPC zachowuje zapisane usposobienie i cel z opisu przy kolejnych spotkaniach. Jego powiedzonko może wracać okazjonalnie, nigdy mechanicznie w każdej turze. Nie twórz nowej wersji istniejącego NPC.\n\n"
        "ZASADY WYJŚCIA JSON:\n"
        "1. gm_story_narration: Głęboka, barwna i kinowa narracja Mistrza Gry w języku polskim podsumowująca akcje graczy i zmieniającą się sytuację (min. 3-5 soczystych zdań).\n"
        "2. player_consequences: Dla KAŻDEGO gracza: individual_summary, hp_delta, xp_gained (50-120 XP), new_items=[] oraz removed_item_names. Podczas aktywnego encounteru nie dodawaj własnych zmian HP; dla wsparcia hp_delta_from_combat_engine opisuje leczenie celu wskazanego w combat_events.\n"
        "3. next_turn_prompt: Nowa sytuacja fabularna i konkretne, bezpośrednie wyzwanie rzucone drużynie na otwarcie kolejnej tury (zawsze kończące się pytaniem 'Co robicie?').\n"
        "3a. next_challenge_tier: Wybierz standard dla zwykłego wyzwania, hard dla poważnej przeszkody albo climactic dla wyjątkowej próby o dużą stawkę. Poziom musi wynikać z opisu next_turn_prompt; nie oznaczaj każdej tury jako hard lub climactic. Serwer wyznaczy DC.\n"
        "4. suggested_actions: Dokładnie 3 zróżnicowane i konkretne ścieżki działania na otwarcie kolejnej tury. Każda ma być dostępna dla każdej klasy, nie może zakładać przedmiotu ani zdolności klasowej.\n"
        "5. scene_image_prompt: Sugestywny prompt po angielsku dla modelu generującego obraz (Gemini 2.5 Flash Image)...\n"
        f"6. naming_opportunity (opcjonalne): Tylko gdy nowe odkrycie lub NPC rzeczywiście pojawia się w gm_story_narration. Użyj wyłącznie jednej z kategorii: {', '.join(category.id for category in world_pack.lore_categories)}. Nie powtarzaj active_lore_entities. Atak proponuj bardzo rzadko i tylko po wyjątkowo udanym ataku gracza; w origin_character_id podaj ID tego gracza, a serwer skontroluje wynik i odstęp. NPC proponuj przy pierwszym ważnym spotkaniu w konkretnej lokacji, z opisem roli lub celu. W scene_evidence skopiuj dosłowny fragment gm_story_narration, który pokazuje tę postać albo odkrycie.\n"
        "7. map_update: Uzupełnij kronikę mapy. destination_node_id MUSI być jednym z ID w campaign_map.allowed_destinations. "
        "Pozostaw current_node_id, jeżeli narracja nie przeniosła całej drużyny do innego pomieszczenia. "
        "Gdy udana deklaracja ruchu ma suggested_destination_node_id, przenieś tam drużynę w narracji i ustaw ten ID w map_update; "
        "nie opisuj nowego pomieszczenia przy pozostawieniu current_node_id. "
        "location_summary ma krótko opisywać wyłącznie to, co naprawdę pojawiło się w narracji tej tury, "
        "a notable_elements zawiera maksymalnie 5 konkretnych elementów sceny. Nie twórz nowych węzłów ani przejść.\n"
        f"{boss_info}"
    )

    user_payload = {
        "campaign_title": session.title,
        "world_pack": world_pack.key,
        "world_terminology": world_pack.terminology.model_dump(mode="json"),
        "image_art_direction": narrative_profile.image_art_direction,
        "campaign_setting": session.setting_theme,
        "campaign_intro": session.campaign_intro,
        "turn_number": turn.turn_number,
        "opening_situation": turn.next_turn_prompt,
        "active_lore_entities": lore_context,
        "party_status": party_context,
        "player_actions_and_dice_rolls": actions_context,
        "combat_events": combat_events,
        "enemy_environment_features": (
            getattr(session, "active_boss_features", None) or []
            if boss_is_alive or boss_defeated_this_turn
            else []
        ),
        "enemy_next_telegraphed_attack": (
            getattr(session, "active_boss_telegraph", None)
            if boss_is_alive
            else None
        ),
        "campaign_map": map_context or {},
    }

    if not client:
        logger.info("Brak klienta Gemini API – używam inteligentnej symulacji fabularnej offline.")
        return _generate_rich_offline_resolution(
            session, turn, actions_with_rolls, characters,
            map_context=map_context, world_pack=world_pack
        )

    # Zapytanie do Gemini API z rotacją modeli i ponawianiem próby
    try:
        response = await call_gemini_with_retry(
            client=client,
            contents=json.dumps(user_payload, ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=GeminiTurnResolutionSchema,
                temperature=0.75,
            )
        )
        cleaned = clean_json_text(response.text)
        data = json.loads(cleaned)
        return GeminiTurnResolutionSchema(**data)
    except Exception as e:
        logger.warning(f"Gemini API niedostępne ({type(e).__name__}: {e}). Przełączam na dynamiczną symulację offline.")
        return _generate_rich_offline_resolution(
            session, turn, actions_with_rolls, characters,
            map_context=map_context, world_pack=world_pack
        )

def _generate_rich_offline_resolution(
    session: GameSession,
    turn: Turn,
    actions_with_rolls: List[dict],
    characters: List[Character],
    map_context: Optional[dict] = None,
    world_pack: WorldPack | None = None,
) -> GeminiTurnResolutionSchema:
    """Generuje dynamiczną, wciągającą fabularnie narrację offline reagującą na akcje graczy."""
    world_pack = world_pack or get_session_world_pack(session)
    narrative_profile = world_pack.narrative_profile
    enemy_profile = world_pack.enemy_profile
    consequences = []
    story_beats = []

    outcome_copy = {
        "critical_success": (0, 120, "osiąga pełny cel i zdobywa wyraźną przewagę"),
        "success": (0, 80, "skutecznie realizuje swój zamiar"),
        "partial_success": (-3, 60, "osiąga cel tylko częściowo i płaci za to 3 HP"),
        "failure": (-5, 50, "nie osiąga celu i traci 5 HP wskutek konsekwencji"),
        "critical_failure": (-8, 40, "ponosi dotkliwą porażkę i traci 8 HP"),
    }
    for action in actions_with_rolls:
        character_id = action["character_id"]
        name = action["character_name"]
        tier = action["outcome_tier"]
        declared_action = (action.get("action_text") or "podejmuje działanie").strip()
        hp_delta, xp, result_copy = outcome_copy.get(tier, outcome_copy["failure"])
        desc = f"{name} deklaruje: „{declared_action}” — {result_copy}."

        if turn.combat_events:
            hp_delta = int(action.get("hp_delta", 0))
            enemy_damage = int(action.get("boss_damage", 0))
            if enemy_damage > 0:
                desc += (
                    f" Mechaniczny wynik to {enemy_damage} obrażeń zadanych "
                    f"{enemy_profile.role_label}."
                )
            if hp_delta < 0:
                desc += f" Kontratak lub zagrożenie odbiera postaci {abs(hp_delta)} HP."
            elif hp_delta > 0:
                desc += f" Efekt wsparcia przywraca {hp_delta} HP."

        story_beats.append(desc)
        consequences.append(PlayerConsequenceSchema(
            character_id=character_id,
            individual_summary=desc,
            hp_delta=hp_delta,
            xp_gained=xp,
            new_items=[],
            removed_item_names=[],
        ))

    combat_summary = ""
    if turn.combat_events:
        event_sentences = []
        for event in turn.combat_events:
            event_type = event.get("type")
            if event_type == "boss_attack":
                event_sentences.append(
                    f"{event.get('boss')} odpowiada atakiem „{event.get('attack')}”, raniąc {event.get('target')} za {event.get('damage')} HP."
                )
            elif event_type == "environment_success":
                event_sentences.append(
                    f"{event.get('actor')} skutecznie wykorzystuje element areny: {event.get('feature')}."
                )
            elif event_type == "phase_change":
                event_sentences.append(
                    f"{event.get('boss')} przechodzi do fazy {event.get('phase')}, zmieniając rytm starcia."
                )
            elif event_type == "boss_defeated":
                event_sentences.append(f"{event.get('boss')} zostaje pokonany.")
            elif event_type == "status_damage":
                event_sentences.append(
                    f"Efekt {event.get('effect')} zadaje {event.get('target')} {event.get('damage')} obrażeń."
                )
            elif event_type in {"support", "revived"}:
                event_sentences.append(
                    f"{event.get('actor')} pomaga {event.get('target')}, przywracając {event.get('healing')} HP."
                )
            elif event_type == "stabilized":
                event_sentences.append(
                    f"{event.get('actor')} stabilizuje {event.get('target')}, zatrzymując postęp agonii."
                )
            elif event_type == "resurrection":
                event_sentences.append(
                    f"{event.get('actor')} wskrzesza {event.get('target')} z {event.get('healing')} HP."
                )
            elif event_type == "death_failure":
                event_sentences.append(
                    f"{event.get('target')} pozostaje w agonii ({event.get('failures')}/3 porażek śmierci)."
                )
            elif event_type == "character_died":
                event_sentences.append(f"{event.get('target')} umiera.")
            elif event_type == "item_found":
                finder = event.get("found_by")
                recipient = event.get("actor")
                money = f" oraz {event['coins_awarded']} środków" if event.get("coins_awarded") else ""
                if finder and finder != recipient:
                    event_sentences.append(
                        f"{finder} odnajduje „{event.get('item')}”{money}, a wspólny łup trafia do {recipient}."
                    )
                else:
                    event_sentences.append(
                        f"{recipient} zdobywa wspólny łup drużyny: „{event.get('item')}”{money}."
                    )
            elif event_type == "item_crafted":
                event_sentences.append(
                    f"{event.get('actor')} scala trzy składniki w przedmiot „{event.get('item')}”."
                )
            elif event_type == "loot_search_empty":
                event_sentences.append(
                    "Dokładne przeszukanie tej lokacji nie przynosi wartościowego łupu."
                )
            elif event_type == "character_attack":
                event_sentences.append(
                    f"{event.get('actor')} trafia {event.get('target')}, zadając "
                    f"{event.get('damage')} obrażeń."
                )
        if event_sentences:
            combat_summary = "\n\n" + " ".join(event_sentences)
    full_narrative = (
        f"Rozstrzygnięcie wydarzeń Tury #{turn.turn_number}:\n\n" +
        "\n\n".join(story_beats) +
        combat_summary +
        f"\n\n{narrative_profile.offline_resolution_close}"
    )

    next_challenge = narrative_profile.offline_next_challenge
    next_turn_number = turn.turn_number + 1
    next_challenge_tier = (
        "climactic" if next_turn_number % 5 == 0 else
        "hard" if next_turn_number % 3 == 0 else "standard"
    )
    if next_challenge_tier == "climactic":
        next_challenge = f"Stawka tej próby jest wyjątkowo wysoka. {next_challenge}"
    elif next_challenge_tier == "hard":
        next_challenge = f"Sytuacja staje się trudniejsza. {next_challenge}"
    suggested = list(narrative_profile.offline_suggested_actions)

    naming_opp = None
    if (turn.turn_number == 2 and not session.active_boss_name
            and narrative_profile.offline_auto_enemy_naming):
        naming_opp = NamingOpportunitySchema(
            category=enemy_profile.lore_category_id,
            description=narrative_profile.offline_enemy_description,
            prompt_for_player=narrative_profile.offline_enemy_naming_prompt,
        )
    if naming_opp is None and turn.turn_number >= 8:
        for action in actions_with_rolls:
            if (action.get("intent") != "attack"
                    or action.get("outcome_tier") not in {"success", "critical_success"}):
                continue
            actor = str(action.get("character_name") or "Bohater")
            if not any(
                event.get("type") == "player_attack"
                and event.get("actor") == actor
                and int(event.get("damage") or 0) > 0
                for event in (turn.combat_events or [])
                if isinstance(event, dict)
            ):
                continue
            declared = (action.get("action_text") or "atak").strip()
            evidence = f"{actor} deklaruje: „{declared}”"
            naming_opp = NamingOpportunitySchema(
                category="attack",
                description=f"Skuteczny manewr {actor}: {declared[:100]}",
                prompt_for_player="Jak nazwiesz tę odkrytą technikę ataku?",
                scene_evidence=evidence,
                origin_character_id=action["character_id"],
            )
            break

    map_update = None
    if map_context:
        destination_node_id = (
            map_context.get("suggested_destination_node_id")
            or map_context.get("current_node_id")
        )
        arrival = ""
        if destination_node_id != map_context.get("current_node_id"):
            destination = next(
                (location for location in map_context.get("allowed_destinations", [])
                 if location.get("id") == destination_node_id),
                None,
            )
            if destination:
                arrival = f"Drużyna dociera do lokacji: {destination['name']}."
                full_narrative += f"\n\n{arrival}"
        map_update = MapLocationUpdateSchema(
            destination_node_id=destination_node_id,
            location_summary=arrival or " ".join(story_beats)[:900],
            notable_elements=[],
        )

    return GeminiTurnResolutionSchema(
        gm_story_narration=full_narrative,
        player_consequences=consequences,
        scene_image_prompt=(
            f"{narrative_profile.image_art_direction} Scene from campaign "
            f"'{session.title}', turn {turn.turn_number}."
        ),
        next_turn_prompt=next_challenge,
        next_challenge_tier=next_challenge_tier,
        suggested_actions=suggested,
        naming_opportunity=naming_opp,
        map_update=map_update,
    )

async def generate_scene_image_ai(
    prompt: str,
    turn_id: int,
    *,
    world_pack: WorldPack | None = None,
) -> str:
    """
    Generuje ilustrację z tury za pomocą modelu Nano Banana (gemini-2.5-flash-image)
    w Google AI Studio (Pay-As-You-Go).
    """
    client = get_genai_client()
    filename = f"turn_{turn_id}_{int(time.time())}.png"
    filepath = UPLOADS_DIR / filename

    if not client:
        logger.info("Brak GEMINI_API_KEY – tworzę grafikę wektorową SVG.")
        return _generate_fallback_svg(prompt, turn_id, world_pack)

    # Nano Banana (dawniej Gemini Flash Image / Nano Banana 2)
    # Jeśli w settings masz inną nazwę, używamy aktualnej nazwy modelu
    model_name = getattr(settings, "IMAGEN_MODEL", "gemini-2.5-flash-image")
    if "imagen" in model_name.lower():
        model_name = "gemini-2.5-flash-image"

    try:
        # W Nano Banana wywołanie odbywa się przez generate_content
        # bez przekazywania zbędnych bloków konfiguracji, które powodują błędy Pydantica
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )

        # Odczytujemy obraz zwrócony w częściach odpowiedzi (parts)
        if response.parts:
            for part in response.parts:
                # 1. Próba zapisania, jeśli SDK udostępnia wyciąganie obrazu
                if hasattr(part, "as_image") and callable(part.as_image):
                    img = part.as_image()
                    if img:
                        img.save(filepath)
                        return f"/uploads/{filename}"

                # 2. Odczyt bajtów z inline_data
                if hasattr(part, "inline_data") and part.inline_data and part.inline_data.data:
                    with open(filepath, "wb") as f:
                        f.write(part.inline_data.data)
                    return f"/uploads/{filename}"

        raise ValueError("API odpowiedziało, ale w response.parts nie ma obiektu obrazu")

    except Exception as e:
        logger.error(f"Nie udało się wygenerować obrazu przez Nano Banana: {e}")
        return _generate_fallback_svg(prompt, turn_id, world_pack)


def _generate_fallback_svg(
    prompt: str,
    turn_id: int,
    world_pack: WorldPack | None = None,
) -> str:
    """Fallback generujący plik SVG w przypadku braku klucza lub błędu API."""
    world_pack = world_pack or get_default_world_pack()
    colors = {token.id: token.value for token in world_pack.theme.tokens}
    escaped_prompt = html.escape(prompt, quote=True)
    angular = world_pack.theme.shape_id == "cut_corner"
    center_motif = (
        '520,160 680,160 760,300 680,440 520,440 440,300'
        if angular else '600,160 720,380 480,380'
    )
    frame_motif = (
        f'<polygon points="380,120 820,120 940,300 820,480 380,480 260,300" '
        f'fill="none" stroke="{colors["primary"]}" stroke-width="2" '
        f'stroke-dasharray="8 4" opacity="0.3"/>'
        if angular else
        f'<circle cx="600" cy="300" r="180" fill="none" '
        f'stroke="{colors["primary"]}" stroke-width="2" '
        f'stroke-dasharray="8 4" opacity="0.3"/>'
    )
    font_family = "Arial, sans-serif" if angular else "Georgia, serif"
    svg_filename = f"turn_{turn_id}_{int(time.time())}.svg"
    svg_filepath = UPLOADS_DIR / svg_filename
    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 675" width="1200" height="675">
      <defs>
        <radialGradient id="vignette" cx="50%" cy="50%" r="70%">
           <stop offset="0%" stop-color="{colors['surface']}" stop-opacity="0.8"/>
           <stop offset="60%" stop-color="{colors['background']}" stop-opacity="0.95"/>
           <stop offset="100%" stop-color="{colors['background']}" stop-opacity="1"/>
        </radialGradient>
        <linearGradient id="gold" x1="0%" y1="0%" x2="100%" y2="100%">
           <stop offset="0%" stop-color="{colors['primary']}"/>
           <stop offset="100%" stop-color="{colors['danger']}"/>
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#vignette)"/>
       {frame_motif}
      <polygon points="{center_motif}" fill="none" stroke="url(#gold)" stroke-width="3" opacity="0.6"/>
       <text x="600" y="320" font-family="{font_family}" font-size="28" fill="{colors['primary']}" text-anchor="middle" letter-spacing="4">MISTRZ GRY • ILUSTRACJA</text>
       <text x="600" y="360" font-family="{font_family}" font-size="16" fill="{colors['text']}" text-anchor="middle" letter-spacing="2">SCENA Z TURY #{turn_id}</text>
      <foreignObject x="150" y="440" width="900" height="180">
         <div xmlns="http://www.w3.org/1999/xhtml" style="color: {colors['text']}; font-family: {font_family}; font-style: italic; font-size: 17px; text-align: center; line-height: 1.5; text-shadow: 0 2px 4px rgba(0,0,0,0.8);">
           „{escaped_prompt}”
        </div>
      </foreignObject>
    </svg>"""
    with open(svg_filepath, "w", encoding="utf-8") as f:
        f.write(svg_content)
    return f"/uploads/{svg_filename}"
