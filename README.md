# ⚔️ Gemini TTRPG Master (Multiplayer Turn-Based Web Game)

Wieloosobowy silnik rozgrywek turowych z opublikowanymi światami **Dark Fantasy** i **NeoKatowice 3077** (fikcyjny cyberpunk w Polsce), prowadzony przez sztuczną inteligencję (**Gemini 3.8 Flash** jako Mistrz Gry). Backend odpowiada za rzuty, walkę, rozwój postaci, ekwipunek i stan kampanii, a klienci synchronizują się w czasie rzeczywistym. Aplikacja obsługuje również mapę kampanii, kategoryzowaną kronikę, zdolności klasowe, łup, crafting, czat, Web Push i generowanie ilustracji na żądanie (**Imagen 3**).

---

## 🌟 Główne Funkcjonalności

1. **AI Mistrz Gry (Gemini 3.8 Flash):**
   - Wymuszone formatowanie **Strict Structured Output JSON** (Pydantic).
   - Gemini interpretuje wyniki rzutów wykonanych przez backend i tworzy filmową narrację.
   - Narracja uwzględnia mechaniczne konsekwencje tury, rozwój postaci, walkę i stan świata zapisany przez backend.
   - Sugerowanie plastycznych promptów dla sceny w języku angielskim dla Imagen 3.
2. **Serwerowy Silnik Rzutów d20:**
   - Kryptograficznie bezpieczny generator liczb losowych (`secrets` w Pythonie); wynik jest losowy, a nie deterministyczny.
   - Narracyjny opis gracza jest podstawowym źródłem zamiaru i testowanej cechy; ważone reguły rozpoznają dominującą czynność oraz sposób wykonania zamiast wybierać pierwszy napotkany wyraz.
   - Poboczne ozdobniki, takie jak okrzyk podczas ataku, nie przebijają fizycznej metody działania; przy niejednoznacznym ataku silnik korzysta z cechy używanej broni, a następnie z najlepiej pasującej cechy postaci.
   - Formularz na bieżąco pokazuje nieblokującą interpretację (`zamiar • cecha`), poziom niskiej pewności i krótkie uzasadnienie; gracz może opcjonalnie skorygować oba pola przed zatwierdzeniem bez rezygnowania ze swobodnego opisu.
   - Podgląd interpretacji działa przez osobny endpoint, a formularz czytelnie obsługuje zarówno błędy JSON, jak i tekstowe odpowiedzi serwera przy zatwierdzaniu akcji.
   - Dynamiczne kalkulowanie modyfikatorów cech oraz założonego ekwipunku ($\text{Wynik} = d20 + \text{Cecha} + \text{Ekwipunek}$).
   - Klasyfikacja: *Krytyczny Sukces* (nat 20), *Sukces* ($\ge$ DC), *Częściowy Sukces* (DC-2 do DC-1), *Porażka*, *Krytyczna Porażka* (nat 1); domyślny próg to DC 12, lecz mechanika może go zmienić.
3. **Turn Gating (Blokada Tury):**
   - Tura rozstrzyga się dopiero, gdy **wszyscy żywi gracze** w pokoju zatwierdzą swoje akcje.
   - Licznik gotowości w czasie rzeczywistym (`X/Y graczy gotowych`).
   - Podczas generowania narracji przez Gemini formularz akcji jest blokowany.
   - Po określonym czasie drużyna może zagłosować nad akcją zastępczą nieaktywnej postaci; gracz może ją nadpisać przed rozstrzygnięciem.
4. **Ilustracje na Żądanie (Imagen 3):**
   - Przycisk *„🎨 Generuj ilustrację z tej tury”* przy każdej ukończonej turze.
   - Każda kampania może wygenerować jedną ilustrację w ciągu dnia kalendarzowego; trwały, atomowo egzekwowany limit odnawia się o północy w strefie `Europe/Warsaw` i jest widoczny w interfejsie jako czas pozostały do kolejnej generacji.
   - Generowanie panoramicznych grafik 16:9 z podglądem pełnoekranowym (Lightbox).
   - Gotowy fallback na grafiki runiczne w trybie testowym bez klucza API.
5. **Karta Postaci w Czasie Rzeczywistym:**
   - Animowany pasek życia (HP) z pulsującym efektem krwi.
   - Pasek postępu doświadczenia (XP) i automatyczny **Level Up** (wyższe HP i rozwój atrybutów).
   - Zarządzanie ekwipunkiem: zakładanie/zdejmowanie oręża oraz picie mikstur leczących.
6. **Brama Pokoju i Kreator Postaci:**
   - Dostęp do pokoju po podaniu hasła (`ROOM_PASSWORD`), zintegrowane nowoczesne wektorowe logo d20 oraz instalacja PWA.
   - Wybór istniejącej postaci lub kreator z alokacją punktów atrybutów i startowym ekwipunkiem.
   - Generator Wstępu do Kampanii AI (wybór scenariusza i motywu, generowanie wstępu i natychmiastowy reset stołu).
7. **Powiadomienia Web Push bez Firebase:**
   - Systemowe powiadomienia po zakończeniu tury oraz przy wzmiankach `@postać` i `@all`.
   - Subskrypcje są przypisane do wybranej postaci i działają po zamknięciu PWA.
8. **Mapa Kampanii:**
   - Proceduralna mapa powiązana z sesją, odkrywanie lokacji i przechodzenie wyłącznie pomiędzy sąsiednimi węzłami.
   - Historia odkrytych miejsc jest przechowywana w bazie i synchronizowana między graczami.
   - Widok automatycznie kadruje odkryty obszar, obsługuje powiększanie, pomniejszanie, przeciąganie oraz szybki powrót do pozycji drużyny.
9. **Walka z Bossami i Efekty Statusu:**
   - Skalowane HP, pancerz, DC obrony, fazy, cechy specjalne i zapowiadane akcje bossa.
   - Osobne rozstrzyganie ataku, obrony, wsparcia wskazanego sojusznika i efektów czasowych postaci oraz przeciwnika.
   - Jawne stany `agonia → stabilny / śmierć`: postać w agonii otrzymuje jedną porażkę śmierci na turę, trzecia oznacza zgon; wsparcie może stabilizować lub podnieść bohatera.
10. **Magia Klasowa:**
    - Księga czarów Czarodzieja oraz modlitwy i cuda Kleryka.
    - Zdolności odblokowywane poziomami, walidowane po stronie backendu i powiązane z właściwą cechą postaci.
    - Szybkie akcje są dopasowane do klasy wybranego bohatera; Wojownik i Łotrzyk nie otrzymują propozycji czarów, a Czarodziej i Kleryk widzą wśród skrótów wyłącznie odblokowane zdolności ze swojej księgi lub modlitw.
    - Drużynowe podpowiedzi Gemini pozostają niemagiczne i dostępne dla każdej klasy; magia jest deklarowana wyłącznie przez wybór konkretnej zdolności klasowej.
    - Wybrana zdolność jawnie ustala swój zamiar i cechę rzucania; tych wartości nie zastępuje automatyczna interpretacja ozdobników dopisanych przez gracza.
    - Kleryk od 7. poziomu otrzymuje Wskrzeszenie, które jako jedyne zwykłe działanie może przywrócić poległego bohatera (25% PW, a przy krytycznym sukcesie 50% PW).
11. **Łup, Ekwipunek i Crafting:**
    - Łup z przeszukiwania lokacji i wspólna nagroda po pokonaniu bossa.
    - Typy, rzadkość, obrażenia, zajęte ręce i limity wyposażenia są egzekwowane przez backend.
    - Crafting zużywa trzy zgodne przedmioty i jest dostępny przez jedną turę po pokonaniu bossa.
    - Deklaracja użycia konkretnego wyposażenia jest walidowana również dla polskich znaków, np. „łuk”; niezapisane jeszcze przedmioty zachowują domyślną ilość jednej sztuki podczas rozliczania craftingu.
12. **Narzędzia Społecznościowe i MG:**
    - Trwały czat drużyny, wzmianki, osobiste notatki oraz wspólne nadawanie nazw elementom świata.
    - Kronika Świata automatycznie porządkuje nazwane odkrycia w działach: bossowie, miejsca, napotkani NPC, oręż i artefakty oraz ataki drużynowe; Gemini może wskazać napotkanego NPC do nazwania przez gracza.
    - Panel narzędzi administracyjnych jest odblokowywany osobnym `GM_PIN`; zawiera m.in. konfigurację scenariusza, reset kampanii, ponowienie i ręczne rozstrzygnięcie tury.
    - MG może awaryjnie skorygować bazowe atrybuty dowolnej postaci w zakresie `0–12`; panel pokazuje zmianę łącznej puli, wymaga potwierdzenia i synchronizuje korektę z graczami. Bonusy ekwipunku, niewydane punkty awansu i już złożone akcje nie są przeliczane.
    - Interfejs działa jako instalowalna PWA z service workerem, zwijanym nagłówkiem sesji i panelem akcji na telefonach oraz ekranach komputerowych do 1799 px, czytelniejszą typografią, semantycznymi modalami, obsługą klawiatury i trybem ograniczonego ruchu.
    - Po powrocie z uśpionej karty, zminimalizowanej przeglądarki lub zablokowanego urządzenia klient odtwarza WebSocket i pobiera aktualny stan tury; po co najmniej dwóch minutach nieobecności pokazuje krótkie powitanie wybranej postaci.
13. **Jądro Wersjonowanych Światów:**
    - Deklaratywne, niemutowalne modele Pydantic walidują identyfikatory, wersje, klasy, zdolności, startery, mapę, motyw, terminologię, kronikę, profile przeciwnika, tabele łupu, crafting, statusy i odwołania pakietu przy imporcie aplikacji.
    - Rejestr zawiera `dark_fantasy@1` i `neokatowice_3077@1` dla rulesetu `d20_v1`; katalog `GET /api/worlds` udostępnia ich bezpieczne podsumowania z motywem i scenariuszami. Narzędzia MG pozwalają wybrać pakiet dla nowego lobby przy potwierdzonym restarcie, ale nie przełączają trwającej rozgrywki w locie.
    - Każda kampania jest trwale przypięta do `world_pack_id` i `world_pack_version`, a postacie i zdolności zapisują stabilne `class_id` i `ability_id`. Dotychczasowe `character_class` oraz `magic_ability_id` pozostają adapterami zgodności.
    - Percepcja (`perception`, `PER`) jest piątą pełnoprawną cechą w bazie, API, kreatorze, karcie, lobby, awansie, korekcie MG, ekwipunku i interpretacji działań. Historyczne postacie otrzymują `0`, bez zmiany pozostałych cech, HP, XP ani poziomu.
    - Klasy, startery, szybkie akcje, ogólne księgi zdolności (`ability_book`), wskazówki cechy dla słownictwa świata, profile mapy, łup, rzadkości, crafting, etykiety statusów, prolog, narracja, kierunek ilustracji i fallback offline są pobierane z przypiętej wersji pakietu. `magic_book` i nazwy pól bossa pozostają adapterami dla dotychczasowej gry.
    - Frontend otrzymuje klasy, pięć etykiet cech, startery, księgi i akcje z API. Nieznany identyfikator klasy lub zdolności kończy się błędem bez podstawienia Kleryka. Zmiana świata aktywnej kampanii jest blokowana, a nieznana jawna wersja kończy się błędem.
    - Motyw pakietu używa trzynastu semantycznych kolorów oraz kontrolowanych ID fontu, tekstury, ikon i kształtu. NeoKatowice mają turkusowo-magentową paletę oraz ścięte narożniki kart; Dark Fantasy zachowuje zaokrąglony styl. Serwer ustawia `data-theme`/`data-shape` i meta `theme-color` przed pobraniem sesji; klient pamięta ostatni motyw dla odświeżenia offline. Lokalny podgląd Neon w narzędziach MG pozostaje prezentacją urządzenia, nie zmienia pakietu kampanii.
    - Pilot NeoKatowice osadza przygodę w fikcyjnym Śląsku roku 3077. Haker, Neurotechnik, Egzoochroniarz i Fixer mają własne startery, szybkie akcje i księgi hacków, neuroprotokołów, systemów bojowych lub kontaktów. Pakiet dostarcza dzielnice i ikony mapy, cybernetyczny łup, zagrożenia, teksty lobby, prolog, instrukcje narratora oraz kierunek ilustracji bez treści fantasy; fallback SVG używa kanciastego motywu.
    - Manifest PWA opisuje neutralny silnik „Przygoda”, a wersjonowane CSS/JS i service worker cache'ują także motyw. Schemat jest wersjonowany przez Alembic. Kontener wykonuje `alembic upgrade head` przed uruchomieniem serwera; bezpośredni start przez `uvicorn` zachowuje tymczasowy fallback dla starszych lokalnych baz.

---

## 📂 Struktura Projektu

```
├── app/
│   ├── __init__.py
│   ├── config.py              # Konfiguracja Pydantic V2 i zmienne .env
│   ├── database.py            # Asynchroniczny silnik SQLAlchemy (SQLite / aiosqlite)
│   ├── models.py              # Modele ORM sesji (w tym limit ilustracji), postaci, tur, nazwanych elementów świata, czatu, mapy, push i głosowań
│   ├── schemas.py             # Schematy Pydantic i Structured Output JSON dla Gemini
│   ├── dice.py                # Serwerowe rzuty d20 i dedukcja atrybutów z kontrolowanymi wskazówkami pakietu
│   ├── combat.py              # Ogólny profil głównego przeciwnika, zdolności, wsparcie, agonia/śmierć i statusy
│   ├── inventory.py           # Sloty, zajęte ręce i aktywny ekwipunek
│   ├── loot.py                # Łup, przeszukiwanie i crafting według pakietu świata
│   ├── magic.py               # Ogólne księgi zdolności i adaptery dawnej magii
│   ├── map_generator.py       # Mapa grafowa generowana z profilu świata
│   ├── gemini_service.py      # Integracja Google GenAI (Gemini 3.8 Flash + Imagen 3)
│   ├── push_service.py        # Wysyłanie powiadomień Web Push
│   ├── generate_vapid_keys.py # Generator kluczy VAPID
│   ├── websocket_manager.py   # Menedżer WebSockets i broadcast zdarzeń
│   ├── main.py                # Składanie FastAPI, middleware, mounty i rejestracja routerów
│   ├── api/
│   │   └── routers/           # Routery UI, auth, push, admin, sesji, postaci, tur, akcji, ilustracji, czatu i katalogu światów
│   ├── services/
│   │   ├── runtime.py         # Wspólne reguły pomocnicze, inicjalizacja i lifespan
│   │   ├── session_service.py # Odczyt, konfiguracja, reset i prolog kampanii
│   │   ├── character_service.py # Postacie, gotowość, rozwój, notatki i ekwipunek
│   │   ├── turn_service.py    # Interpretacja akcji i rozstrzyganie tur
│   │   ├── chat_service.py    # Trwały czat i obsługa WebSocket
│   │   ├── image_service.py   # Generowanie ilustracji oraz limit kampanii
│   │   └── world_service.py   # Publiczny katalog i deklaratywne dane świata dla UI
│   ├── worlds/
│   │   ├── models.py          # Niemutowalny kontrakt WorldPack i typy składowe
│   │   ├── registry.py        # Walidowany rejestr oraz kontrolowany fallback
│   │   └── packs/             # `dark_fantasy_v1.json` i `neokatowice_3077_v1.json`
│   ├── static/
│   │   ├── css/style.css      # Punkt wejścia kaskady CSS
│   │   ├── css/modules/       # Tokeny, baza, komponenty, ekwipunek, mapa, kronika, komunikaty, responsywność i motyw
│   │   ├── js/theme-bootstrap.js # Ustawienie motywu i kontrolowanego kształtu przed CSS
│   │   ├── js/app.js          # Składanie głównego komponentu Alpine `rpgGame`
│   │   ├── js/modules/        # Stan, PWA, auth/MG, sesja/postać, mapa/historia, realtime/czat, akcje i ekwipunek
│   │   ├── manifest.json      # Neutralny manifest instalowalnej PWA
│   │   ├── sw.js              # Service worker, cache modułów i obsługa Web Push
│   │   └── icons/             # Wektorowe logo d20 i komplet ikon PWA (192, 512, maskable, apple-touch, favicon)
│   └── templates/
│       ├── index.html         # Szkielet dokumentu i kolejność zasobów
│       └── partials/          # Brama, lobby, stół, panele funkcjonalne i osobne modale Jinja
├── tests/
│   ├── test_combat.py         # Testy walki, wyposażenia i efektów statusu
│   ├── test_current_world_contract.py # Kontrakt regresyjny bieżącego świata, tras, klas, ksiąg, mapy i UI
│   ├── test_dice.py           # Testy rzutów kośćmi i modyfikatorów
│   ├── test_frontend_module_contract.py # Partiale, zasoby, kaskada CSS, kolejność skryptów i cache PWA
│   ├── test_full_resolution.py # Test pełnego cyklu tury i awansu
│   ├── test_lobby_flow.py     # Testy lobby, gotowości i uprawnień MG
│   ├── test_loot.py           # Testy łupu oraz craftingu
│   ├── test_turn_flow.py      # Testy API, autoryzacji i akcji
│   ├── test_stage6_world_content.py # Próbny pakiet: klasy, księga, mapa, przeciwnik i walidacja mechanik
│   ├── test_stage7_theme_selection.py # Kontrolowane motywy i wybór świata tylko przy restarcie
│   ├── test_stage8_neokatowice_pilot.py # Klasy, księgi, startery, mapa, motyw i przypięta wersja pilota
│   ├── test_websocket_chat.py # Test komunikacji czatu przez WebSocket
│   ├── test_world_registry.py # Walidacja pakietów, odwołań, fallbacku i katalogu światów
│   └── test_world_migration.py # Migracja historycznej kampanii bez zmiany postępu
├── docs/
│   ├── WORLD_PACK_ROADMAP.md  # Etapowy plan przejścia do silnika wielu światów
│   ├── WORLD_DEPENDENCY_INVENTORY.md # Inwentarz hardkodów i granica silnik/pakiet
│   └── adr/
│       └── 0001-versioned-world-packs.md # Decyzja o deklaratywnych pakietach świata
├── uploads/                   # Katalog na wygenerowane obrazy z Imagen 3
├── data/                      # Katalog na plik bazy SQLite (w Dockerze)
├── alembic/                   # Środowisko i wersjonowane migracje schematu bazy
├── alembic.ini                # Konfiguracja migracji korzystająca z DATABASE_URL
├── Dockerfile                 # Zoptymalizowany obraz produkcyjny Python 3.12-slim
├── docker-compose.yml         # Konfiguracja uruchomieniowa kontenera
├── requirements.txt           # Zależności Python, w tym Alembic i dane stref czasowych
├── .env.example               # Wzór pliku środowiskowego
└── README.md                  # Dokumentacja techniczna
```

Etapy 6–8 nie dodają zmiennych `.env` ani osobnego buildu frontendu. Domyślny
pozostaje `dark_fantasy@1`; `neokatowice_3077@1` jest drugim grywalnym pakietem,
a podgląd Neon nie zmienia świata zapisanego w kampanii. Weryfikacja resetu,
tworzenia postaci i tur musi korzystać z osobnej bazy przez `DATABASE_URL` lub
z kopii zapisu, nie z aktywnej bazy. Ręczna checklista odbioru etapu 8 jest w
`docs/WORLD_PACK_ROADMAP.md`.

---

## ⚙️ 1. Konfiguracja Środowiska (.env)

Skopiuj plik wzorcowy do `.env`:
```bash
cp .env.example .env
```

Edytuj plik `.env`:
```ini
# Klucz API z Google AI Studio (https://aistudio.google.com/)
GEMINI_API_KEY=AIzaSy...twoj_klucz_api

# Najnowszy model z zaawansowanym myśleniem (General Availability wrzesień 2026)
GEMINI_MODEL=gemini-3.8-flash

# Model używany, gdy model główny jest niedostępny
GEMINI_FALLBACK_MODEL=gemini-3.6-flash

# Model generowania ilustracji scen na żądanie
IMAGEN_MODEL=imagen-3.0-generate-002

# Hasło dostępu do sesji dla Ciebie i znajomych
ROOM_PASSWORD=dragon2026

# Osobny PIN do narzędzi Mistrza Gry
GM_PIN=zmien_na_wlasny_pin

# Konfiguracja sieci
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite+aiosqlite:///./ttrpg_game.db
SECRET_KEY=tajny_klucz_bezpieczenstwa_salt_2026

# Web Push (wygeneruj raz: python -m app.generate_vapid_keys --write-env --subject mailto:admin@twojadomena.pl)
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
VAPID_SUBJECT=mailto:admin@twojadomena.pl

# Czas oczekiwania i długość głosowania nad akcją nieaktywnej postaci
PROXY_ACTION_WAIT_HOURS=8
PROXY_ACTION_VOTE_HOURS=2
```

Web Push wymaga HTTPS poza środowiskiem `localhost`. Po uzupełnieniu wartości VAPID
uruchom aplikację ponownie, wybierz postać i użyj przycisku `Push wył.` w panelu czatu.
Na iOS/iPadOS aplikacja musi być dodana do ekranu początkowego.

> **Uwaga:** Jeśli nie podasz klucza `GEMINI_API_KEY`, aplikacja automatycznie przełączy się na inteligentny symulator narracyjny offline z generatorami wektorowych grafik runicznych, dzięki czemu możesz w pełni przetestować mechanikę gry lokalnie przed podpięciem konta Google AI Studio!

---

## 🚀 2. Uruchomienie Lokalne (Python)

Wymagania: Python 3.11+

```powershell
# 1. Utwórz i aktywuj wirtualne środowisko w PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Zainstaluj zależności
python -m pip install -r requirements.txt

# 3. Utwórz lokalną konfigurację
Copy-Item .env.example .env

# 4. Zastosuj migracje bazy
python -m alembic upgrade head

# 5. Uruchom testy automatyczne
python -m pytest tests/

# 6. Uruchom serwer developerski
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

W systemach Linux/macOS środowisko aktywuje polecenie `source .venv/bin/activate`, a plik konfiguracyjny tworzy `cp .env.example .env`.

Aplikacja będzie dostępna pod adresem: `http://localhost:8000`.

---

## 🐳 3. Uruchomienie Produkcyjne (Docker & Docker Compose)

Uruchomienie za pomocą jednego polecenia:

```bash
# Zbudowanie obrazu i uruchomienie w tle
docker compose up -d --build

# Sprawdzenie logów aplikacji
docker compose logs -f ttrpg-game

# Zatrzymanie kontenera
docker compose down
```

Kontener przechowuje stan bazy w wolumenie `./data`, a wygenerowane grafiki w wolumenie `./uploads`, co zapewnia pełną trwałość danych przy restartach i aktualizacjach. Przed aktualizacją istniejącej kampanii wykonaj kopię pliku SQLite; kontener automatycznie uruchamia migracje Alembic przed startem API.

---

## 🌐 4. Wystawienie na Świat przez Cloudflare Tunnel

Cloudflare Tunnel pozwala na bezpieczne wystawienie aplikacji działającej lokalnie lub w Dockerze na Twoją domenę bez otwierania portów na routerze, bez publicznego IP i z darmowym certyfikatem SSL.

### Krok 1: Instalacja `cloudflared`
- **macOS:** `brew install cloudflared`
- **Linux (Ubuntu/Debian):**
  ```bash
  curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
  sudo dpkg -i cloudflared.deb
  ```

### Krok 2: Autoryzacja i Utworzenie Tunelu
```bash
# Zaloguj się na swoje konto Cloudflare
cloudflared tunnel login

# Utwórz nowy tunel o nazwie ttrpg-tunnel
cloudflared tunnel create ttrpg-tunnel
```
Polecenie zwróci identyfikator tunelu (UUID), np. `a1b2c3d4-e5f6-7890-abcd-ef1234567890`.

### Krok 3: Konfiguracja Pliku `config.yml`
Utwórz plik konfiguracyjny `~/.cloudflared/config.yml`:

```yaml
tunnel: a1b2c3d4-e5f6-7890-abcd-ef1234567890
credentials-file: /root/.cloudflared/a1b2c3d4-e5f6-7890-abcd-ef1234567890.json

ingress:
  - hostname: rmpg.twojadomena.pl
    service: http://localhost:8000
    originRequest:
      noTLSVerify: true
      connectTimeout: 30s
  # Opcjonalne reguły dla WebSockets (Cloudflare domyślnie wspiera WS)
  - service: http_status:404
```

### Krok 4: Podpięcie Domeny w Cloudflare (DNS Route)
```bash
cloudflared tunnel route dns ttrpg-tunnel rmpg.twojadomena.pl
```
To polecenie automatycznie utworzy rekord CNAME w Twojej strefie DNS w Cloudflare kierujący na tunel.

### Krok 5: Uruchomienie Tunelu
Testowe uruchomienie:
```bash
cloudflared tunnel run ttrpg-tunnel
```

Uruchomienie jako usługa systemowa w tle (systemd):
```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared
```

> **Ważne dla WebSockets:** W panelu Cloudflare (w zakładce *Network*) upewnij się, że opcja **WebSockets** jest włączona (`ON`). Dzięki temu synchronizacja tur i rzutów kością będzie działać z zerowym opóźnieniem.

---

## 🧪 5. Testy Jednostkowe i Integracyjne

Zestaw testów obejmuje mechanikę gry, API oraz komunikację czasu rzeczywistego:
```bash
python -m pytest tests/ -v
```

Zakres testów:
- `tests/test_current_world_contract.py`:
  - Chroni publiczną tabelę tras HTTP i WebSocket oraz nazwy zdarzeń czasu rzeczywistego przed przypadkową zmianą podczas modularizacji.
  - Rozwija routery dołączane leniwie przez FastAPI, dzięki czemu porównuje faktyczne endpointy z niezmienioną fixture również po podziale backendu.
  - Utrwala obecne klasy, startowy ekwipunek, księgi Czarodzieja i Kleryka, profil mapy Dark Fantasy, kształt odpowiedzi sesji i kluczowe elementy renderowanego UI.
  - Korzysta z fixture `tests/fixtures/dark_fantasy_v1_contract.json`, która jest punktem odniesienia dla przyszłego pakietu `dark_fantasy@1`.
  - Sprawdza kluczowe markery UI już po złożeniu wszystkich partiali Jinja.
  - Lokalizuje finał mapy przez stabilne `final_node_id`, niezależnie od kolejności dopisanych odnóg.
- `tests/test_combat.py`:
  - Rozpoznawanie dominującej intencji, w tym zdań zawierających mylące przysłowia lub wzmianki o innym typie akcji, skalowanie bossów, obrażenia, efekty statusu oraz walidacja używanego ekwipunku z polskimi znakami.
- `tests/test_dice.py`:
  - Dedukcja atrybutów z treści deklaracji gracza (Siła, Zręczność, Rozum, Charyzma i Percepcja), z ignorowaniem słabych ozdobników narracyjnych przy fizycznym ataku oraz rozdzieleniem obserwacji od analizy.
  - Obliczanie modyfikatorów z aktywnego ekwipunku.
  - Wyznaczanie progów sukcesu i kontrolowany testowo rzut k20.
- `tests/test_full_resolution.py`:
  - Pełny cykl rozstrzygnięcia tury, zapis narracji, aktualizacja HP/XP i awans.
- `tests/test_frontend_module_contract.py`:
  - Renderowanie wszystkich partiali Jinja i istnienie wskazanych zasobów lokalnych.
  - Kolejność modułów CSS i skryptów Alpine oraz kompletność wersjonowanego cache PWA.
- `tests/test_lobby_flow.py`:
  - Konfiguracja lobby, gotowość graczy oraz kontrola dostępu do narzędzi MG.
- `tests/test_loot.py`:
  - Przyznawanie łupu, jednorazowe przeszukiwanie lokacji i zasady craftingu, także dla niezapisanych obiektów ORM z domyślną ilością.
- `tests/test_turn_flow.py`:
  - Pobieranie strony głównej i weryfikacja hasła do pokoju.
  - Tworzenie postaci i przydzielanie startowego ekwipunku.
  - Składanie akcji tury i sprawdzanie stanu gotowości drużyny.
  - Izolowanie ponownego użycia tury 1 przez wyczyszczenie znaczników wcześniejszego rozstrzygnięcia.
- `tests/test_websocket_chat.py`:
  - Wymiana wiadomości czatu przez WebSocket z obsługą opcjonalnego początkowego snapshotu `CHAT_HISTORY` z wcześniej zapisanej bazy.
- `tests/test_world_registry.py`:
  - Ładowanie obu pakietów z domyślnym `dark_fantasy@1`, pięć kanonicznych cech rulesetu i zachowanie obecnych klas, starterów, ksiąg, mapy oraz narracji.
  - Odrzucanie nieznanej jawnej wersji i błędnych referencji oraz kontrakt odpowiedzi `GET /api/worlds`.
- `tests/test_stage8_neokatowice_pilot.py`:
  - Zawartość fikcyjnego Śląska, cztery księgi, startery potrzebne do zdolności, ikony mapy, kontrolowany kształt i przypięcie wersji świata.
- `tests/test_world_migration.py`:
  - Uruchomienie Alembic na historycznej bazie i kontrola backfillu świata, klasy, Percepcji oraz ogólnego ID zdolności bez zmiany postępu postaci.

---

## 🧭 Roadmapa silnika wielu światów

Rozwój w kierunku kampanii cyberpunkowych, pirackich, pustynnych, historyczno-okultystycznych, słowiańskich, wikińskich, westernowych, space-grimdark, infernalnych i pastoralnych jest podzielony na niezależnie odbierane etapy. Pełny plan znajduje się w [`docs/WORLD_PACK_ROADMAP.md`](docs/WORLD_PACK_ROADMAP.md), decyzja architektoniczna w [`docs/adr/0001-versioned-world-packs.md`](docs/adr/0001-versioned-world-packs.md), a aktualne sprzężenia fantasy w [`docs/WORLD_DEPENDENCY_INVENTORY.md`](docs/WORLD_DEPENDENCY_INVENTORY.md).

Etapy 1–7 są zakończone, a etapy 6–7 odebrane ręcznie. Kontrakt
`dark_fantasy_v1` utrwala obecną rozgrywkę, backend i frontend są podzielone na
moduły, a walidowany rejestr ładuje `dark_fantasy@1` oraz pilota
`neokatowice_3077@1`. Kampania zapisuje ID i wersję pakietu, klasy oraz
zdolności mają stabilne identyfikatory, a Alembic migruje historyczne dane.
Percepcja działa w całej ścieżce gry. Etap 8 jest zaimplementowany i czeka na
ręczny odbiór krótkiej kampanii NeoKatowice na osobnej bazie.

Ruleset używa pięciu kanonicznych atrybutów: Siły, Zręczności, Intelektu, Charyzmy i Percepcji. Migracja nadaje istniejącym postaciom Percepcję `0` bez zmiany pozostałych cech, HP, XP i poziomu. Roadmapa zawiera przy każdym etapie osobną checklistę ręcznego odbioru po lokalnym zbudowaniu aplikacji oraz instrukcję użycia izolowanej bazy `manual_review.db`.

---

## 📝 Utrzymanie Dokumentacji

Każda zakończona zmiana w projekcie musi obejmować aktualizację `README.md` oraz `AGENTS.md` o informacje opisujące nowy lub zmieniony stan aplikacji. Dotyczy to również zmian funkcjonalnych, konfiguracji, struktury projektu, komend i procesu pracy. Na końcu podsumowania każdej zmiany należy zaproponować krótką, opisową nazwę commitu w języku angielskim.

---

## 📜 Licencja & Zespół
Projekt stworzony jako silnik RPG nowej generacji łączący tradycyjne reguły stołowych gier fabularnych z mocą modeli Google Gemini & Imagen.
