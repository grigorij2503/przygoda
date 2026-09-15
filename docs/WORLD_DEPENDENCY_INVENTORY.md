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

Po etapie 6 `app/main.py` składa aplikację i rejestruje routery bez gałęzi
zależnych od świata. `dark_fantasy@1` jest nadal jedynym opublikowanym pakietem.
Klasy, startery, szybkie akcje, księgi zdolności, wskazówki cechy w opisie akcji,
słowniki wyposażenia i przeszukiwania,
łup/crafting, profil głównego przeciwnika i statusów, mapa, etykiety kroniki,
komunikaty lobby, narrator, ilustracje i fallback offline czytają przypięty
pakiet. Pozostałe nazwy `boss_*`/`magic_*` są adapterami kontraktu historycznej
kampanii, a kolorystyka i CSS nadal czekają na etap 7.

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

Po etapie 6 frontend bierze katalog klas, pięć etykiet cech, startery, szybkie
akcje, księgi, kronikę, profil przeciwnika i opcje scenariusza z `world_pack`
w `/api/session`. Poniższe historyczne zależności wskazują także pozostały
zakres etapu 7: warstwę wizualną i neutralną tożsamość PWA. Etap 7 dodał
serwerowe `data-theme`/meta koloru, trzynaście kontrolowanych tokenów,
`theme-bootstrap.js`, semantyczne nadpisania w `theme.css`, neutralny manifest
oraz wybór świata przy potwierdzonym restarcie MG. Nadal tylko Dark Fantasy jest
grywalne; Neon jest lokalnym podglądem, a nie drugim pakietem produkcyjnym.

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
| `css/modules/` | Cinzel, złoto, runy, `fantasy-card` | etap 7: semantyczne tokeny i kontrolowane motywy; alias `fantasy-card` jest zachowany dla zgodności DOM |
| manifest i meta | jedna ciemna tożsamość PWA | etap 7: neutralny manifest, dynamiczny meta kolor strony |
| `app/static/sw.js` | ręczna lista modułów CSS/JS Dark Fantasy | etap 7: cache dokładnie wersjonowanych modułów i motywu |

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
