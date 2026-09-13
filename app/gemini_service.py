import asyncio
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
from app.magic import get_unlocked_magic_abilities
from app.models import Character, GameSession, Turn
from app.schemas import (
    GeminiTurnResolutionSchema,
    GenerateIntroResponse,
    MapLocationUpdateSchema,
    NamingOpportunitySchema,
    PlayerConsequenceSchema,
    PrologueResponse,
)

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
    tone: str = "Dark Fantasy"
) -> PrologueResponse:
    """
    Generuje bogate, wielowątkowe wprowadzenie do kampanii (Prolog),
    które wymienia z imienia i klasy każdego z obecnych bohaterów,
    osadza ich w początkowej scenie oraz przedstawia 3 zróżnicowane ścieżki działania.
    """
    client = get_genai_client()

    party_descriptions = []
    for c in characters:
        party_descriptions.append(f"• {c.name} (Klasa: {c.character_class}, prowadzony przez gracza: {c.player_name}) - Siła +{c.strength}, Zręczność +{c.agility}, Rozum +{c.intellect}, Charyzma +{c.charisma}")

    party_text = "\n".join(party_descriptions) if party_descriptions else "Drużyna samotnych awanturników"

    prompt = (
        f"Jesteś mistrzem narracji Dark Fantasy w stylu Grimdark.\n"
        f"Stwórz epickie, wciągające wprowadzenie fabularne (Prolog) dla następującej drużyny graczy:\n"
        f"{party_text}\n\n"
        f"Sceneria / Tematyka kampanii: {scenario_type}\n"
        f"Klimat: {tone}\n\n"
        f"WYMAGANIA DLA PROLOGU:\n"
        f"1. Scena początkowa (np. w zadymionej karczmie, przy gasnącym ognisku na szlaku lub w zrujnowanej kaplicy), w której każdy z obecnych bohaterów zostaje wspomniany z imienia i klasy w charakterystyczny sposób.\n"
        f"2. Zdarzenie inicjujące (wpadający ranny posłaniec, krzyk z zewnątrz, płonące niebo lub odnalezienie starej mapy), które kieruje ich do: {scenario_type}.\n"
        f"3. Opis podróży przez mroczne pustkowia i dotarcie przed same wrota / wejście do scenerii.\n"
        f"4. Dokładnie 3 konkretne, sugerowane ścieżki działania (suggested_actions), np. Ścieżka Siły (wyważenie wrót), Ścieżka Sprytu (poszukiwanie wyłomu), Ścieżka Magii/Wiedzy (zbadanie run).\n"
        f"5. first_challenge: Bezpośrednie wyzwanie kończące prolog i wzywające graczy do podjęcia akcji w Turze 1."
    )

    if not client:
        # Bogaty fallback offline z uwzględnieniem bohaterów
        names_list = ", ".join([c.name for c in characters]) if characters else "Wędrowcy"
        story = (
            f"Krople ulewnego deszczu bębnią o spróchniałe okiennice gospody 'Pod Wiszącym Toporem'. "
            f"Przy ciężkim dębowym stole siedzą {names_list}. "
            f"W kominku dogasają węgle, gdy nagle dębowe drzwi otwierają się z hukiem. Do sali wtacza się zakrwawiony krasnoludzki zwiadowca. "
            f"'Twierdza... runęła w płomieniach! Demony ognia przedarły się przez najgłębsze szyby!' – charczy zwiadowca, po czym upada bez tchu. "
            f"Po trudnej nocy drużyna staje u stóp czarnych bazaltowych murów w scenerii: {scenario_type}. "
            f"W powietrzu unosi się żar i siarka. Główne wrota są zaryglowane potężną sztabą, wysoko po prawej widać wyłom w murze, "
            f"a nad portalem pulsują runy dawnych krasnoludzkich klanów."
        )
        return PrologueResponse(
            title=f"Upadek Twierdzy: {scenario_type}",
            setting_theme=tone,
            prologue_story=story,
            suggested_actions=[
                "⚔️ Ścieżka Siły: Forsowanie głównej bramy i przygotowanie tarczy na przyjęcie wroga.",
                "🏹 Ścieżka Zręczności: Wspinaczka po zrujnowanych przyporach ku wyłomowi na wyższej kondygnacji.",
                "🔮 Ścieżka Rozumu/Magii: Zbadanie pulsujących run ochronnych w poszukiwaniu sekretnego hasła lub mechanizmu."
            ],
            first_challenge="Wrota przed wami drżą od wewnątrz, a z głębi korytarzy dochodzi nieludzki ryk. Co robicie?"
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
        names_list = ", ".join([c.name for c in characters]) if characters else "Drużyna"
        return PrologueResponse(
            title=f"Wyprawa: {scenario_type}",
            setting_theme=tone,
            prologue_story=(
                f"W mrocznym schronieniu {names_list} dobijają targu. "
                f"Wieści o niebezpieczeństwie w scenerii '{scenario_type}' nie pozostawiają wątpliwości – tylko zjednoczone siły mogą powstrzymać nadciągającą zagładę. "
                f"Po wyczerpującym marszu stajecie przed surowymi, kamiennymi wrotami. Z ciemności dobiega echo obcych kroków."
            ),
            suggested_actions=[
                "⚔️ Natarcie bezpośrednie i zabezpieczenie wejścia",
                "🏹 Ciche podejście i zwiad pozycji wroga",
                "🔮 Rzucenie zaklęć ochronnych i analiza aury magicznej"
            ],
            first_challenge="Co decyduje się zrobić każdy z członków drużyny?"
        )

async def generate_campaign_intro_ai(scenario_type: str, tone: str = "Dark Fantasy") -> GenerateIntroResponse:
    """Generuje wprowadzenie do kampanii za pomocą Gemini lub zwraca klimatyczny szablon."""
    client = get_genai_client()
    if not client:
        return GenerateIntroResponse(
            title=f"Cienie Przeszłości: {scenario_type}",
            setting_theme=f"{tone}, posępne zamczysko",
            campaign_intro=(
                f"Mgła opada na prastare mury, a zimny wiatr niesie echo dawno zapomnianych krzyków. "
                f"Wasza drużyna dociera do wejścia w scenerii: '{scenario_type}'. "
                f"Wrota z czarnego dębu są uchylone, a z ciemności unosi się odór starej siarki i wilgoci. "
                f"Przed wami pierwsze niebezpieczeństwo – korytarz usiany dziwnymi runami i gasnące pochodnie."
            ),
            first_challenge="Rozpoznajcie runy lub ostrożnie wkroczcie do głównej sali, zanim wrota zamkną się za wami."
        )

    prompt = (
        f"Stwórz klimatyczny wstęp do turowej sesji TTRPG w stylu {tone}.\n"
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
            title=f"Wyprawa: {scenario_type}",
            setting_theme=f"{tone}",
            campaign_intro=(
                f"Wasza kompania staje u progu niebezpieczeństwa w scenerii '{scenario_type}'. "
                f"Przed wami mrok, wilgotny kamień i niepewny los. Każdy krok może zadecydować o życiu i śmierci."
            ),
            first_challenge="Wkroczyć do wnętrza, zabezpieczając flanki i badając otoczenie."
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

    # Przygotowanie kontekstu drużyny
    party_context = []
    for c in characters:
        equipped_items = [f"{it.name} (+{it.stat_bonus} do {it.target_stat})" for it in c.inventory if it.is_equipped]
        party_context.append({
            "character_id": c.id,
            "name": c.name,
            "class": c.character_class,
            "hp": f"{c.current_hp}/{c.max_hp}",
            "level": c.level,
            "status_effects": getattr(c, "status_effects", None) or [],
            "stats": f"STR:+{c.strength}, AGI:+{c.agility}, INT:+{c.intellect}, CHA:+{c.charisma}",
            "equipped": equipped_items,
            "inventory": [
                {
                    "name": item.name,
                    "description": item.description,
                    "type": item.item_type,
                    "hands_required": item.hands_required,
                    "equipped": item.is_equipped,
                    "quantity": item.quantity,
                }
                for item in c.inventory
            ],
            "available_magic": get_unlocked_magic_abilities(c.character_class, c.level),
        })

    actions_context = []
    for a in actions_with_rolls:
        actions_context.append({
            "character_id": a["character_id"],
            "character_name": a["character_name"],
            "action_declared": a["action_text"],
            "magic_ability": a.get("magic_ability"),
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
            if category == "boss" and not (boss_is_alive or boss_defeated_this_turn):
                continue
            if (
                category == "boss"
                and session.active_boss_name
                and getattr(ent, "custom_name", "") != session.active_boss_name
            ):
                continue
            lore_context.append(
                f"[{category.upper()}]: '{getattr(ent, 'custom_name', '')}' "
                f"(opis: {getattr(ent, 'original_description', '')}, nazwany przez: "
                f"{getattr(ent, 'named_by_character_name', 'Bohater')})"
            )

    boss_info = ""
    if boss_defeated_this_turn:
        boss_state = "BOSS ZOSTAŁ POKONANY W TEJ TURZE. Opisz jego upadek i nie przywracaj mu HP."
        boss_info = (
            f"\nGŁÓWNY WRÓG / BOSS: {session.active_boss_title} "
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
            f"\nAKTYWNY GŁÓWNY WRÓG / BOSS: {session.active_boss_title} "
            f"o imieniu '{session.active_boss_name}' (HP po rozliczeniu ataków: "
            f"{session.active_boss_hp}/{session.active_boss_max_hp}). Boss nadal walczy. "
            f"Faza: {getattr(session, 'active_boss_phase', 1)}, pancerz: "
            f"{getattr(session, 'active_boss_armor', 0)}, efekty: "
            f"{getattr(session, 'active_boss_effects', None) or []}. "
            "Pola boss_damage, hp_delta_from_combat_engine oraz combat_events są "
            "mechanicznym wynikiem silnika i muszą być dokładnie zgodne z narracją."
        )

    system_instruction = (
        "Jesteś mistrzowskim, niezwykle immersyjnym Mistrzem Gry (Game Masterem) w mrocznym świecie Dark Fantasy RPG (stylistyka Wiedźmina, Dark Souls, Warhammera).\n"
        "Twoim najwyższym priorytetem jest tworzenie wciągającej, kinowej fabuły, która bezlitośnie i bezpośrednio reaguje na KAŻDE słowo zadeklarowane przez graczy.\n\n"
        "OTRZYMUJESZ WYNIKI DETERMINISTYCZNYCH RZUTÓW KOŚCIĄ D20 WYKONANYCH PRZEZ SILNIK BACKENDU DLA KAŻDEJ ZADEKLAROWANEJ AKCJI.\n\n"
        "ZASADY FABULARNE MISTRZA GRY:\n"
        "1. KONSEKWENCJE DECYZJI: Ściśle rozwijaj to, co zadeklarował gracz. "
        "Jeśli gracz deklaruje ucieczkę ('uciekam', 'odwrót') – opisz dramatyczną ucieczkę, pościg w cieniach, czy udało się zerwać kontakt i jakie nowe fascynujące miejsce odkrył (np. zapomniana karczma na rozdrożach, zatęchła krypta, wąski zaułek w ruinach). "
        "Jeśli gracz atakuje – opisz dynamikę starcia, dźwięk stali o kość, krew na pancerzu, rany i reakcję wroga. "
        "Jeśli bada lub czaruje – opisz aurę, zapach ozonu, zgrzyt kamiennych płyt i odkryte tajemnice.\n"
        "2. WYNIKI RZUTÓW: Bezwzględnie podporządkuj powodzenie zamiarów rzutom kości (critical_success, success, partial_success, failure, critical_failure).\n"
        "3. STAN ZDROWIA I ZAGROŻENIA: W narracji wspominaj o stanie fizycznym bohaterów – ranach, krwawieniu, zmęczeniu, utracie tchu lub determinacji.\n"
        "4. CIĄGŁOŚĆ OPOWIEŚCI: Nie twórz suchych raportów punktowych! Każda tura to żywy, emocjonujący fragment wciągającej powieści dark fantasy.\n\n"
        "Nie streszczaj ponownie zamkniętych wydarzeń z wcześniejszych tur. Pokonanego wcześniej bossa, jego śmierć ani szczątki wspominaj tylko wtedy, gdy combat_events zawiera boss_defeated albo bieżąca akcja gracza bezpośrednio dotyczy jego pozostałości. Rozpocznij od bieżącej sytuacji i działań graczy.\n\n"
        "5. PRAWDZIWY EKWIPUNEK: Pole inventory przy postaci jest jedynym źródłem prawdy o posiadanych przedmiotach. Nie pozwalaj użyć ani uzyskać korzyści z przedmiotu, którego tam nie ma. Broń, tarcza i zbroja dają korzyść tylko, gdy mają equipped=true. Jeśli deklaracja mimo zabezpieczeń odwołuje się do nieposiadanego przedmiotu, opisz brak przedmiotu i improwizację zgodną z wynikiem rzutu, zamiast materializować wyposażenie.\n"
        "6. ŁUP I CRAFTING: Ekwipunek rozlicza wyłącznie backend. Zdarzenia item_found, item_crafted i loot_search_empty w combat_events są ostateczne — opisz je dokładnie i nie dodawaj żadnych innych znalezisk. W każdym player_consequences ustaw new_items=[]; przedmioty utracone z innych przyczyn nadal wpisuj do removed_item_names.\n\n"
        "7. MAGIA KLASOWA: Pole magic_ability przy akcji jest jedynym źródłem prawdy o użytym czarze, modlitwie lub cudzie. Nie rozszerzaj efektu poza opis tej zdolności. Puste magic_ability oznacza zwykłą, niemagiczną akcję. Pole available_magic zawiera wyłącznie zdolności odblokowane dla danej postaci; nie przyznawaj dostępu do innych mocy.\n\n"
        "ZASADY WYJŚCIA JSON:\n"
        "1. gm_story_narration: Głęboka, barwna i kinowa narracja Mistrza Gry w języku polskim podsumowująca akcje graczy i zmieniającą się sytuację (min. 3-5 soczystych zdań).\n"
        "2. player_consequences: Dla KAŻDEGO gracza: individual_summary (fabularne podsumowanie jego losu), hp_delta (utracone/odzyskane HP), xp_gained (50-120 XP), new_items=[] oraz removed_item_names. Podczas aktywnej walki z bossem ustaw hp_delta dokładnie na hp_delta_from_combat_engine; nie dodawaj własnych obrażeń.\n"
        "3. next_turn_prompt: Nowa sytuacja fabularna i konkretne, bezpośrednie wyzwanie rzucone drużynie na otwarcie kolejnej tury (zawsze kończące się pytaniem 'Co robicie?').\n"
        "4. suggested_actions: Dokładnie 3 zróżnicowane i konkretne ścieżki działania na otwarcie kolejnej tury dopasowane do NOWEJ sytuacji.\n"
        "5. scene_image_prompt: Sugestywny prompt po angielsku dla modelu generującego obraz (Gemini 2.5 Flash Image)...\n"
        "6. naming_opportunity (opcjonalne): Jeśli w tej turze drużyna odkryła coś wyjątkowego (nowy wróg, sekretne miejsce, oręż, unikalny manewr).\n"
        "7. map_update: Uzupełnij kronikę mapy. destination_node_id MUSI być jednym z ID w campaign_map.allowed_destinations. "
        "Pozostaw current_node_id, jeżeli narracja nie przeniosła całej drużyny do innego pomieszczenia. "
        "location_summary ma krótko opisywać wyłącznie to, co naprawdę pojawiło się w narracji tej tury, "
        "a notable_elements zawiera maksymalnie 5 konkretnych elementów sceny. Nie twórz nowych węzłów ani przejść.\n"
        f"{boss_info}"
    )

    user_payload = {
        "campaign_title": session.title,
        "campaign_setting": session.setting_theme,
        "campaign_intro": session.campaign_intro,
        "turn_number": turn.turn_number,
        "opening_situation": turn.next_turn_prompt,
        "active_lore_entities": lore_context,
        "party_status": party_context,
        "player_actions_and_dice_rolls": actions_context,
        "combat_events": combat_events,
        "boss_environment_features": (
            getattr(session, "active_boss_features", None) or []
            if boss_is_alive or boss_defeated_this_turn
            else []
        ),
        "boss_next_telegraphed_attack": (
            getattr(session, "active_boss_telegraph", None)
            if boss_is_alive
            else None
        ),
        "campaign_map": map_context or {},
    }

    if not client:
        logger.info("Brak klienta Gemini API – używam inteligentnej symulacji fabularnej offline.")
        return _generate_rich_offline_resolution(
            session, turn, actions_with_rolls, characters, map_context=map_context
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
            session, turn, actions_with_rolls, characters, map_context=map_context
        )

def _generate_rich_offline_resolution(
    session: GameSession,
    turn: Turn,
    actions_with_rolls: List[dict],
    characters: List[Character],
    map_context: Optional[dict] = None,
) -> GeminiTurnResolutionSchema:
    """Generuje dynamiczną, wciągającą fabularnie narrację offline reagującą na akcje graczy."""
    consequences = []
    story_beats = []
    character_by_id = {character.id: character for character in characters}

    for a in actions_with_rolls:
        cid = a["character_id"]
        name = a["character_name"]
        tier = a["outcome_tier"]
        act_text = (a.get("action_text") or "").lower()
        declared_action = (a.get("action_text") or "działa zdecydowanie").strip()
        character = character_by_id.get(cid)
        character_class = character.character_class if character else "bohater"

        is_escape = any(w in act_text for w in ["uciek", "odwrót", "spierdal", "bieg", "wycof", "kryj"])
        is_attack = a.get("intent") == "attack" or any(w in act_text for w in ["atak", "tnę", "miecz", "cios", "strzał", "wal", "zabij", "uderz", "topór", "łuk"])
        is_search = any(w in act_text for w in ["szukam", "badam", "zwiad", "rozgląd", "otwier", "sprawdz"])
        is_magic = any(w in act_text for w in ["czar", "magi", "zaklę", "lecz", "płomie", "aur", "tarcz"])

        if tier == "critical_success":
            hp_delta = 0
            xp = 120
            if is_escape:
                desc = f"{name} wykonuje brawurowy odwrót! Zręcznie gubi pościg w labiryncie korytarzy i przez wyłamane dębowe wrota wpada wprost do starej, ukrytej podziemiach karczmy, gdzie tli się jeszcze bezpieczny kominek!"
            elif is_attack:
                desc = f"{name} wyprowadza morderczy cios! Naturalne 20 na kości. Ostrze przeszywa czuły punkt pancerza wroga, rzucając bestię na kolana w strugach czarnej posoki."
            elif is_search:
                desc = f"{name} odnajduje sekretne przejście w litej skale oraz schowek skrywający starożytny oręż!"
            elif is_magic:
                desc = f"Zaklęcie {name} eksploduje potężną falą czystej energii, odrzucając wrogów na kamienne filary i rozświetlając mrok jaskrawym blaskiem!"
            else:
                desc = f"{name} z mistrzowską precyzją realizuje swój zamysł, zyskując absolutną przewagę i oszałamiając przeciwników."
        elif tier == "success":
            hp_delta = 0
            xp = 80
            if is_escape:
                desc = f"{name} bierze nogi za pas! Przeskakując nad gruzami i gasnącymi pochodniami, urywa się pościgowi i znajduje bezpieczną osłonę za ciężkimi wrotami dawnej strażnicy."
            elif is_attack:
                damage_note = (
                    f" Cios odbiera przeciwnikowi {a.get('boss_damage', 0)} HP."
                    if a.get("boss_damage", 0) > 0
                    else " Przeciwnik cofa się pod naporem udanego natarcia."
                )
                attack_variants = [
                    f"{name}, walczący jako {character_class}, przekuwa deklarację „{declared_action}” w czysty, precyzyjny atak. Stal przecina gardę, a echo trafienia niesie się po polu walki.{damage_note}",
                    f"{name} wybiera właściwy moment i realizuje swój zamiar: „{declared_action}”. Przeciwnik zbyt późno dostrzega kierunek uderzenia i traci równowagę.{damage_note}",
                    f"Manewr postaci {name} — „{declared_action}” — kończy się zdecydowanym trafieniem. Wróg odpowiada rykiem, lecz to bohater utrzymuje inicjatywę.{damage_note}",
                    f"{name} wykorzystuje umiejętności klasy {character_class}, by wykonać: „{declared_action}”. Atak przełamuje obronę i zmusza przeciwnika do desperackiego odwrotu.{damage_note}",
                ]
                desc = attack_variants[cid % len(attack_variants)]
            elif is_search:
                desc = f"{name} dostrzega ślady świeżej krwi oraz bezpieczną ścieżkę omijającą zdradliwe zapadnie."
            elif is_magic:
                desc = f"Magia spleciona przez {name} bezbłędnie dosięga celu, spowijając pole walki osłabiającą wrogów aurą."
            else:
                desc = f"{name} zdecydowanym ruchem osiąga cel akcji, pewnie panując nad sytuacją."
        elif tier == "partial_success":
            hp_delta = -3
            xp = 60
            if is_escape:
                desc = f"{name} wyrywa się ze szponów wroga, lecz ostry odłamek skały rozcina mu ramię (-3 HP). Krwawiąc, dociera do nowego korytarza, słysząc za plecami wściekłe wycie pościgu."
            elif is_attack:
                desc = f"{name} rani wroga, lecz sam nadziewa się na rozpaczliwy kontratak (-3 HP). Ostrze ześlizguje się po napierśniku, zostawiając bolesne cięcie."
            else:
                desc = f"{name} dopina swego, lecz chwila dekoncentracji kosztuje 3 punkty życia w starciu z bezlitosnym otoczeniem."
        elif tier == "critical_failure":
            hp_delta = -8
            xp = 40
            if is_escape:
                desc = f"Katastrofalny bieg! {name} potyka się o rumowisko i z impetem uderza o granit (-8 HP). Z trudem łapie dech, podczas gdy potwory zaciskają pierścień okrążenia!"
            elif is_attack:
                desc = f"Krytyczna pomyłka {name}! Broń grzęźnie w kamiennym filarze, a potężne uderzenie wroga łamie żebra (-8 HP) i ciska postacią o ścianę."
            else:
                desc = f"Fatalny zbieg okoliczności obraca zamiar {name} w ruinę, a bestie bezlitośnie zadają 8 obrażeń."
        else:
            hp_delta = -5
            xp = 50
            if is_escape:
                desc = f"Droga ucieczki zostaje odcięta! Przeciwnik zastępuje drogę {name}, tnąc bez wahania za 5 HP i zmuszając do obrony w ciasnym narożniku."
            elif is_attack:
                desc = f"Cios {name} przecina próżnię. Wróg błyskawicznie kontratakuje z flanki, zadając 5 obrażeń."
            else:
                desc = f"Próba {name} kończy się niepowodzeniem. Postać traci 5 HP i zostaje zepchnięta do defensywy."

        if turn.combat_events:
            hp_delta = int(a.get("hp_delta", 0))
            boss_damage = int(a.get("boss_damage", 0))
            if boss_damage > 0 and tier != "success":
                desc += f" Mechaniczny wynik ciosu to {boss_damage} obrażeń zadanych bossowi."
            if hp_delta < 0:
                desc += f" Kontratak i zagrożenia areny odbierają mu {abs(hp_delta)} HP."

        story_beats.append(desc)
        consequences.append(PlayerConsequenceSchema(
            character_id=cid,
            individual_summary=desc,
            hp_delta=hp_delta,
            xp_gained=xp,
            new_items=[],
            removed_item_names=[]
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
            elif event_type == "item_found":
                finder = event.get("found_by")
                recipient = event.get("actor")
                if finder and finder != recipient:
                    event_sentences.append(
                        f"{finder} odnajduje „{event.get('item')}”, a wspólny łup trafia do {recipient}."
                    )
                else:
                    event_sentences.append(
                        f"{recipient} zdobywa wspólny łup drużyny: „{event.get('item')}”."
                    )
            elif event_type == "item_crafted":
                event_sentences.append(
                    f"{event.get('actor')} scala trzy składniki w przedmiot „{event.get('item')}”."
                )
            elif event_type == "loot_search_empty":
                event_sentences.append(
                    "Dokładne przeszukanie tej lokacji nie przynosi wartościowego łupu."
                )
        if event_sentences:
            combat_summary = "\n\n" + " ".join(event_sentences)
    full_narrative = (
        f"Rozstrzygnięcie wydarzeń Tury #{turn.turn_number}:\n\n" +
        "\n\n".join(story_beats) +
        combat_summary +
        "\n\nPowietrze gęstnieje od pyłu i zapachu żelaza. Wasze oddechy są ciężkie, a stan zdrowia przypomina o brutalności tego świata. Sytuacja uległa gwałtownej zmianie!"
    )

    next_challenge = (
        "Z mroku wyłaniają się nowe zarysy – metaliczny szczęk, gasnące pochodnie i echo kroków w głębi traktu. "
        "Wasze pozycje uległy zmianie, a czas na reakcję kurczy się nieubłaganie. Co robicie dalej?"
    )

    suggested = [
        "⚔️ Natarcie bezpośrednie z wykorzystaniem impetu i osłabienia przeciwnika",
        "🛡️ Przegrupowanie, osłona rannych i przygotowanie pozycji obronnej",
        "🔍 Wykorzystanie nowego otoczenia, zbadanie przejścia lub manewr z flanki"
    ]

    naming_opp = None
    if turn.turn_number == 2 and not session.active_boss_name:
        naming_opp = NamingOpportunitySchema(
            category="boss",
            description="Olbrzymi czempion ciemności o płonących ślepiach i okutym runami toporze",
            prompt_for_player="Pradawna bestia staje na waszej drodze. Jak nazwiesz tego potężnego wroga?"
        )

    map_update = None
    if map_context:
        current_node_id = map_context.get("current_node_id")
        allowed_destinations = map_context.get("allowed_destinations") or []
        destination_node_id = current_node_id
        movement_words = ("idę", "idziemy", "wchodz", "przechodz", "ruszam", "uciek", "odwrót")
        successful_move = any(
            any(word in (action.get("action_text") or "").lower() for word in movement_words)
            and action.get("outcome_tier") not in {"failure", "critical_failure"}
            for action in actions_with_rolls
        )
        if successful_move:
            destination_node_id = next(
                (
                    location.get("id")
                    for location in allowed_destinations
                    if location.get("id") != current_node_id
                ),
                current_node_id,
            )
        map_update = MapLocationUpdateSchema(
            destination_node_id=destination_node_id,
            location_summary=" ".join(story_beats)[:900],
            notable_elements=[],
        )

    return GeminiTurnResolutionSchema(
        gm_story_narration=full_narrative,
        player_consequences=consequences,
        scene_image_prompt=f"Dark fantasy oil painting of adventurers inside {session.title}, cinematic shadows, gritty texture",
        next_turn_prompt=next_challenge,
        suggested_actions=suggested,
        naming_opportunity=naming_opp,
        map_update=map_update,
    )

async def generate_scene_image_ai(prompt: str, turn_id: int) -> str:
    """
    Generuje ilustrację z tury za pomocą modelu Nano Banana (gemini-2.5-flash-image)
    w Google AI Studio (Pay-As-You-Go).
    """
    client = get_genai_client()
    filename = f"turn_{turn_id}_{int(time.time())}.png"
    filepath = UPLOADS_DIR / filename

    if not client:
        logger.info("Brak GEMINI_API_KEY – tworzę grafikę wektorową SVG.")
        return _generate_fallback_svg(prompt, turn_id)

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
        return _generate_fallback_svg(prompt, turn_id)


def _generate_fallback_svg(prompt: str, turn_id: int) -> str:
    """Fallback generujący plik SVG w przypadku braku klucza lub błędu API."""
    svg_filename = f"turn_{turn_id}_{int(time.time())}.svg"
    svg_filepath = UPLOADS_DIR / svg_filename
    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 675" width="1200" height="675">
      <defs>
        <radialGradient id="vignette" cx="50%" cy="50%" r="70%">
          <stop offset="0%" stop-color="#2d1b4e" stop-opacity="0.8"/>
          <stop offset="60%" stop-color="#120c1f" stop-opacity="0.95"/>
          <stop offset="100%" stop-color="#07040d" stop-opacity="1"/>
        </radialGradient>
        <linearGradient id="gold" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#e6c35c"/>
          <stop offset="100%" stop-color="#8a6d2b"/>
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#vignette)"/>
      <circle cx="600" cy="300" r="180" fill="none" stroke="#d4b483" stroke-width="2" stroke-dasharray="8 4" opacity="0.3"/>
      <polygon points="600,160 720,380 480,380" fill="none" stroke="url(#gold)" stroke-width="3" opacity="0.6"/>
      <text x="600" y="320" font-family="'Cinzel', serif, Georgia" font-size="28" fill="#e6c35c" text-anchor="middle" letter-spacing="4">MISTRZ GRY • NANO BANANA</text>
      <text x="600" y="360" font-family="'Cinzel', serif, Georgia" font-size="16" fill="#a79a86" text-anchor="middle" letter-spacing="2">ILUSTRACJA SCENY Z TURY #{turn_id}</text>
      <foreignObject x="150" y="440" width="900" height="180">
        <div xmlns="http://www.w3.org/1999/xhtml" style="color: #d4b483; font-family: Georgia, serif; font-style: italic; font-size: 17px; text-align: center; line-height: 1.5; text-shadow: 0 2px 4px rgba(0,0,0,0.8);">
          „{prompt}”
        </div>
      </foreignObject>
    </svg>"""
    with open(svg_filepath, "w", encoding="utf-8") as f:
        f.write(svg_content)
    return f"/uploads/{svg_filename}"
