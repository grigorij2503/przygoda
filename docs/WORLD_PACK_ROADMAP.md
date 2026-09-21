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

Kontrakt `dark_fantasy_v1` zapisuje obecny stan pięciu cech. Percepcja została
dodana addytywnie w etapie 5: historyczne postacie otrzymują wartość `0`, ich
pozostałe statystyki i HP nie zmieniają się, a łączny budżet punktów nowej
postaci pozostaje taki jak wcześniej. Maksimum bazowe nadal wynosi 12. Percepcja
jest uwzględniona w interpretacji akcji, ekwipunku, awansach, korekcie MG, API
oraz wszystkich widokach postaci.

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

Status: zakończony 2026-09-14.

- podział HTML na bramę, lobby, stół, historię, panel akcji, postać, ekwipunek,
  czat, mapę i modale;
- podział JavaScriptu na moduły funkcjonalne przy zachowaniu jednego głównego
  `rpgGame` w pierwszym kroku;
- wydzielenie lokalnych komponentów `Alpine.data` i współdzielonego stanu tam,
  gdzie przynosi to realną izolację;
- podział CSS na tokeny, bazę, komponenty i funkcje;
- aktualizacja listy zasobów oraz wersji cache service workera.

Implementacja zachowuje jeden komponent `rpgGame`, jego 302 właściwości i 54
gettery, ale składa go z funkcjonalnych modułów przez deskryptory właściwości.
Lokalne stany podpowiedzi i informacji o atrybutach są nazwanymi komponentami
`Alpine.data`. Render strony jest składany z partiali Jinja, a dotychczasowa
kaskada CSS została przeniesiona bez zmiany kolejności do modułów ładowanych
przez jeden arkusz wejściowy. Cache PWA `v30` zawiera wszystkie nowe zasoby.

Odbiór lokalny ujawnił również wcześniejsze niespójności niezależne od podziału
frontendu: transliterację litery `ł` w deklaracjach wyposażenia, obsługę
domyślnego `quantity` przed zapisem ORM oraz założenia testów o pozycji finału
mapy i ponownym użyciu rozstrzygniętej tury. Zostały skorygowane bez zmiany
kontraktu publicznego ani zawartości fixture Dark Fantasy.

Kryterium zakończenia: zachowane selektory, formularze, synchronizacja,
responsywność, dostępność i zachowanie PWA.

Test lokalny: wymagany na szerokim ekranie i w mobilnym trybie narzędzi
deweloperskich. Przeklikać wszystkie modale, zwijanie nagłówka i panelu akcji,
historię tur, mapę z zoomem i przesuwaniem, filtrowanie ekwipunku, czat, notatkę,
lightbox oraz obsługę klawiaturą. Następnie odświeżyć PWA, przełączyć chwilowo
tryb offline i wrócić online; nie może pojawić się stary JS lub brakujący partial.
Na izolowanej bazie lub kopii kampanii sprawdzić też przejście do sąsiedniego
pomieszczenia po udanej deklaracji, zachowanie opisu poprzedniej lokacji oraz
szare przebyte przejścia przy bieżącym węźle. Przyciski skali i przeciąganie
mają rzeczywiście zmieniać kadr mapy.

### Etap 4 - jądro pakietów świata

Status: zakończony i odebrany ręcznie 2026-09-14.

- modele Pydantic `WorldPack` i typów składowych;
- rejestr pakietów oraz walidacja ID, wersji i odwołań;
- `ruleset_id="d20_v1"`;
- deklaracja pięciu kanonicznych atrybutów i ich etykiet, w tym `perception`;
- pierwszy, domyślny pakiet `dark_fantasy@1` zawierający obecną treść;
- endpoint katalogu światów;
- kontrolowany fallback wyłącznie do `dark_fantasy@1`.

Implementacja ładuje deklaratywne pliki JSON przy imporcie rejestru i odrzuca
duplikaty, niepełne pary `id`/`version`, nieznane jawne wersje oraz błędne
odwołania do klas, motywu i zdolności. Wszystkie kolekcje pakietu są krotkami
zamrożonych modeli; mechanika jest wskazywana tylko kontrolowanymi kluczami.
Startery nowych postaci oraz narracja nowo tworzonej sesji domyślnej pochodzą z
`dark_fantasy@1`. Frontendowe szybkie akcje, runtime ksiąg, łup i generator mapy
pozostają jeszcze adapterami zgodności i zostaną przepięte w etapie 6.

Kryterium zakończenia: obecna kampania pobiera treść z rejestru, ale użytkownik
nie może jeszcze zmieniać świata.

Test lokalny: wymagany. Po zbudowaniu i uruchomieniu na izolowanej bazie otworzyć
`http://localhost:8000/api/worlds`. Odpowiedź ma wskazywać
`default_world.key="dark_fantasy@1"`, zawierać dokładnie jeden świat, cztery klasy
i pięć deklarowanych atrybutów zakończonych `perception`. Następnie w aplikacji
utworzyć kolejno Wojownika, Łotrzyka, Czarodzieja i Kleryka, sprawdzając ich trzy
startery. Dla Czarodzieja i Kleryka otworzyć księgę, użyć jednej szybkiej akcji,
odświeżyć stronę i otworzyć mapę. Nazwa kampanii, wstęp, startery, szybkie akcje,
księgi i mapa muszą pozostać takie same jak przed etapem 4; UI nie powinno jeszcze
oferować wyboru świata ani pola Percepcji.

### Etap 5 - wersjonowanie kampanii i migracje

Status: zakończony i odebrany ręcznie 2026-09-14.

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

Implementacja dodaje pierwszą rewizję Alembic i uruchamia ją automatycznie przed
API w kontenerze. Migracja jest addytywna: istniejącym sesjom przypisuje
`dark_fantasy@1`, mapuje polskie nazwy klas na stabilne ID, kopiuje
`magic_ability_id` do `ability_id` i nadaje historycznym postaciom Percepcję `0`.
Stare pola pozostają zapisywane i zwracane równolegle. Percepcja działa w rzutach,
przedmiotach, kontekście Gemini, kreatorze, wszystkich kartach postaci, ręcznej
korekcie akcji, awansie i panelu MG. Słowa dotyczące obserwacji, zmysłów,
tropienia i zasadzek kierują do Percepcji, a wiedza i analiza do Intelektu.

Kryterium zakończenia: historyczna baza otwiera się bez utraty postaci, tur,
mapy, ilustracji, ekwipunku, czatu i kroniki. Dotychczasowe postacie mają
Percepcję `0`, lecz nie zmienione pozostałe cechy, HP, XP ani poziom.

Test lokalny: wymagany w dwóch wariantach. Najpierw skopiować starszy plik SQLite
pod inną nazwą, ustawić kopię w `DATABASE_URL`, wykonać
`python -m alembic upgrade head` i dopiero uruchomić aplikację. W
`/api/session` potwierdzić `world_pack_id="dark_fantasy"`, wersję `1`, właściwe
`class_id` oraz Percepcję `0`; następnie sprawdzić kilka istniejących postaci,
tur, mapę, czat, księgi i ekwipunek. HP, XP, poziom i cztery stare cechy muszą być
niezmienione. Nigdy nie wykonywać odbioru na jedynej kopii aktywnej bazy.

W drugim wariancie uruchomić czystą `manual_review.db`, utworzyć postać z punktami
Percepcji i sprawdzić niezmieniony limit całej puli oraz wzór HP. Zweryfikować PER
w wyborze postaci, lobby, karcie i ręcznej korekcie cechy akcji; przez panel MG
zmienić Percepcję, a po przyznaniu punktu awansu wydać go na PER. Złożyć kolejno
akcje „nasłuchuję za drzwiami”, „wypatruję zasadzki” i „analizuję dokument”.
Pierwsze dwie mają wskazywać Percepcję, ostatnia Intelekt. Dla Czarodzieja użyć
zdolności i po odświeżeniu sprawdzić, że akcja zawiera zgodne `ability_id` oraz
`magic_ability_id`. Interfejs nadal nie powinien oferować zmiany świata.

### Etap 6 - generalizacja zawartości

Status: zaimplementowany i odebrany ręcznie z etapem 7 dnia 2026-09-15.

`dark_fantasy@1` pozostaje jedynym zarejestrowanym światem. Próbny, niepublikowany
pakiet jest sprawdzany przez kontrakt `tests/test_stage6_world_content.py` na
ogólnych interfejsach. UI nie oferuje jeszcze wyboru świata ani zmiany motywu;
obie rzeczy należą do etapu 7. Pola `magic_*`, `active_boss_*` i zdarzenia
`boss_*` pozostają adapterami zgodności dla istniejących kampanii.

- klasy, startery i szybkie akcje z pakietu;
- `magic_book` zastąpione domenowo przez `ability_book`;
- deklaratywne efekty i walidacja zdolności;
- słowniki przedmiotów, łup, rzadkości i crafting z profilu świata;
- kontrolowane wskazówki cechy dla słownictwa przyszłych światów, bez regexów
  ani wykonywalnego kodu w pakiecie;
- ogólna rola przeciwnika zamiast wszędzie zaszytego `boss`;
- profile map, kroniki, komunikatów, narratora, ilustracji i fallbacku offline;
- etykiety wszystkich pięciu atrybutów oraz przedmioty wzmacniające Percepcję;
- frontend otrzymuje klasy i akcje wyłącznie z API.

Kryterium zakończenia: próbny pakiet można dodać bez warunków zależnych od świata
w routerach, walce i frontendzie.

Test lokalny: wymagany wyłącznie na osobnej bazie SQLite albo kopii, nigdy na
aktywnym zapisie kampanii. Uruchomić lokalną aplikację lub własny kontener na tej
bazie i przejść od lobby do tury. Dla każdej obecnej klasy sprawdzić startery,
szybkie akcje, a dla Czarodzieja i Kleryka także `ability_book` oraz działanie
odblokowanej zdolności; Wojownik i Łotrzyk nie mają księgi. Potwierdzić łup z
lokacji, nagrodę po walce, crafting oraz akcję opartą na Percepcji. W odpowiedzi
`/api/session` sprawdzić `world_pack.classes`, pięć etykiet cech, `quick_actions`,
`ability_book`, `active_enemy` i kompatybilne `magic_book`/`active_boss`.
W formularzu postaci i akcji treść klas, starterów, ksiąg i skrótów ma zgadzać
się z API. W kopii można ręcznie wysłać nieznane `class_id` lub `ability_id`:
żądanie powinno zwrócić błąd, nie stworzyć Kleryka ani zamienić zdolności.
Odświeżyć PWA, sprawdzić mapę, kronikę, prolog i fallback ilustracji bez klucza
oraz upewnić się, że dotychczasowy wygląd Dark Fantasy jest niezmieniony.

### Etap 7 - motywy i wybór świata

Status: zaimplementowany i odebrany ręcznie z etapem 6 dnia 2026-09-15.
W chwili odbioru rejestr publikował tylko `dark_fantasy@1`, a Neon był lokalnym
podglądem. W etapie 8 do tego mechanizmu dołączono grywalny drugi pakiet.

- semantyczne tokeny kolorów, typografii, powierzchni i stanów;
- `data-theme` na korzeniu aplikacji;
- zastąpienie twardych klas kolorystycznych semantycznymi komponentami;
- zatwierdzona lista fontów, tekstur i ikon;
- wybór świata w narzędziach MG przed lobby;
- dynamiczny meta `theme-color` i cache zasobów motywu;
- neutralny manifest PWA reprezentujący silnik, nie pojedynczą kampanię.

Kryterium historycznego odbioru: Dark Fantasy wyglądało jak wcześniej, a próbny
drugi motyw zmieniał wygląd bez duplikowania HTML. Późniejsza aktualizacja
oprawy dodała małe metalowe okucia Dark Fantasy i neon NeoKatowic.

Test lokalny: wymagany na komputerze, telefonie i w trybie z ograniczonym ruchem,
na osobnej bazie SQLite albo kopii kampanii. Otworzyć narzędzia MG i sprawdzić,
że katalog świata pokazuje `Dark Fantasy • v1`. Wybrać jego scenariusz, wpisać
`RESETUJ`, otworzyć lobby, a następnie przejść do prologu i stołu. Zmiana świata
powinna nastąpić dopiero przy tym potwierdzonym restarcie, nie podczas aktywnej
tury. W narzędziach MG włączyć lokalny podgląd Neon, obejrzeć karty, przyciski,
focus/kontrast, modale, paski HP/XP, statusy, mapę, kronikę i Percepcję; wrócić
przyciskiem „Motyw kampanii” i potwierdzić wygląd Dark Fantasy z drobnymi
metalowymi okuciami kart. Podgląd
nie może zmienić pakietu ani widoku innego gracza. Odświeżyć stronę z włączonym
podglądem, a także po przywróceniu motywu kampanii: nie powinno być błysku
innej palety, `data-theme` i meta `theme-color` muszą odpowiadać widocznemu
motywowi. Krótkie odświeżenie offline powinno użyć ostatniego zapisanego motywu
tego świata, a cache powinien zawierać dokładnie wersjonowane zasoby etapu 7.
Nie ma jeszcze drugiej grywalnej kampanii do przeklikania; będzie odbierana
w etapie 8.

Zatwierdzone prezentacje etapu 7: fonty `Cinzel`, `Cinzel Decorative` i `Inter`;
tekstury `runes`, `grid`, `none`; zestawy ikon `classic`, `neutral`. Pakiet podaje
wyłącznie kontrolowane ID i trzynaście kolorów `#RRGGBB`; nie może wskazywać
zewnętrznych fontów, adresów assetów ani dowolnego CSS.

### Etap 8 - pilot NeoKatowice 3077

Status: zaimplementowany 2026-09-15 i odebrany ręcznie przez użytkownika przed etapem 9.
Publikowany pakiet `neokatowice_3077@1` przedstawia fikcyjne Katowice w Polsce
roku 3077. `dark_fantasy@1` pozostaje domyślnym; jego późniejsza aktualizacja
wizualna dodała cienkie metalowe okucia bez zmiany pakietu.

- klasy: Haker, Neurotechnik, Egzoochroniarz i Fixer;
- księgi: katalog hacków, protokoły neuro, systemy bojowe i sieć kontaktów;
- zdolności: włamanie, skan, zakłócenie, przejęcie drona, przeciążenie implantu
  i medyczny reboot;
- cyberdecki, wszczepy, broń impulsowa, pancerze i stymulanty;
- mapa futurystycznych dzielnic Katowic (m.in. Nikiszowiec, Szopienice,
  Ligota, Brynów) oraz węzłów sieci, z ikonami z pakietu;
- korporacje, gangi, autonomiczne systemy i konstrukty neuro;
- grafitowy motyw z turkusem i magentą oraz kontrolowanymi ściętymi narożnikami
  kart zamiast mocnych zaokrągleń;
- osobny profil narracji oraz ilustracji, w tym geometryczny fallback offline
  i krótkie teksty lobby bez karczmy.

Kryterium zakończenia: pełny cykl lobby, tury, zdolności, walki, łupu, mapy,
awansu i ilustracji działa dla pilota oraz nie zmienia Dark Fantasy.

Test lokalny: wymagany jako pełna krótka kampania na **czystej osobnej bazie
SQLite lub kopii**, nigdy na aktywnym zapisie. Nie ma osobnego buildu frontendu:
uruchomić aplikację lokalnie albo zbudować własny kontener wskazujący tę bazę.
W narzędziach MG wybrać `NeoKatowice 3077 • v1`, wpisać `RESETUJ` i potwierdzić
nowe lobby. Stworzyć Hakera, Neurotechnika, Egzoochroniarza i Fixera, sprawdzić
startery oraz cztery różne księgi. W turach użyć Włamania do sieci, Skanu
sensorycznego testującego Percepcję, wsparcia Rebootem medycznym ze wskazanym
sojusznikiem i ataku Egzoochroniarza; niedostępna zdolność wyższego poziomu ma
być odrzucona. Nazwać zagrożenie, rozegrać starcie i obejrzeć fazy/statusy,
znaleźć łup, otworzyć warsztat i przejść do sąsiedniego sektora mapy. Sprawdzić
śląskie nazwy, ikony sektorów, kronikę, ścięte narożniki kart, cienkie neonowe
obrysy przycisków, poświatę nagłówków, fokus i czytelność modali także na
telefonie. W widoku tury sprawdzić techniczne nagłówki i czytelną narrację bez
ozdobnego inicjału, metadane transmisji z numerem tury, cyjanowy panel akcji,
fioletowe moduły z jawną blokadą poziomu oraz zwarty czerwony HUD przeciwnika.
Porównać układ na telefonie i upewnić się, że metadane transmisji nie przechodzą
do Dark Fantasy. Bez klucza API sprawdzić
prolog, narrację i fallback ilustracji; z kluczem także wygenerowaną ilustrację
bez elementów fantasy. Po restarcie aplikacji kampania ma zachować świat, motyw
i klasy. Na osobnej kopii utworzyć nową kampanię Dark Fantasy i sprawdzić, że
nie przejęła cyberpunkowych nazw, starterów, mapy ani kolorów. Próba zmiany
świata w aktywnej kampanii bez potwierdzonego resetu ma pozostać zablokowana.

### Etap 9 - pozostałe światy

Status: zaimplementowany 2026-09-19; oczekuje na osobny ręczny odbiór użytkownika.
W rejestrze jest teraz 15 grywalnych pakietów: dwa wcześniejsze oraz 13 nowych.
Każdy nowy świat ma oryginalną nazwę i treść, minimum trzy klasy z własnymi
księgami, scenariusze, wyposażenie, łup, mapę, profil zagrożenia, narratora,
kierunek ilustracji i kontrolowany motyw. To warianty istniejącego `d20_v1`,
nie odrębne systemy reguł.

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

Partia śledztwa i humoru, dopisana na życzenie użytkownika:

- Szepty Zatopionej Gwiazdy — autorski horror kosmiczny inspirowany konwencją
  Lovecrafta, bez zapożyczania jego postaci i nazw;
- Zagadka Gazowej Latarni — detektyw doradczy, zagadka z uczciwymi wskazówkami,
  inspirowana konwencją Sherlocka bez powielania jego konkretnych spraw;
- Lochy, Łup i Kłopoty — lekkie, humorystyczne RPG o absurdalnym łupie,
  inspirowane komediową konwencją Munchkina bez kopiowania kart i zasad.

Nowe JSON-y używają ściśle walidowanego formatu `recipe_v1`. Loader rozwija
go przy starcie do pełnego, niemutowalnego `WorldPack`; dopiero taki pakiet trafia
do rejestru. Przepis deklaruje treść i identyfikatory kontrolowanych mechanik,
bez kodu, CSS, HTML i URL zasobów. Dark Fantasy oraz NeoKatowice zachowują swoje
dotychczasowe pełne JSON-y bez zmiany kontraktów i pozostają przypięte do v1.
Trzy spokojniejsze światy (Norki, Szepty, Zagadka) wyłączają wyłącznie
automatyczne wprowadzanie nazwanego wroga przez fallback offline; ręczne
rozpoczęcie starcia przez MG nadal jest możliwe. Ten znacznik jest cechą
profilu narracji, nie warunkiem zależnym od ID świata.

### Kierunek wizualny 15 światów

Własny moduł `theme-art.css` rozwija palety świata w typografię nagłówków,
teksturę tła i cienkie obramowanie kart. Zachowuje semantyczne kolory pakietu,
a dane `recipe_v1` i ich materializacja pozostają bez zmian. Wspólne kroje i
motywy tworzą rodziny, ale każda oprawa ma własny akcent. Długą narrację
składa czytelny krój o ograniczonej szerokości; na małym ekranie tekstury i
cienie pozostają lekkie.

| Świat | Motyw wizualny |
|---|---|
| Dark Fantasy | Klasyczna ciemna karta, cienkie metalowe okucia i nity w czterech narożnikach, subtelny złoty akcent. |
| NeoKatowice 3077 | Motyw `neo_katowice`: Rajdhani w nagłówkach, Space Grotesk w narracji, monospace w telemetrii, niemal czarne panele, cienkie cyjanowe kontury i ścięte narożniki. Aktywna sytuacja ma oprawę transmisji, deklaracja konsoli, zdolności modułów, a wróg zwartego czerwonego HUD. |
| Archipelag Korsarzy | Cormorant Garamond, subtelne linie atlasu i mosiężna karta. |
| Piaski Ekspedycji | Cormorant, promienie słońca i warstwice wydm. |
| Słowiańska Gromada | Cinzel, oszczędny motyw plecionki i drewna. |
| Front 1944: Relikty Nocy | Special Elite, linie akt i pasek teczki polowej. |
| Wiedźmy Pogranicza | Cormorant, ziołowe okręgi i miękki atrament. |
| Kurz, Ołów i Brzydkie Sprawy | Special Elite, księga pogranicza i sepiowa poświata. |
| Wyspy Kruczego Sztormu | Cormorant, ukośne linie deszczu i chłodne światło. |
| Wieczna Wojna Gwiazd | Rajdhani i Space Grotesk, rzadsza siatka mapy okrętu i wojskowe oznaczenie panelu. |
| Katedry Popiołu | Cinzel Decorative, ukośny ślad żaru i ciemnoczerwone krawędzie. |
| Norki pod Zielonym Wzgórzem | Fraunces, miękkie plamy koloru i zaokrąglone karty jak ilustrowana książka. |
| Szepty Zatopionej Gwiazdy | Cormorant, koncentryczne kręgi i zimna, niepokojąca poświata. |
| Zagadka Gazowej Latarni | Special Elite, linie notatnika i ślad czerwonego marginesu. |
| Lochy, Łup i Kłopoty | Bangers w nagłówkach, kropkowany raster, przerywana cienka kreska i komiksowe akcenty; narracja nadal jest czytelna. |

Kolejny kierunek dla ilustracji AI: nowa wersja pakietu „Lochy, Łup i Kłopoty”
mogłaby jawnie wymagać własnej dwuwymiarowej kreski tuszem, prostych kształtów
i komicznych póz. Opublikowanego kierunku ilustracji w `recipe_v1` nie zmieniamy
bez wersjonowania. Warto też stopniowo zastępować pozostałe kolory Tailwind
w szablonach semantycznymi klasami, a docelowo dostarczać lokalne podzbiory
fontów dla identycznego wyglądu offline.

Badania, na których oparto ograniczenia interfejsu: [MDN o dziedziczeniu tokenów
CSS](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Cascading_variables/Using_custom_properties),
[USWDS o typografii i długości wiersza](https://designsystem.digital.gov/components/typography/),
[WCAG 2.2 o kontraście i celach dotykowych](https://www.w3.org/TR/WCAG22/),
[metadane kroju Bangers](https://github.com/google/fonts/blob/main/ofl/bangers/METADATA.pb)
(w tym obsługa Latin Extended). Fonty mają kroje zapasowe, gdy Google Fonts
nie jest osiągalne.

Doprecyzowanie Dark Fantasy korzysta z ogólnego kierunku ciemnych materiałów i
kontrolowanego światła opisanego przez [zespół graficzny Diablo IV](https://news.blizzard.com/en-us/article/23964183/peeling-back-the-varnish-the-graphics-of-diablo-iv),
bez kopiowania gotowych elementów gry. NeoKatowice opierają proporcje światła
na dostarczonym przez właściciela zrzucie aplikacji mobilnej: prawie czarne
tło, cienkie kontury i selektywna poświata. Wielowarstwowy `text-shadow` jest
oparty na [dokumentacji MDN](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Text_decoration/Text_shadows);
nie nakładamy silnego blasku na całą długą narrację.

Narzędzia MG pokazują podgląd motywu aktualnie wybranego świata przed
potwierdzonym resetem. Jest on tymczasowy i lokalny: ponowny wybór aktualizuje
podgląd, przycisk „Motyw kampanii” go usuwa, a zmiana przypiętego świata po
resecie i zamknięcie narzędzi MG również go czyszczą. Nie zmienia to danych kampanii ani wyglądu u innych
graczy.

Odbiór lokalny: wymagany osobno dla każdego dodanego pakietu na **czystej
oddzielnej bazie SQLite albo kopii**, nigdy na aktywnej kampanii. Nie ma osobnego
buildu frontendu. Zbudować obraz i uruchomić go zgodnie z sekcją „Bezpieczny
odbiór lokalny” powyżej albo uruchomić lokalny serwer z takim `DATABASE_URL`.
Każdy świat wymaga potwierdzonego `RESETUJ`, więc dla kolejnego użyć kolejnej
czystej bazy albo świadomie zresetować wyłącznie bazę odbiorową. Minimalnie:
przed resetem nazwać odkrycie, a po utworzeniu nowego lobby potwierdzić pustą
Kronikę Świata i brak poprzedniej propozycji nazwania. Dalej
obejrzeć trzy klasy i pięć cech, stworzyć dwie różne postacie, otworzyć ich
księgi, wykonać zwykłą akcję i zdolność pierwszego poziomu, podjąć akcję
Percepcji, przejść do sąsiedniego węzła, znaleźć łup, sprawdzić motyw i
odświeżyć aplikację. Zdolność poziomu 3 powinna pozostać zablokowana na
poziomie 1. Obejrzeć nagłówek, kartę, narrację, mapę i formularz na telefonie;
sprawdzić czy litery z polskimi znakami nie zmieniają kroju, tekst mieści się
w panelach, ramki nie zabierają miejsca i po odświeżeniu wraca właściwy motyw.
W panelu MG wybrać inny świat i użyć „Wybrany świat — podgląd”: wygląd powinien
zmienić się bez resetu, a „Motyw kampanii” powinien odtworzyć aktywną oprawę.
Następnie użyć specyficznej ścieżki z tabeli:

W dwunastu z trzynastu światów z tabeli panel ekwipunku ma pokazać miękką,
neutralną sylwetkę w kolorach motywu. Norki mają własną rysunkową sylwetkę.
W każdym z nich sprawdzić sloty hełmu i butów oraz czytelne saldo i formularz
przekazania po nadaniu przedmiotu przez MG na izolowanej bazie. Tło i obramowanie
księgi zdolności mają korzystać z palety świata, a nie z fioletu pozostałego
po innym motywie.

| Świat / klucz | Dodatkowy odbiór przez UI |
|---|---|
| Archipelag Korsarzy / `archipelag_korsarzy@1` | Sprawdzić morski prolog, porty mapy, pirackie klasy i wyposażenie. |
| Piaski Ekspedycji / `piaski_ekspedycji@1` | Sprawdzić pustynne wykopaliska, mapę ruin i tropienie oparte na Percepcji. |
| Słowiańska Gromada / `slowianska_gromada@1` | Sprawdzić wiejskie problemy, słowiańskie role i rozwiązanie tury rozmową. |
| Front 1944 / `front_1944_relikty_nocy@1` | Sprawdzić frontowe wyposażenie, wojskowe i nadnaturalne zagrożenie oraz ton narracji. |
| Wiedźmy Pogranicza / `wiedzmy_pogranicza@1` | Sprawdzić księgi wiedźm, lokacje pogranicza i odrębny motyw. |
| Kurz i Ołów / `kurz_olow_brzydkie_sprawy@1` | Sprawdzić westernową lokację, klasę, broń i dialog jako alternatywę dla starcia. |
| Wyspy Kruczego Sztormu / `wyspy_kruczego_sztormu@1` | Sprawdzić wyspiarską mapę, role załogi i wyprawę przez kolejny węzeł. |
| Wieczna Wojna Gwiazd / `wieczna_wojna_gwiazd@1` | Sprawdzić skrajnie militarny ton science fiction, księgi i chłodny motyw. |
| Katedry Popiołu / `katedry_popiolu@1` | Sprawdzić mroczne ruiny, łup, crafting i fatalistyczny ton bez nazw cudzej serii. |
| Norki pod Zielonym Wzgórzem / `norki_zielonego_wzgorza@1` | Rozwiązać turę przy spokojnym zadaniu; fallback nie może sam wprowadzić wroga. Obejrzeć zielono-kremową księgę „Przepisy sąsiedzkie”, rysunkową sylwetkę oraz zaokrąglone sloty hełmu i butów na komputerze i telefonie. |
| Szepty Zatopionej Gwiazdy / `szepty_zatopionej_gwiazdy@1` | Rozwiązać śledztwo przy latarni bez walki; sprawdzić niepokój i brak automatycznego wroga. |
| Zagadka Gazowej Latarni / `zagadka_gazowej_latarni@1` | Porównać wskazówki w sprawie koperty, użyć dedukcji i zakończyć turę bez walki. |
| Lochy, Łup i Kłopoty / `lochy_lup_klopoty@1` | Sprawdzić absurdalny skarb, humor bez wyśmiewania graczy, czytelny komiksowy nagłówek i kreskę kart. |

Po odbiorze każdej partii krótko wrócić na osobnej kopii do Dark Fantasy i
NeoKatowic 3077: ich klasy, księgi, mapy, kolory i zapis kampanii nie mogą
przejmować treści nowego świata. Próba przełączenia aktywnej kampanii bez
potwierdzonego resetu nadal ma być blokowana.

Na izolowanej bazie odbiorowej sprawdzić także wspólne zasady: opis ataku
z imieniem towarzysza zadaje mu obrażenia bez wybierania celu w formularzu,
niejednoznaczny „kolega” wymaga imienia przy większej drużynie, a leczenie
może wskazać rzucającego. Pierwsze przeszukanie pomieszczenia zamyka dalsze
próby także po porażce lub pustym wyniku; zdobyty przedmiot trafia do
znalazcy i ma tę samą nazwę w narracji oraz plecaku. Jeśli pojawi się
przeklęty przedmiot, po założeniu karta pokazuje premię i karę. MG może
zapisać epilog, po czym historia pozostaje widoczna, a kolejne akcje są
zamknięte do nowego scenariusza.

### Odbiór skalowania trudności

Na osobnej bazie odbiorowej lub kopii kampanii uruchomić starcie najpierw jedną,
a potem czterema żywymi postaciami o porównywalnym poziomie i wyposażeniu.
Nowy przeciwnik powinien mieć więcej HP dla czwórki i odpowiadać na dwóch
różnych bohaterów w turze; samotnej postaci zadaje słabszy pojedynczy cios.
Po rozpoczęciu starcia zmiana składu drużyny nie przelicza jego maksymalnego HP
ani zapisanej liczby ataków, ale wróg nie wybiera więcej celów niż jest żywych
postaci. W tej samej kopii sprawdzić, że zwykła przeszkoda nadal ma DC 12,
trudna i kulminacyjna otrzymują wyższy próg przy wyższych poziomach, a atak na
aktywnego wroga używa jego DC obrony. Przy włączonym fallbacku offline tura 3
oznacza trudną próbę, a tura 5 kulminacyjną. Nie wykonywać tych zmian stanu na
aktywnej bazie kampanii.

### Odbiór ekwipunku i salda

Na osobnej bazie odbiorowej lub kopii kampanii po migracji `0003_inventory_wallet`
sprawdzić, że historyczne postacie mają saldo `0`, dotychczasowe przedmioty i
premie oraz dwa sloty dłoni, pancerz, hełm, buty i pięć aktywnych slotów.
W Dark Fantasy sylwetka powinna zachować płaszcz i zbroję, w NeoKatowicach
pokazać techniczną postać, a w innym świecie postać neutralną. Hełm ma być
nad głową sylwetki, buty pod jej stopami; długa nazwa broni i jej premie nie
mogą być ucięte. Na telefonie wszystkie sloty i formularz przekazania muszą
być czytelne.

W narzędziach MG nadać jednej postaci hełm i buty z premią najwyżej +1, założyć
je i sprawdzić zmianę cechy; założenie drugiego hełmu powinno odłożyć pierwszy
do plecaka. MG może przyznać i odjąć środki, lecz saldo nie może spaść poniżej
zera. W plecaku przekazać drugiej żyjącej postaci cały przedmiot i część stosu:
odbiorca widzi go po synchronizacji, nadawca traci właściwą ilość, a żadna
akcja tury nie powstaje. Przekaz podczas rozstrzygania tury ma być odrzucony.
Po udanym przeszukaniu oraz pokonaniu przeciwnika odbiorca łupu zyskuje także
środki. Opublikowane pakiety v1 nie otrzymują automatycznie nowych wpisów
łupu dla hełmów i butów; nadaje je MG. Dostęp do pokoju nie oznacza wyłącznego
własnictwa postaci, ponieważ gra nie ma indywidualnych kont graczy.

### Odbiór postoju i handlu

Na osobnej bazie odbiorowej lub kopii kampanii po migracji `0006_market_post`
pokonać głównego przeciwnika i przejść do następnej tury: warsztat powinien być
dostępny, a handlarz pojawiać się losowo bez zmiany oferty po odświeżeniu.
Gdy handlarza nie ma, MG może otworzyć go ręcznie. Sprawdzić zakup, sprzedaż
jednej sztuki stosu, brak salda ujemnego, jedną próbę negocjacji na postać i
odświeżenie drugiego klienta przez WebSocket. W warsztacie wybrać trzy konkretne
przedmioty tego samego typu, zatwierdzić akcję i upewnić się, że tylko udany
rzut zużywa składniki. W polu opisu przy stoisku podać wyraźną próbę kradzieży
i nazwę oferowanego przedmiotu; nie ma osobnego przycisku. Po przyłapaniu
sprawdzić karę do wysokości posiadanych środków, zamknięcie handlu dla tej
postaci, zmianę usposobienia NPC w Kronice i odmowę w następnym spotkaniu.
Sprawdzić również stojący portret właściwy dla motywu świata, czytelność karty
na telefonie i ikonę zastępczą przy brakującym pliku; własną grafikę można
podmienić w `app/static/img/merchants/<theme_id>.png` bez zmiany pakietu świata.
Następna tura oraz oba rodzaje restartu zamykają stary postój. Nie wykonywać
tych czynności na aktywnej bazie kampanii.

### Odbiór odkryć Kroniki

Na osobnej bazie lub kopii kampanii po migracji `0004_lore_discoveries` sprawdzić,
że stare wpisy Kroniki pozostają, a oczekująca propozycja nazwania zachowuje
pytanie po odświeżeniu. W turach przed ósmą i bez udanego ataku nie powinna
powstawać nowa technika. Po faktycznie opisanym, udanym ataku nazwać technikę,
wybrać ją z karty przypisanej postaci i porównać obrażenia: trafienie daje
dokładnie +1 po pancerzu, porażka 0, a jednoczesny wybór zdolności klasowej
jest niedostępny. Następna automatyczna okazja nie może pojawić się przez osiem
tur. Spotkać ważnego NPC w konkretnej lokacji, nadać mu imię, usposobienie i
cel i powiedzonko; przy ponownym spotkaniu zachowuje te cechy, ale nie powtarza
powiedzonka co turę. Restart scenariusza usuwa stare techniki i tożsamości NPC.

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
