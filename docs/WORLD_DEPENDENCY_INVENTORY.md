# Inwentarz zależności obecnej kampanii od świata

Dokument jest punktem odniesienia dla etapów 2-7. Oznaczenie `silnik` oznacza
zachowanie wspólne dla wszystkich światów, a `pakiet` treść, która docelowo
powinna pochodzić z wersjonowanego `WorldPack`.

## Trwały model danych

| Miejsce | Stan obecny | Docelowa odpowiedzialność |
|---|---|---|
| `GameSession.setting_theme` | dowolny tekst, domyślnie Dark Fantasy | opis kampanii plus przypięty pakiet i wersja |
| `Character.character_class` | prezentacyjna polska nazwa klasy | adapter; docelowo stabilne `class_id` z pakietu |
| atrybuty postaci | cztery kolumny bez Percepcji | pięć kanonicznych cech; addytywne `perception=0` dla historii |
| `PlayerAction.magic_ability_id` | ID zdolności magicznej | adapter; docelowo ogólne `ability_id` |
| pola `active_boss_*` | nazewnictwo głównego przeciwnika | stan silnika z terminologią prezentowaną przez pakiet |
| `NamedLoreEntity.category` | boss, location, npc, weapon, attack | stabilne kategorie silnika z etykietami pakietu |
| `CampaignMap.layout` | graf odpowiedni dla podziemi | graf silnika wygenerowany przez profil mapy pakietu |

## Backend i mechanika

| Plik / obszar | Zależności od Dark Fantasy | Kierunek ekstrakcji |
|---|---|---|
| `app/main.py` lifespan | krypta, szkielety, miecze, fantasy image prompt | domyślna kampania z `dark_fantasy@1` |
| `app/main.py` proxy actions | boss, atak i obrona opisane fantasy | neutralne szablony lub szybkie akcje pakietu |
| `app/main.py` item claims | miecz, tarcza, topór, łuk, kostur itd. | `item_vocabulary` pakietu |
| `app/main.py` character creation | klasy rozpoznawane po fragmentach nazw i startery | `classes[].starter_items` |
| `app/main.py` session DTO | `magic_book` i `active_boss` | adapter plus `ability_book` i terminologia świata |
| `app/main.py` reset/setup | Dark Fantasy i karczma | wybór i inicjalizacja pakietu |
| `app/main.py` naming | broń jako domyślna nagroda | profil kroniki i przedmiotów |
| `app/main.py` turn resolution | magic ability i boss event types | ogólna zdolność i role encounter |
| `app/main.py` images | fallback Dark Fantasy | `image_art_direction` |
| `app/magic.py` | Czarodziej, Kleryk, księgi i polskie aliasy magii | ogólny katalog zdolności pakietu |
| `app/combat.py` | boss, fantasy statusy, specjalne Wskrzeszenie | silnik encounter oraz rejestr efektów zdolności |
| `app/dice.py` | słowa miecz, topór, łuk, magia, modlitwa | wspólny rdzeń plus słowniki pakietu |
| `app/dice.py` i schematy akcji | brak `perception`, obserwacja miesza się z Intelektem lub Zręcznością | osobne reguły Percepcji i stabilne rozróżnienie od analizy |
| `app/loot.py` | runiczne nazwy, eliksiry, klasy fantasy | tabele łupu i preferencje klasy z pakietu |
| `app/map_generator.py` | krypty, kaplice, grobowce, kuźnie | wspólny graf plus `map_profile` |
| `app/gemini_service.py` | Wiedźmin, Dark Souls, Warhammer, magia i bossowie | neutralny prompt bazowy plus profil narratora |
| `app/schemas.py` | przykłady fantasy, `magic_ability_id`, kategorie broni | neutralne schematy plus adapter kompatybilności |

## Frontend

| Miejsce | Zależności od Dark Fantasy | Kierunek ekstrakcji |
|---|---|---|
| `app/static/js/app.js` stan | domyślna klasa i scenariusz fantasy | domyślne wartości z aktywnego pakietu |
| szybkie akcje | cztery klasy zdefiniowane ponownie w JS | `classes[].quick_actions` z API |
| `magicBook` | nazwa i semantyka tylko dla magii | ogólne `abilityBook` z aliasem |
| etykiety statystyk | stałe polskie etykiety | prezentacyjne etykiety pakietu |
| kreator, karta, awans i panel MG | cztery pola statystyk | piąte pole Percepcji bez zwiększania puli punktów |
| kronika | stałe boss/location/npc/weapon/attack | stabilne ID i etykiety pakietu |
| mapa | ikony pomieszczeń podziemi | ikony bezpiecznie wybierane przez profil mapy |
| `index.html` kreator | cztery klasy i dokładne startery | renderowanie katalogu klas z API |
| `index.html` teksty | bohater, magia, boss, wyprawa | `terminology` i neutralne komponenty |
| `style.css` | Cinzel, złoto, runy, `fantasy-card` | semantyczne tokeny i `theme_id` |
| manifest i meta | jedna ciemna tożsamość PWA | neutralny manifest, dynamiczny meta kolor strony |
| service worker | jedna ręczna lista plików CSS/JS | cache wszystkich modułów i zasobów motywów |

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

## Planowane rozszerzenie: Percepcja

Fixture etapu 1 zachowuje cztery cechy, ponieważ opisuje aktualne zachowanie, a
nie stan docelowy. W etapie 5 Percepcja zostanie dodana do ORM, migracji, Pydantic,
API, rozpoznawania akcji, modyfikatorów przedmiotów, kreatora, karty, awansu i
narzędzi MG. Historyczne rekordy otrzymają wartość `0`. Nowe światy będą mogły
wyświetlać ją jako Percepcję, Czujność, Obserwację lub Sensory, zachowując
kanoniczne ID `perception`.

## Reguły przeglądu kolejnych etapów

- nowe odwołanie do konkretnego świata wymaga wskazania pola `WorldPack`;
- nowe `if world_id` poza rejestrem lub strategią rulesetu jest błędem projektu;
- zmiana istniejącego payloadu wymaga aktualizacji adaptera i fixture kontraktu;
- zmiana zachowania `dark_fantasy@1` jest jawna, a nie skutkiem ubocznym refaktoru;
- nazwy inspirowane cudzymi franczyzami nie trafiają do pakietów produkcyjnych.
