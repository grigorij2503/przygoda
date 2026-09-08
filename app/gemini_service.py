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
from app.models import Character, GameSession, Turn
from app.schemas import (
    GeminiTurnResolutionSchema,
    GenerateIntroResponse,
    NewItemSchema,
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
    """Wywołuje Gemini z zachowaniem wybranego modelu i ponawianiem próby przy błędach 503 / 429."""
    config.automatic_function_calling = types.AutomaticFunctionCallingConfig(disable=True)
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            return client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=contents,
                config=config,
            )
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            if ("503" in err_str or "unavailable" in err_str or "429" in err_str or "resource_exhausted" in err_str) and attempt < max_retries:
                sleep_time = attempt * 1.5
                logger.warning(f"Gemini API ({settings.GEMINI_MODEL}) chwilowo niedostępny (kod 503/429, próba {attempt}/{max_retries}). Ponawiam za {sleep_time}s...")
                await asyncio.sleep(sleep_time)
            else:
                raise e
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
    lore_entities: Optional[List[any]] = None
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
            "stats": f"STR:+{c.strength}, AGI:+{c.agility}, INT:+{c.intellect}, CHA:+{c.charisma}",
            "equipped": equipped_items
        })

    actions_context = []
    for a in actions_with_rolls:
        actions_context.append({
            "character_id": a["character_id"],
            "character_name": a["character_name"],
            "action_declared": a["action_text"],
            "tested_attribute": a["tested_stat"],
            "dice_roll_d20": a["dice_roll_raw"],
            "stat_bonus": a["stat_modifier"],
            "item_bonus": a["item_modifier"],
            "total_score": a["dice_total"],
            "dc_difficulty": a["dc"],
            "outcome_tier": a["outcome_tier"]
        })

    # Kontekst nazwanych przez graczy elementów świata (Lore)
    lore_context = []
    if lore_entities:
        for ent in lore_entities:
            if getattr(ent, 'is_active', True):
                lore_context.append(f"[{getattr(ent, 'category', 'lore').upper()}]: '{getattr(ent, 'custom_name', '')}' (opis: {getattr(ent, 'original_description', '')}, nazwany przez: {getattr(ent, 'named_by_character_name', 'Bohater')})")

    boss_info = ""
    if session.active_boss_name:
        boss_info = f"\nAKTYWNY GŁÓWNY WRÓG / BOSS: {session.active_boss_title} o imieniu '{session.active_boss_name}' (HP: {session.active_boss_hp}/{session.active_boss_max_hp}). Pamiętaj, aby opisywać jego poczynania i odnosić się do niego pod tym imieniem!"

    system_instruction = (
        "Jesteś surowym, bezstronnym i niezwykle immersyjnym Mistrzem Gry (Game Masterem) w mrocznym świecie Dark Fantasy TTRPG.\n"
        "OTRZYMUJESZ WYNIKI DETERMINISTYCZNYCH RZUTÓW KOŚCIĄ D20 WYKONANYCH PRZEZ BEZSTRONNY SILNIK BACKENDU.\n"
        "Twoim bezwzględnym obowiązkiem jest podporządkowanie fabuły i konsekwencji tym rzutom:\n"
        "- critical_success (naturalne 20): Spektakularny sukces, premia, oszołomienie wroga lub znalezienie czegoś cennego.\n"
        "- success (wynik >= DC): Pełne powodzenie zamiaru gracza.\n"
        "- partial_success (wynik o 1-2 poniżej DC): Sukces z kosztem (cel osiągnięty, ale postać obrywa lekkie obrażenia, traci przedmiot lub zwraca uwagę potwora).\n"
        "- failure (wynik poniżej DC): Porażka, nieudana próba, obrażenia dla gracza lub pogorszenie sytuacji taktycznej.\n"
        "- critical_failure (naturalne 1): Katastrofalna porażka, poważne rany, upuszczenie broni lub krytyczna komplikacja.\n\n"
        "ZASADY WYJŚCIA JSON:\n"
        "1. gm_story_narration: Płynna, kinowa i mroczna narracja w języku polskim.\n"
        "2. player_consequences: Dla KAŻDEGO gracza zwróć dokładny bilans: hp_delta (np. -4, +6, 0), xp_gained (50-120 XP), nowo znalezione przedmioty (new_items) lub zużyte (removed_item_names).\n"
        "3. scene_image_prompt: Sugestywny prompt PO ANGIELSKU dla modelu Imagen 3 (Dark fantasy oil painting, gritty realism, atmospheric lighting).\n"
        "4. next_turn_prompt: Nowa sytuacja i bezpośrednie wyzwanie rzucone drużynie na początek kolejnej tury.\n"
        "5. naming_opportunity (opcjonalne): Jeśli w tej turze drużyna odkryła coś wyjątkowego – nowego groźnego wroga (boss), sekretne niezwykłe miejsce (location), potężny unikalny oręż (weapon) lub wykonała spektakularny wspólny atak dwóch graczy (attack) – wypełnij to pole, aby wyznaczony losowo gracz mógł nadać temu stałe imię/nazwę!"
        f"{boss_info}"
    )

    user_payload = {
        "campaign_title": session.title,
        "campaign_setting": session.setting_theme,
        "campaign_intro": session.campaign_intro,
        "turn_number": turn.turn_number,
        "active_lore_entities": lore_context,
        "party_status": party_context,
        "player_actions_and_dice_rolls": actions_context
    }

    if not client:
        # Dynamiczny, bogaty fallback offline
        logger.info("Brak klucza GEMINI_API_KEY – używam silnika symulacji fabuły offline.")
        consequences = []
        narrative_parts = []

        for a in actions_with_rolls:
            cid = a["character_id"]
            name = a["character_name"]
            tier = a["outcome_tier"]
            total = a["dice_total"]
            stat = a["tested_stat"]

            if tier == "critical_success":
                hp_delta = 0
                xp = 120
                desc = f"{name} wykonuje mistrzowski manewr! Rzut d20 dał naturalne 20 (suma {total}). Przeciwnicy cofają się w popłochu."
            elif tier == "success":
                hp_delta = 0
                xp = 80
                desc = f"{name} z powodzeniem realizuje swój zamiar (test {stat}: {total} vs DC {a['dc']}). Akcja zakończona pełnym sukcesem."
            elif tier == "partial_success":
                hp_delta = -3
                xp = 60
                desc = f"{name} osiąga cel, lecz chwila zawahania kosztuje 3 HP (test {stat}: {total} vs DC {a['dc']})."
            elif tier == "critical_failure":
                hp_delta = -8
                xp = 40
                desc = f"Katastrofalny błąd {name}! Naturalne 1 na kości. Broń wyślizguje się z dłoni, a cios wroga rani postać za 8 HP."
            else:
                hp_delta = -5
                xp = 50
                desc = f"Akcja {name} nie powiodła się (wynik {total} vs DC {a['dc']}). Wróg wykorzystuje lukę w obronie, zadając 5 obrażeń."

            narrative_parts.append(desc)
            consequences.append(PlayerConsequenceSchema(
                character_id=cid,
                individual_summary=desc,
                hp_delta=hp_delta,
                xp_gained=xp,
                new_items=[
                    NewItemSchema(
                        name="Starożytny Sztylet Cienia",
                        description="Błyszczący runami odłamek czarnego kamienia",
                        item_type="weapon",
                        target_stat="agility",
                        stat_bonus=1
                    )
                ] if tier in ["critical_success"] else [],
                removed_item_names=[]
            ))

        full_narrative = (
            f"Tura {turn.turn_number} dobiegła końca. " + " ".join(narrative_parts) +
            " Echo walki cichnie pośród zimnych sklepień, lecz w powietrzu wciąż czuć zapach niebezpieczeństwa."
        )

        # W turze 2 zasymuluj okazję do nazwania bossa
        naming_opp = None
        if turn.turn_number == 2 and not session.active_boss_name:
            naming_opp = NamingOpportunitySchema(
                category="boss",
                description="Olbrzymi wódz demonów w napierśniku ze stopionej miedzi",
                prompt_for_player="Pradawna bestia wyłania się z lawy. Jak nazwiesz tego potężnego wroga?"
            )

        return GeminiTurnResolutionSchema(
            gm_story_narration=full_narrative,
            player_consequences=consequences,
            scene_image_prompt=f"Dark fantasy oil painting of adventurers fighting inside {session.title}, torchlight, cinematic shadows, gritty texture",
            next_turn_prompt="Dym opada, a z głębi korytarza wyłania się kolejna przeszkoda. Jak reagujecie?",
            naming_opportunity=naming_opp
        )

    # Zapytanie do Gemini API z ponawianiem próby
    try:
        response = await call_gemini_with_retry(
            client=client,
            contents=json.dumps(user_payload, ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=GeminiTurnResolutionSchema,
                temperature=0.7,
            )
        )
        cleaned = clean_json_text(response.text)
        data = json.loads(cleaned)
        return GeminiTurnResolutionSchema(**data)
    except (httpx.NetworkError, ConnectionError, OSError) as e:
        # Błąd sieciowy (brak internetu, DNS, timeout) – fallback offline
        logger.warning(f"Brak połączenia z Gemini API ({e}). Przełączam na symulację offline.")
    except Exception as e:
        # Inne błędy API (np. 503, 429) które nie zostały obsłużone przez retry
        logger.error(f"Krytyczny błąd wywołania Gemini API dla tury: {e}")
        raise e

    # --- Fallback offline (po złapaniu wyjątku sieciowego) ---
    logger.info("Używam silnika symulacji fabuły offline (fallback po błędzie sieci).")
    consequences = []
    narrative_parts = []

    for a in actions_with_rolls:
        cid = a["character_id"]
        name = a["character_name"]
        tier = a["outcome_tier"]
        total = a["dice_total"]
        stat = a["tested_stat"]

        if tier == "critical_success":
            hp_delta = 0
            xp = 120
            desc = f"{name} wykonuje mistrzowski manewr! Rzut d20 dał naturalne 20 (suma {total}). Przeciwnicy cofają się w popłochu."
        elif tier == "success":
            hp_delta = 0
            xp = 80
            desc = f"{name} z powodzeniem realizuje swój zamiar (test {stat}: {total} vs DC {a['dc']}). Akcja zakończona pełnym sukcesem."
        elif tier == "partial_success":
            hp_delta = -3
            xp = 60
            desc = f"{name} osiąga cel, lecz chwila zawahania kosztuje 3 HP (test {stat}: {total} vs DC {a['dc']})."
        elif tier == "critical_failure":
            hp_delta = -8
            xp = 40
            desc = f"Katastrofalny błąd {name}! Naturalne 1 na kości. Broń wyślizguje się z dłoni, a cios wroga rani postać za 8 HP."
        else:
            hp_delta = -5
            xp = 50
            desc = f"Akcja {name} nie powiodła się (wynik {total} vs DC {a['dc']}). Wróg wykorzystuje lukę w obronie, zadając 5 obrażeń."

        narrative_parts.append(desc)
        consequences.append(PlayerConsequenceSchema(
            character_id=cid,
            individual_summary=desc,
            hp_delta=hp_delta,
            xp_gained=xp,
            new_items=[],
            removed_item_names=[]
        ))

    full_narrative = (
        f"Tura {turn.turn_number} dobiegła końca. " + " ".join(narrative_parts) +
        " Echo walki cichnie pośród zimnych sklepień, lecz w powietrzu wciąż czuć zapach niebezpieczeństwa."
    )

    return GeminiTurnResolutionSchema(
        gm_story_narration=full_narrative,
        player_consequences=consequences,
        scene_image_prompt=f"Dark fantasy oil painting of adventurers fighting inside {session.title}, torchlight, cinematic shadows, gritty texture",
        next_turn_prompt="Dym opada, a z głębi korytarza wyłania się kolejna przeszkoda. Jak reagujecie?",
        naming_opportunity=None
    )

async def generate_scene_image_ai(prompt: str, turn_id: int) -> str:
    """
    Generuje ilustrację z tury za pomocą Imagen 3 na żądanie.
    Zwraca relatywną ścieżkę do pliku graficznego serwowanego przez aplikację.
    """
    client = get_genai_client()
    filename = f"turn_{turn_id}_{int(time.time())}.png"
    filepath = UPLOADS_DIR / filename

    if not client:
        logger.info("Brak GEMINI_API_KEY dla Imagen 3 – tworzę grafikę wektorową SVG.")
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
          <text x="600" y="320" font-family="'Cinzel', serif, Georgia" font-size="28" fill="#e6c35c" text-anchor="middle" letter-spacing="4">MISTRZ GRY • IMAGEN 3</text>
          <text x="600" y="360" font-family="'Cinzel', serif, Georgia" font-size="16" fill="#a79a86" text-anchor="middle" letter-spacing="2">ILUSTRACJA SCENY Z TURY #{turn_id}</text>
          <foreignObject x="150" y="440" width="900" height="180">
            <div xmlns="http://www.w3.org/1999/xhtml" style="color: #d4b483; font-family: Georgia, serif; font-style: italic; font-size: 17px; text-align: center; line-height: 1.5; text-shadow: 0 2px 4px rgba(0,0,0,0.8);">
              „{prompt}”
            </div>
          </foreignObject>
        </svg>"""
        svg_filename = f"turn_{turn_id}_{int(time.time())}.svg"
        svg_filepath = UPLOADS_DIR / svg_filename
        with open(svg_filepath, "w", encoding="utf-8") as f:
            f.write(svg_content)
        return f"/uploads/{svg_filename}"

    try:
        response = client.models.generate_images(
            model=settings.IMAGEN_MODEL,
            prompt=prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="16:9",
                person_generation="ALLOW_ADULT",
            )
        )
        if response.generated_images:
            image_bytes = response.generated_images[0].image.image_bytes
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            return f"/uploads/{filename}"
        else:
            raise ValueError("Brak zwróconych obrazów z Imagen 3")
    except Exception as e:
        logger.error(f"Nie udało się wygenerować obrazu przez Imagen 3: {e}")
        svg_filename = f"turn_{turn_id}_{int(time.time())}.svg"
        svg_filepath = UPLOADS_DIR / svg_filename
        with open(svg_filepath, "w", encoding="utf-8") as f:
            f.write(f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 675" width="1200" height="675">
              <rect width="100%" height="100%" fill="#0e0e14"/>
              <text x="600" y="320" font-family="serif" font-size="22" fill="#d4b483" text-anchor="middle">Ilustracja: {e}</text>
            </svg>""")
        return f"/uploads/{svg_filename}"
