# Inwentarz zależności obecnej kampanii od świata

Dokument jest punktem odniesienia dla etapów 2-7. Oznaczenie `silnik` oznacza
zachowanie wspólne dla wszystkich światów, a `pakiet` treść, która docelowo
powinna pochodzić z wersjonowanego `WorldPack`.

## Trwały model danych

| Miejsce | Stan obecny | Docelowa odpowiedzialność |
|---|---|---|
| `GameSession.setting_theme` | dowolny opis kampanii obok `world_pack_id` i `world_pack_version` | prezentacyjny opis przypiętego pakietu |
| `Character.character_class` | prezentacyjna polska nazwa klasy obok stabilnego `class_id` | adapter do usunięcia po okresie zgodności |
| atrybuty postaci | pięć kolumn, historyczne `perception=0` | pięć kanonicznych cech rulesetu |
| `PlayerAction.magic_ability_id` | adapter zapisywany obok ogólnego `ability_id` | usunięcie adaptera po okresie zgodności |
| pola `active_boss_*` | nazewnictwo głównego przeciwnika | stan silnika z terminologią prezentowaną przez pakiet |
| `NamedLoreEntity.category` | boss, location, npc, weapon, attack | stabilne kategorie silnika z etykietami pakietu |
| `CampaignMap.layout` | graf odpowiedni dla podziemi | graf silnika wygenerowany przez profil mapy pakietu |

## Backend i mechanika

Po etapie 4 `app/main.py` nie zawiera zależności od konkretnego świata. Składa
aplikację i rejestruje routery, w tym katalog `/api/worlds`. Walidowany
`app/worlds/registry.py` ładuje `dark_fantasy@1`; startery i początkowa narracja
zostały już przeniesione do pakietu, a pozostałe hardkody są adapterami do
usunięcia w etapach 5-6.

| Plik / obszar | Zależności od Dark Fantasy | Kierunek ekstrakcji |
|---|---|---|
| `app/services/runtime.py` lifespan | pobiera tytuł, wstęp, pierwsze wyzwanie, sugestie i prompt obrazu z rejestru | przypięty pakiet kampanii po etapie 5 |
| `app/services/runtime.py` proxy actions | boss, atak i obrona opisane fantasy | neutralne szablony lub szybkie akcje pakietu |
| `app/services/runtime.py` item claims | miecz, tarcza, topór, łuk, kostur itd. | `item_vocabulary` pakietu |
| `app/services/character_service.py` tworzenie postaci | startery pochodzą z `classes[].starter_items`; aliasy i fallback zachowują stary kontrakt | stabilne `class_id` przypiętej kampanii po etapie 5 |
| `app/services/session_service.py` DTO sesji | `magic_book` i `active_boss` | adapter plus `ability_book` i terminologia świata |
| `app/services/session_service.py` reset/setup | Dark Fantasy i karczma | wybór i inicjalizacja pakietu |
| `app/services/session_service.py` naming | broń jako domyślna nagroda | profil kroniki i przedmiotów |
| `app/services/turn_service.py` rozstrzyganie | magic ability i boss event types | ogólna zdolność i role encounter |
| `app/services/image_service.py` ilustracje | fallback Dark Fantasy | `image_art_direction` |
| `app/magic.py` | Czarodziej, Kleryk, księgi i polskie aliasy magii | ogólny katalog zdolności pakietu |
| `app/combat.py` | boss, fantasy statusy, specjalne Wskrzeszenie | silnik encounter oraz rejestr efektów zdolności |
| `app/dice.py` | słowa miecz, topór, łuk, magia, modlitwa | wspólny rdzeń plus słowniki pakietu |
| `app/dice.py` i schematy akcji | brak `perception`, obserwacja miesza się z Intelektem lub Zręcznością | osobne reguły Percepcji i stabilne rozróżnienie od analizy |
| `app/loot.py` | runiczne nazwy, eliksiry, klasy fantasy | tabele łupu i preferencje klasy z pakietu |
| `app/map_generator.py` | krypty, kaplice, grobowce, kuźnie | wspólny graf plus `map_profile` |
| `app/gemini_service.py` | Wiedźmin, Dark Souls, Warhammer, magia i bossowie | neutralny prompt bazowy plus profil narratora |
| `app/schemas.py` | przykłady fantasy, `magic_ability_id`, kategorie broni | neutralne schematy plus adapter kompatybilności |

## Frontend

Po etapie 3 zależności pozostają funkcjonalnie takie same, ale nie są już
skupione w trzech dużych plikach. Poniższe ścieżki wskazują nowe miejsca
ekstrakcji do pakietów świata w etapach 4-7.

| Miejsce | Zależności od Dark Fantasy | Kierunek ekstrakcji |
|---|---|---|
| `app/static/js/modules/core.js` stan | domyślna klasa i scenariusz fantasy | domyślne wartości z aktywnego pakietu |
| `app/static/js/modules/session-character.js` szybkie akcje | cztery klasy zdefiniowane ponownie w JS | `classes[].quick_actions` z API |
| `session-character.js` `magicBook` | nazwa i semantyka tylko dla magii | ogólne `abilityBook` z aliasem |
| etykiety statystyk | stałe polskie etykiety | prezentacyjne etykiety pakietu |
| partiale postaci, kreatora, awansu i MG | cztery pola statystyk | piąte pole Percepcji bez zwiększania puli punktów |
| kronika | stałe boss/location/npc/weapon/attack | stabilne ID i etykiety pakietu |
| `story-map-proxy.js` i partial mapy | ikony pomieszczeń podziemi | ikony bezpiecznie wybierane przez profil mapy |
| `partials/modals/character_creation.html` | cztery klasy i dokładne startery | renderowanie katalogu klas z API |
| partiale Jinja | bohater, magia, boss, wyprawa | `terminology` i neutralne komponenty |
| `css/modules/` | Cinzel, złoto, runy, `fantasy-card` | semantyczne tokeny i `theme_id` |
| manifest i meta | jedna ciemna tożsamość PWA | neutralny manifest, dynamiczny meta kolor strony |
| `app/static/sw.js` | ręczna lista modułów CSS/JS Dark Fantasy | cache wszystkich modułów i zasobów motywów |

## Kontrakt pozostający w silniku

- blokada tury do czasu akcji wszystkich żywych postaci;
- serwerowy rzut d20 i poziomy wyniku;
- pięć kanonicznych atrybutów: Siła, Zręczność, Intelekt, Charyzma i Percepcja;
- HP, XP, poziomy, agonia, stabilizacja i śmierć;
- statusy i kontrolowany rejestr efektów;
- wyposażanie, sloty i zużywanie przedmiotów;
- graf mapy, odkrywanie oraz przejścia między sąsiednimi węzłami;
- trwały czat, notatki, kronika i głosowania proxy;
- WebSocket, Web Push, PWA i limit ilustracji;
- wspólny structured output narratora.

## Kontrakt przenoszony do pakietu

- nazwa i opis świata;
- klasy, ikony, główne cechy i startery;
- szybkie akcje oraz księgi zdolności;
- słowniki naturalnego języka specyficzne dla epoki;
- katalog przedmiotów, łup i nazwy rzadkości;
- profil głównego przeciwnika i etykiety statusów;
- typy lokacji, nazwy, opisy, ikony oraz układ mapy;
- kategorie i etykiety kroniki;
- terminologia UI;
- paleta, typografia, tekstura i bezpieczne zasoby;
- instrukcje narratora, ton i kierunek artystyczny ilustracji.

## Percepcja

Fixture kontraktu obejmuje już pięć cech. Etap 5 dodał Percepcję do ORM, Alembic,
Pydantic, API, rozpoznawania akcji, modyfikatorów przedmiotów, kontekstu narratora,
kreatora, kart, awansu i narzędzi MG. Historyczne rekordy otrzymują wartość `0`.
Nowe światy będą mogły wyświetlać ją jako Percepcję, Czujność, Obserwację lub
Sensory, zachowując kanoniczne ID `perception`.

## Reguły przeglądu kolejnych etapów

- nowe odwołanie do konkretnego świata wymaga wskazania pola `WorldPack`;
- nowe `if world_id` poza rejestrem lub strategią rulesetu jest błędem projektu;
- zmiana istniejącego payloadu wymaga aktualizacji adaptera i fixture kontraktu;
- zmiana zachowania `dark_fantasy@1` jest jawna, a nie skutkiem ubocznym refaktoru;
- nazwy inspirowane cudzymi franczyzami nie trafiają do pakietów produkcyjnych.
