# Roadmapa wersjonowanych światów kampanii

## Cel

Rozwinąć aplikację z pojedynczej gry Dark Fantasy w silnik wielu kampanii bez
naruszania istniejącej rozgrywki. Silnik ma zachować wspólne zasady tur, rzutów
d20, HP/XP, walki, ekwipunku, mapy grafowej i synchronizacji, natomiast klasy,
zdolności, przedmioty, słownictwo, oprawa oraz instrukcje narratora mają pochodzić
z wersjonowanego pakietu świata.

Nie planujemy obecnie migracji do Reacta. FastAPI wspiera podział na routery przez
`APIRouter`, Alpine udostępnia rejestrowane komponenty i globalne magazyny stanu,
a Jinja obsługuje dziedziczenie, części i makra. Te mechanizmy wystarczają do
modularizacji obecnej aplikacji bez wymiany frameworka.

Źródła:

- [FastAPI: Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
- [Alpine.data](https://alpinejs.dev/globals/alpine-data)
- [Alpine.store](https://alpinejs.dev/globals/alpine-store)
- [Jinja: Template Designer Documentation](https://jinja.palletsprojects.com/en/stable/templates/)
- [Gemini: Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)
- [Alembic: Auto Generating Migrations](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- [MDN: CSS custom properties](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Cascading_variables/Using_custom_properties)
- [MDN: PWA theme_color](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Manifest/Reference/theme_color)

## Granica domeny

```text
                     WorldPack: id + wersja
                              |
          +-------------------+-------------------+
          |                   |                   |
     klasy i księgi      mapa i zawartość    motyw i słownictwo
          |                   |                   |
          +-------------------+-------------------+
                              |
                       Ruleset: d20_v1
                              |
        rzuty - tury - HP/XP - walka - ekwipunek - WebSocket
                              |
                 FastAPI API + Alpine/Jinja UI
```

Silnik pozostaje odpowiedzialny za mechanikę i trwały stan. Pakiet świata jest
deklaratywny i nie zawiera wykonywalnego Pythona, JavaScriptu ani dowolnego CSS.
Mechanika zdolności jest wybierana wyłącznie przez kontrolowane klucze, np.
`damage`, `heal`, `revive`, `scan`, `jam` i `protect`.

Pierwsza wersja utrzymuje kanoniczne atrybuty `strength`, `agility`, `intellect`
i `charisma`. Pakiet może zmieniać ich nazwy prezentacyjne, lecz nie znaczenie w
bazie ani kontrakcie silnika.

## Docelowy kontrakt pakietu

```text
WorldPack
|- id, version, display_name
|- ruleset_id
|- terminology
|- theme_id
|- classes[]
|  |- id, name, icon, primary_stat
|  |- starter_items[]
|  |- quick_actions[]
|  `- ability_book
|- abilities[]
|  |- intent, tested_stat, targeting
|  `- mechanic_key + mechanic_params
|- loot_tables
|- item_vocabulary
|- enemy_profile
|- map_profile
|- lore_categories
`- narrative_profile + image_art_direction
```

Pakiety będą przechowywane w repozytorium jako dane JSON walidowane modelami
Pydantic podczas startu. Dłuższe instrukcje narratora mogą pozostać osobnymi
plikami tekstowymi. Każda kampania zostanie przypięta do konkretnego `id` i
wersji; istniejące definicje wersji są niemutowalne.

## Etapy

### Etap 1 - kontrakt bezpieczeństwa

Status: zakończony 2026-09-14.

Zakres:

- spisanie stabilnego kontraktu obecnej rozgrywki;
- fixture `dark_fantasy_v1_contract.json`;
- przypadki regresyjne dla tras, odpowiedzi sesji, klas, starterów, ksiąg
  zdolności, mapy i podstawowych komunikatów WebSocket;
- katalog wszystkich zależności od świata;
- ADR opisujący pakiety, ich wersjonowanie i kompatybilność;
- aktualizacja `README.md` oraz `AGENTS.md`.

Etap nie zmienia kodu wykonawczego, publicznego API, schematu bazy ani DOM.

Kryterium zakończenia: obecna kampania Dark Fantasy jest opisana jako jawny
kontrakt, a kolejne refaktoryzacje mają maszynowy punkt odniesienia.

### Etap 2 - modularizacja backendu

Status: oczekuje na akceptację rozpoczęcia.

- utworzenie routerów: auth, admin, sessions, characters, actions, turns, chat,
  images i push;
- utworzenie serwisów sesji, postaci, tur, czatu i ilustracji;
- pozostawienie w `main.py` składania aplikacji, lifespan i rejestracji routerów;
- zachowanie adresów, kodów HTTP, formatów odpowiedzi i zdarzeń WebSocket.

Kryterium zakończenia: publiczna tabela tras i payloady są zgodne z fixture
etapu 1, a `main.py` nie zawiera logiki poszczególnych obszarów funkcjonalnych.

### Etap 3 - modularizacja Alpine, Jinja i CSS

- podział HTML na bramę, lobby, stół, historię, panel akcji, postać, ekwipunek,
  czat, mapę i modale;
- podział JavaScriptu na moduły funkcjonalne przy zachowaniu jednego głównego
  `rpgGame` w pierwszym kroku;
- wydzielenie lokalnych komponentów `Alpine.data` i współdzielonego stanu tam,
  gdzie przynosi to realną izolację;
- podział CSS na tokeny, bazę, komponenty i funkcje;
- aktualizacja listy zasobów oraz wersji cache service workera.

Kryterium zakończenia: zachowane selektory, formularze, synchronizacja,
responsywność, dostępność i zachowanie PWA.

### Etap 4 - jądro pakietów świata

- modele Pydantic `WorldPack` i typów składowych;
- rejestr pakietów oraz walidacja ID, wersji i odwołań;
- `ruleset_id="d20_v1"`;
- pierwszy, domyślny pakiet `dark_fantasy@1` zawierający obecną treść;
- endpoint katalogu światów;
- kontrolowany fallback wyłącznie do `dark_fantasy@1`.

Kryterium zakończenia: obecna kampania pobiera treść z rejestru, ale użytkownik
nie może jeszcze zmieniać świata.

### Etap 5 - wersjonowanie kampanii i migracje

- wdrożenie Alembic;
- dodanie `GameSession.world_pack_id` i `world_pack_version`;
- dodanie `Character.class_id` i ogólnego `PlayerAction.ability_id`;
- migracja istniejących kampanii do `dark_fantasy@1`;
- tymczasowe zachowanie `character_class`, `magic_book` i `magic_ability_id` jako
  adapterów kompatybilności;
- blokada zmiany świata w aktywnej kampanii.

Kryterium zakończenia: historyczna baza otwiera się bez utraty postaci, tur,
mapy, ilustracji, ekwipunku, czatu i kroniki.

### Etap 6 - generalizacja zawartości

- klasy, startery i szybkie akcje z pakietu;
- `magic_book` zastąpione domenowo przez `ability_book`;
- deklaratywne efekty i walidacja zdolności;
- słowniki przedmiotów, łup, rzadkości i crafting z profilu świata;
- ogólna rola przeciwnika zamiast wszędzie zaszytego `boss`;
- profile map, kroniki, komunikatów, narratora, ilustracji i fallbacku offline;
- frontend otrzymuje klasy i akcje wyłącznie z API.

Kryterium zakończenia: próbny pakiet można dodać bez warunków zależnych od świata
w routerach, walce i frontendzie.

### Etap 7 - motywy i wybór świata

- semantyczne tokeny kolorów, typografii, powierzchni i stanów;
- `data-theme` na korzeniu aplikacji;
- zastąpienie twardych klas kolorystycznych semantycznymi komponentami;
- zatwierdzona lista fontów, tekstur i ikon;
- wybór świata w narzędziach MG przed lobby;
- dynamiczny meta `theme-color` i cache zasobów motywu;
- neutralny manifest PWA reprezentujący silnik, nie pojedynczą kampanię.

Kryterium zakończenia: Dark Fantasy wygląda jak wcześniej, a próbny drugi motyw
zmienia wygląd bez duplikowania HTML.

### Etap 8 - pilot Neonowa Polska 3078

- klasy: Haker, Neurotechnik, Egzoochroniarz i Fixer;
- księgi: katalog hacków, protokoły neuro, systemy bojowe i sieć kontaktów;
- zdolności: włamanie, skan, zakłócenie, przejęcie drona, przeciążenie implantu
  i medyczny reboot;
- cyberdecki, wszczepy, broń impulsowa, pancerze i stymulanty;
- mapa futurystycznych dzielnic Polski oraz węzłów sieci;
- korporacje, gangi, autonomiczne systemy i konstrukty neuro;
- grafitowy motyw z cyjanem i magentą;
- osobny profil narracji oraz ilustracji.

Kryterium zakończenia: pełny cykl lobby, tury, zdolności, walki, łupu, mapy,
awansu i ilustracji działa dla pilota oraz nie zmienia Dark Fantasy.

### Etap 9 - pozostałe światy

Partia map i eksploracji:

- Archipelag Korsarzy;
- Piaski Magicznej Ekspedycji;
- Słowiańska Gromada.

Partia epok i hybryd:

- Front 1944: Relikty Nocy;
- Wiedźmy Pogranicza;
- Kurz, Ołów i Brzydkie Sprawy;
- Wyspy Kruczego Sztormu.

Partia skrajnych tonów:

- Wieczna Wojna Gwiazd;
- Katedry Popiołu;
- Norki pod Zielonym Wzgórzem.

Każdy pakiet otrzymuje walidację kontraktu treści i własny profil akceptacyjny.
Ostatnia partia celowo sprawdza space grimdark, brutalne dark action RPG oraz
spokojną przygodę, w której walka nie jest dominującą aktywnością.

## Zasady kompatybilności

- świata nie można zmieniać w połowie kampanii;
- zapisana kampania wskazuje niezmienny identyfikator i wersję pakietu;
- brak pakietu lub wersji jest jawnym błędem, a nie cichą podmianą zawartości;
- dotychczasowe pola API pozostają do czasu zakończenia okresu kompatybilności;
- pakiety nie mogą definiować kodu wykonawczego ani dowolnych zewnętrznych URL;
- structured output Gemini pozostaje wspólny dla wszystkich światów;
- nie dodajemy warunków `if world_id == ...` poza rejestrem i kontrolowanymi
  strategiami rulesetu;
- każdy etap aktualizuje `README.md`, `AGENTS.md` i inwentarz testów.

## Nazwy inspirowane istniejącymi markami

Produkcyjne pakiety powinny używać oryginalnych nazw, postaci i opisów. Sam pomysł
gatunku nie jest chroniony tak jak jego konkretne wyrażenie, a rozpoznawalne nazwy
mogą być chronione znakami towarowymi. Dlatego roadmapa używa oryginalnych nazw
roboczych zamiast nazw cudzych franczyz.

- [WIPO: What Can I Protect with a Copyright?](https://www.wipo.int/en/web/copyright/protection)
- [EUIPO: Trade mark registration FAQ](https://www.euipo.europa.eu/en/help-centre/tm/faq-registration)
