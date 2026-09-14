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

Docelowy `d20_v1` ma pięć kanonicznych atrybutów: `strength`, `agility`,
`intellect`, `charisma` i `perception`. Percepcja odpowiada za zauważanie
szczegółów, czujność, tropienie, wykrywanie zasadzek, obserwację i korzystanie ze
zmysłów lub sensorów. Intelekt pozostaje cechą wiedzy, analizy, rozumowania,
techniki i rozwiązywania problemów. Pakiet może zmieniać nazwy prezentacyjne
atrybutów, lecz nie ich identyfikatory w bazie ani kontrakcie silnika.

Istniejący kontrakt `dark_fantasy_v1` celowo zapisuje obecny stan czterech cech.
Percepcja zostanie dodana addytywnie w etapie 5: historyczne postacie otrzymają
wartość `0`, ich pozostałe statystyki i HP nie zmienią się, a łączny budżet
punktów nowej postaci pozostanie taki jak wcześniej. Maksimum bazowe pozostanie
na poziomie 12. Percepcja zostanie następnie uwzględniona w interpretacji akcji,
ekwipunku, awansach, korekcie MG, API oraz wszystkich widokach postaci.

## Docelowy kontrakt pakietu

```text
WorldPack
|- id, version, display_name
|- ruleset_id
|- terminology
|- attributes[]: id, label, abbreviation, description
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

## Bezpieczny odbiór lokalny

Każdy etap kończy się osobną checklistą ręczną. Odbiór należy wykonywać na
oddzielnej bazie, ponieważ tworzenie postaci, akcje i reset kampanii zapisują stan.
Przy wariancie Docker można zbudować obraz, a następnie uruchomić jednorazową
instancję wskazującą plik `manual_review.db`:

```powershell
docker compose build
docker compose run --rm --service-ports -e DATABASE_URL=sqlite+aiosqlite:////app/data/manual_review.db ttrpg-game
```

Port 8000 musi być wolny, więc regularna lokalna instancja nie może działać w tym
samym czasie. Pliku `data/manual_review.db` nie należy używać jako produkcyjnego
zapisu kampanii. Jeżeli etap wymaga sprawdzenia migracji historycznych danych,
należy wskazać kopię właściwego pliku bazy pod inną nazwą, nigdy oryginał.

Po uruchomieniu ręczny odbiór odbywa się pod `http://localhost:8000`. Checklista
danego etapu opisuje różnice względem wspólnego minimum: logowanie, pobranie
sesji, wybór lub utworzenie postaci, odświeżenie strony i sprawdzenie połączenia
WebSocket.

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

Test lokalny: opcjonalny, ponieważ etap nie zmienia runtime. Po zbudowaniu obrazu
otworzyć aplikację, przejść przez bramę, wybrać postać i odświeżyć stronę. Obecny
stół, mapa, ekwipunek, księga zdolności i czat powinny wyglądać identycznie.

### Etap 2 - modularizacja backendu

Status: zakończony 2026-09-14.

- utworzenie routerów: auth, admin, sessions, characters, actions, turns, chat,
  images i push;
- utworzenie serwisów sesji, postaci, tur, czatu i ilustracji;
- pozostawienie w `main.py` składania aplikacji oraz konfiguracji lifespan i
  rejestracji routerów;
- zachowanie adresów, kodów HTTP, formatów odpowiedzi i zdarzeń WebSocket.

Implementacja zachowuje 59 dotychczasowych funkcji bez zmiany ich ciał. Fixture
`dark_fantasy_v1_contract.json` nie została zmieniona; test tabeli tras obsługuje
routery dołączane leniwie przez nowsze wersje FastAPI.

Kryterium zakończenia: publiczna tabela tras i payloady są zgodne z fixture
etapu 1, a `main.py` nie zawiera logiki poszczególnych obszarów funkcjonalnych.

Test lokalny: wymagany. Na bazie kontrolnej przejść przez logowanie, narzędzia MG,
lobby i gotowość, utworzyć postać, złożyć oraz poprawić akcję, zakończyć turę,
wysłać wiadomość czatu, otworzyć mapę, notatkę i ekwipunek. Po odświeżeniu stan
ma pozostać zapisany, a interfejs nie może zgłaszać błędu tury ani rozłączenia.

### Etap 3 - modularizacja Alpine, Jinja i CSS

Status: oczekuje na akceptację rozpoczęcia.

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

Test lokalny: wymagany na szerokim ekranie i w mobilnym trybie narzędzi
deweloperskich. Przeklikać wszystkie modale, zwijanie nagłówka i panelu akcji,
historię tur, mapę z zoomem i przesuwaniem, filtrowanie ekwipunku, czat, notatkę,
lightbox oraz obsługę klawiaturą. Następnie odświeżyć PWA, przełączyć chwilowo
tryb offline i wrócić online; nie może pojawić się stary JS lub brakujący partial.

### Etap 4 - jądro pakietów świata

- modele Pydantic `WorldPack` i typów składowych;
- rejestr pakietów oraz walidacja ID, wersji i odwołań;
- `ruleset_id="d20_v1"`;
- deklaracja pięciu kanonicznych atrybutów i ich etykiet, w tym `perception`;
- pierwszy, domyślny pakiet `dark_fantasy@1` zawierający obecną treść;
- endpoint katalogu światów;
- kontrolowany fallback wyłącznie do `dark_fantasy@1`.

Kryterium zakończenia: obecna kampania pobiera treść z rejestru, ale użytkownik
nie może jeszcze zmieniać świata.

Test lokalny: wymagany. Otworzyć katalog światów pod `/api/worlds`, potwierdzić
obecność wyłącznie `dark_fantasy@1`, a następnie przeklikać tworzenie każdej z
czterech obecnych klas. Startery, szybkie akcje, księgi, mapa i narracja muszą być
takie same jak przed wprowadzeniem rejestru.

### Etap 5 - wersjonowanie kampanii i migracje

- wdrożenie Alembic;
- dodanie `GameSession.world_pack_id` i `world_pack_version`;
- dodanie `Character.class_id` i ogólnego `PlayerAction.ability_id`;
- dodanie `Character.perception` z wartością `0` dla historycznych postaci;
- rozszerzenie schematów postaci, akcji, ekwipunku i korekty MG o `perception`;
- dodanie Percepcji do kreatora, karty, awansu i interpretacji akcji przy
  zachowaniu różnicy między spostrzeganiem a analizą intelektualną;
- zachowanie dotychczasowego budżetu punktów tworzenia postaci oraz formuły HP;
- migracja istniejących kampanii do `dark_fantasy@1`;
- tymczasowe zachowanie `character_class`, `magic_book` i `magic_ability_id` jako
  adapterów kompatybilności;
- blokada zmiany świata w aktywnej kampanii.

Kryterium zakończenia: historyczna baza otwiera się bez utraty postaci, tur,
mapy, ilustracji, ekwipunku, czatu i kroniki. Dotychczasowe postacie mają
Percepcję `0`, lecz nie zmienione pozostałe cechy, HP, XP ani poziom.

Test lokalny: wymagany w dwóch wariantach. Najpierw uruchomić aplikację na kopii
starszej bazy i sprawdzić kilka istniejących postaci, tur, mapę, czat oraz
ekwipunek; Percepcja powinna wynosić `0`. Następnie na czystej bazie utworzyć
postać z punktami Percepcji, sprawdzić limit całej puli, korektę MG, wydanie
punktu awansu na Percepcję oraz akcje typu „nasłuchuję”, „wypatruję zasadzki” i
„analizuję dokument”. Pierwsze dwie powinny wskazywać Percepcję, ostatnia
Intelekt.

### Etap 6 - generalizacja zawartości

- klasy, startery i szybkie akcje z pakietu;
- `magic_book` zastąpione domenowo przez `ability_book`;
- deklaratywne efekty i walidacja zdolności;
- słowniki przedmiotów, łup, rzadkości i crafting z profilu świata;
- ogólna rola przeciwnika zamiast wszędzie zaszytego `boss`;
- profile map, kroniki, komunikatów, narratora, ilustracji i fallbacku offline;
- etykiety wszystkich pięciu atrybutów oraz przedmioty wzmacniające Percepcję;
- frontend otrzymuje klasy i akcje wyłącznie z API.

Kryterium zakończenia: próbny pakiet można dodać bez warunków zależnych od świata
w routerach, walce i frontendzie.

Test lokalny: wymagany. Dla każdej obecnej klasy sprawdzić startery, szybkie
akcje, księgę zdolności, łup, crafting i akcję Percepcji. W narzędziach
deweloperskich potwierdzić, że frontend otrzymuje katalog klas, etykiety pięciu
cech i akcje z API, a ręczna zmiana nieznanego ID klasy lub zdolności kończy się
czytelnym błędem zamiast fallbackiem do Kleryka.

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

Test lokalny: wymagany na komputerze, telefonie i w trybie z ograniczonym ruchem.
W narzędziach MG wybrać kolejno dostępne motywy, sprawdzić kolory, fonty, focus,
kontrast, modale, paski HP/XP, mapę i piątą cechę. Po odświeżeniu oraz krótkim
przejściu offline aktywny motyw nie może migać, wracać do fantasy ani mieszać
zasobów z innym światem.

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

Test lokalny: wymagany jako pełna krótka kampania na czystej bazie. Wybrać
Neonową Polskę 3078, utworzyć kolejno Hakera, Neurotechnika, Egzoochroniarza i
Fixera, sprawdzić ich startery oraz księgi, wykonać hack, skan Percepcją, wsparcie
i zwykły atak, zakończyć starcie, zdobyć łup, przejść po mapie i wygenerować
ilustrację. Po restarcie aplikacji kampania musi zachować świat, motyw i klasy.
Na końcu utworzyć osobną kampanię Dark Fantasy i sprawdzić, że nie przejęła
cyberpunkowych nazw, przedmiotów ani kolorów.

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

Test lokalny: wymagany osobno dla każdego dodanego pakietu. Minimalna ścieżka to
wybór świata, obejrzenie wszystkich klas i pięciu cech, utworzenie dwóch różnych
postaci, użycie jednej zwykłej i jednej specjalnej zdolności, akcja Percepcji,
jedna zmiana lokacji, łup oraz restart aplikacji. Dla Norek pod Zielonym
Wzgórzem trzeba dodatkowo rozwiązać turę bez walki, aby potwierdzić, że narrator
i progresja nie wymuszają przeciwnika. Po każdej partii wykonać też krótki odbiór
Dark Fantasy oraz Neonowej Polski 3078 pod kątem przenikania treści i motywów.

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
