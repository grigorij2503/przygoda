# ⚔️ Gemini TTRPG Master (Multiplayer Turn-Based Web Game)

Wieloosobowa aplikacja webowa do rozgrywek turowych w klimacie **Dark Fantasy**, prowadzonych przez sztuczną inteligencję (**Gemini 3.8 Flash** jako Mistrz Gry). Backend odpowiada za rzuty, zasady walki, rozwój postaci, ekwipunek i stan kampanii, a klienci synchronizują się w czasie rzeczywistym. Aplikacja obsługuje również mapę kampanii, bossów, magię, łup, crafting, czat, Web Push i generowanie ilustracji na żądanie (**Imagen 3**).

---

## 🌟 Główne Funkcjonalności

1. **AI Mistrz Gry (Gemini 3.8 Flash):**
   - Wymuszone formatowanie **Strict Structured Output JSON** (Pydantic).
   - Gemini interpretuje wyniki rzutów wykonanych przez backend i tworzy filmową narrację.
   - Narracja uwzględnia mechaniczne konsekwencje tury, rozwój postaci, walkę i stan świata zapisany przez backend.
   - Sugerowanie plastycznych promptów dla sceny w języku angielskim dla Imagen 3.
2. **Serwerowy Silnik Rzutów d20:**
   - Kryptograficznie bezpieczny generator liczb losowych (`secrets` w Pythonie); wynik jest losowy, a nie deterministyczny.
   - Automatyczna dedukcja cechy (Siła, Zręczność, Rozum, Charyzma) z tekstu akcji gracza.
   - Dynamiczne kalkulowanie modyfikatorów cech oraz założonego ekwipunku ($\text{Wynik} = d20 + \text{Cecha} + \text{Ekwipunek}$).
   - Klasyfikacja: *Krytyczny Sukces* (nat 20), *Sukces* ($\ge$ DC), *Częściowy Sukces* (DC-2 do DC-1), *Porażka*, *Krytyczna Porażka* (nat 1); domyślny próg to DC 12, lecz mechanika może go zmienić.
3. **Turn Gating (Blokada Tury):**
   - Tura rozstrzyga się dopiero, gdy **wszyscy żywi gracze** w pokoju zatwierdzą swoje akcje.
   - Licznik gotowości w czasie rzeczywistym (`X/Y graczy gotowych`).
   - Podczas generowania narracji przez Gemini formularz akcji jest blokowany.
   - Po określonym czasie drużyna może zagłosować nad akcją zastępczą nieaktywnej postaci; gracz może ją nadpisać przed rozstrzygnięciem.
4. **Ilustracje na Żądanie (Imagen 3):**
   - Przycisk *„🎨 Generuj ilustrację z tej tury”* przy każdej ukończonej turze.
   - Generowanie panoramicznych grafik 16:9 z podglądem pełnoekranowym (Lightbox).
   - Gotowy fallback na grafiki runiczne w trybie testowym bez klucza API.
5. **Karta Postaci w Czasie Rzeczywistym:**
   - Animowany pasek życia (HP) z pulsującym efektem krwi.
   - Pasek postępu doświadczenia (XP) i automatyczny **Level Up** (wyższe HP i rozwój atrybutów).
   - Zarządzanie ekwipunkiem: zakładanie/zdejmowanie oręża oraz picie mikstur leczących.
6. **Brama Pokoju i Kreator Postaci:**
   - Dostęp do pokoju po podaniu hasła (`ROOM_PASSWORD`).
   - Wybór istniejącej postaci lub kreator z alokacją punktów atrybutów i startowym ekwipunkiem.
   - Generator Wstępu do Kampanii AI (wybór scenariusza i motywu, generowanie wstępu i natychmiastowy reset stołu).
7. **Powiadomienia Web Push bez Firebase:**
   - Systemowe powiadomienia po zakończeniu tury oraz przy wzmiankach `@postać` i `@all`.
   - Subskrypcje są przypisane do wybranej postaci i działają po zamknięciu PWA.
8. **Mapa Kampanii:**
   - Proceduralna mapa powiązana z sesją, odkrywanie lokacji i przechodzenie wyłącznie pomiędzy sąsiednimi węzłami.
   - Historia odkrytych miejsc jest przechowywana w bazie i synchronizowana między graczami.
9. **Walka z Bossami i Efekty Statusu:**
   - Skalowane HP, pancerz, DC obrony, fazy, cechy specjalne i zapowiadane akcje bossa.
   - Osobne rozstrzyganie ataku, obrony, wsparcia i efektów czasowych postaci oraz przeciwnika.
10. **Magia Klasowa:**
    - Księga czarów Czarodzieja oraz modlitwy i cuda Kleryka.
    - Zdolności odblokowywane poziomami, walidowane po stronie backendu i powiązane z właściwą cechą postaci.
11. **Łup, Ekwipunek i Crafting:**
    - Łup z przeszukiwania lokacji i wspólna nagroda po pokonaniu bossa.
    - Typy, rzadkość, obrażenia, zajęte ręce i limity wyposażenia są egzekwowane przez backend.
    - Crafting zużywa trzy zgodne przedmioty i jest dostępny przez jedną turę po pokonaniu bossa.
12. **Narzędzia Społecznościowe i MG:**
    - Trwały czat drużyny, wzmianki, osobiste notatki oraz wspólne nadawanie nazw elementom świata.
    - Panel narzędzi administracyjnych jest odblokowywany osobnym `GM_PIN`; zawiera m.in. konfigurację scenariusza, reset kampanii, ponowienie i ręczne rozstrzygnięcie tury.
    - Interfejs działa jako instalowalna PWA z service workerem i układem dostosowanym do urządzeń mobilnych.

---

## 📂 Struktura Projektu

```
├── app/
│   ├── __init__.py
│   ├── config.py              # Konfiguracja Pydantic V2 i zmienne .env
│   ├── database.py            # Asynchroniczny silnik SQLAlchemy (SQLite / aiosqlite)
│   ├── models.py              # Modele ORM sesji, postaci, tur, czatu, mapy, push i głosowań
│   ├── schemas.py             # Schematy Pydantic i Structured Output JSON dla Gemini
│   ├── dice.py                # Serwerowe rzuty d20 i dedukcja atrybutów
│   ├── combat.py              # Intencje akcji, obrażenia, bossowie i efekty statusu
│   ├── inventory.py           # Sloty, zajęte ręce i aktywny ekwipunek
│   ├── loot.py                # Łup, przeszukiwanie i crafting
│   ├── magic.py               # Zdolności Czarodzieja i Kleryka
│   ├── map_generator.py       # Generowanie i serializacja mapy kampanii
│   ├── gemini_service.py      # Integracja Google GenAI (Gemini 3.8 Flash + Imagen 3)
│   ├── push_service.py        # Wysyłanie powiadomień Web Push
│   ├── generate_vapid_keys.py # Generator kluczy VAPID
│   ├── websocket_manager.py   # Menedżer WebSockets i broadcast zdarzeń
│   ├── main.py                # Aplikacja FastAPI, routing REST, cykl tury, WebSockets
│   ├── static/
│   │   ├── css/style.css      # Style Dark Fantasy i responsywny interfejs
│   │   ├── js/app.js          # Alpine.js, WebSockets, interakcje i Lightbox
│   │   ├── manifest.json      # Manifest instalowalnej PWA
│   │   ├── sw.js              # Service worker i obsługa Web Push
│   │   └── icons/             # Ikony aplikacji
│   └── templates/
│       └── index.html         # Szablon interfejsu (Tailwind CSS CDN + Alpine.js)
├── tests/
│   ├── test_combat.py         # Testy walki, wyposażenia i efektów statusu
│   ├── test_dice.py           # Testy rzutów kośćmi i modyfikatorów
│   ├── test_full_resolution.py # Test pełnego cyklu tury i awansu
│   ├── test_lobby_flow.py     # Testy lobby, gotowości i uprawnień MG
│   ├── test_loot.py           # Testy łupu oraz craftingu
│   ├── test_turn_flow.py      # Testy API, autoryzacji i akcji
│   └── test_websocket_chat.py # Test komunikacji czatu przez WebSocket
├── uploads/                   # Katalog na wygenerowane obrazy z Imagen 3
├── data/                      # Katalog na plik bazy SQLite (w Dockerze)
├── Dockerfile                 # Zoptymalizowany obraz produkcyjny Python 3.12-slim
├── docker-compose.yml         # Konfiguracja uruchomieniowa kontenera
├── requirements.txt           # Zależności Python
├── .env.example               # Wzór pliku środowiskowego
└── README.md                  # Dokumentacja techniczna
```

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

# 4. Uruchom testy automatyczne
python -m pytest tests/

# 5. Uruchom serwer developerski
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

Kontener przechowuje stan bazy w wolumenie `./data`, a wygenerowane grafiki w wolumenie `./uploads`, co zapewnia pełną trwałość danych przy restartach i aktualizacjach.

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
- `tests/test_combat.py`:
  - Rozpoznawanie intencji, skalowanie bossów, obrażenia, efekty statusu oraz walidacja używanego ekwipunku.
- `tests/test_dice.py`:
  - Dedukcja atrybutów z treści deklaracji gracza (Siła, Zręczność, Rozum, Charyzma).
  - Obliczanie modyfikatorów z aktywnego ekwipunku.
  - Wyznaczanie progów sukcesu i kontrolowany testowo rzut k20.
- `tests/test_full_resolution.py`:
  - Pełny cykl rozstrzygnięcia tury, zapis narracji, aktualizacja HP/XP i awans.
- `tests/test_lobby_flow.py`:
  - Konfiguracja lobby, gotowość graczy oraz kontrola dostępu do narzędzi MG.
- `tests/test_loot.py`:
  - Przyznawanie łupu, jednorazowe przeszukiwanie lokacji i zasady craftingu.
- `tests/test_turn_flow.py`:
  - Pobieranie strony głównej i weryfikacja hasła do pokoju.
  - Tworzenie postaci i przydzielanie startowego ekwipunku.
  - Składanie akcji tury i sprawdzanie stanu gotowości drużyny.
- `tests/test_websocket_chat.py`:
  - Wymiana wiadomości czatu przez WebSocket.

---

## 📝 Utrzymanie Dokumentacji

Każda zakończona zmiana w projekcie musi obejmować aktualizację `README.md` oraz `AGENTS.md` o informacje opisujące nowy lub zmieniony stan aplikacji. Dotyczy to również zmian funkcjonalnych, konfiguracji, struktury projektu, komend i procesu pracy. Na końcu podsumowania każdej zmiany należy zaproponować krótką, opisową nazwę commitu w języku angielskim.

---

## 📜 Licencja & Zespół
Projekt stworzony jako silnik RPG nowej generacji łączący tradycyjne reguły stołowych gier fabularnych z mocą modeli Google Gemini & Imagen.
