# ⚔️ Gemini TTRPG Master (Multiplayer Turn-Based Web Game)

Kompletna, produkcyjna aplikacja webowa do rozgrywek turowych w klimacie **Dark Fantasy**, prowadzonych przez sztuczną inteligencję (**Gemini 3.8 Flash** jako bezstronny Mistrz Gry) z deterministycznym silnikiem rzutów kością po stronie backendu, kartami postaci w czasie rzeczywistym oraz generowaniem ilustracji przygody na żądanie (**Imagen 3**).

---

## 🌟 Główne Funkcjonalności

1. **AI Mistrz Gry (Gemini 3.8 Flash):**
   - Wymuszone formatowanie **Strict Structured Output JSON** (Pydantic).
   - Gemini interpretuje deterministyczne rzuty kośćmi wykonane przez backend i tworzy filmową narrację.
   - Dynamiczne przyznawanie punktów doświadczenia (XP), obrażeń/leczenia (HP) oraz generowanie łupów i artefaktów.
   - Sugerowanie plastycznych promptów dla sceny w języku angielskim dla Imagen 3.
2. **Deterministyczny Silnik Rzutów d20 (Backend):**
   - Kryptograficzny generator liczb losowych (`secrets` w Pythonie).
   - Automatyczna dedukcja cechy (Siła, Zręczność, Rozum, Charyzma) z tekstu akcji gracza.
   - Dynamiczne kalkulowanie modyfikatorów cech oraz założonego ekwipunku ($\text{Wynik} = d20 + \text{Cecha} + \text{Ekwipunek}$).
   - Klasyfikacja: *Krytyczny Sukces* (nat 20), *Sukces* ($\ge$ DC 12), *Częściowy Sukces* (DC-2 do DC-1), *Porażka*, *Krytyczna Porażka* (nat 1).
3. **Turn Gating (Blokada Tury):**
   - Tura rozstrzyga się dopiero, gdy **wszyscy żywi gracze** w pokoju zatwierdzą swoje akcje.
   - Licznik gotowości w czasie rzeczywistym (`X/Y graczy gotowych`).
   - Podczas generowania narracji przez Gemini formularz akcji jest blokowany.
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

---

## 📂 Struktura Projektu

```
├── app/
│   ├── __init__.py
│   ├── config.py              # Konfiguracja Pydantic V2 i zmienne .env
│   ├── database.py            # Asynchroniczny silnik SQLAlchemy (SQLite / aiosqlite)
│   ├── models.py              # Modele ORM: GameSession, Character, InventoryItem, Turn, PlayerAction
│   ├── schemas.py             # Schematy Pydantic i Structured Output JSON dla Gemini
│   ├── dice.py                # Deterministyczny silnik d20 z dedukcją atrybutów
│   ├── gemini_service.py      # Integracja Google GenAI (Gemini 3.8 Flash + Imagen 3)
│   ├── websocket_manager.py   # Menedżer WebSockets i broadcast zdarzeń
│   ├── main.py                # Aplikacja FastAPI, routing REST, cykl tury, WebSockets
│   ├── static/
│   │   ├── css/style.css      # Klimatyczne style Dark Fantasy, runy, paski HP/XP
│   │   └── js/app.js          # Reaktywna logika Alpine.js, WebSockets, Lightbox
│   └── templates/
│       └── index.html         # Szablon interfejsu (Tailwind CSS CDN + Alpine.js)
├── tests/
│   ├── test_dice.py           # Testy rzutów kośćmi i modyfikatorów
│   ├── test_turn_flow.py      # Testy API, autoryzacji i tworzenia postaci
│   └── test_full_resolution.py# Test pełnego cyklu rozstrzygania tury i awansu
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

# Model generowania ilustracji scen na żądanie
IMAGEN_MODEL=imagen-3.0-generate-002

# Hasło dostępu do sesji dla Ciebie i znajomych
ROOM_PASSWORD=dragon2026

# Konfiguracja sieci
HOST=0.0.0.0
PORT=8000
DATABASE_URL=sqlite+aiosqlite:///./ttrpg_game.db
SECRET_KEY=tajny_klucz_bezpieczenstwa_salt_2026

# Web Push (wygeneruj raz: python -m app.generate_vapid_keys --write-env --subject mailto:admin@twojadomena.pl)
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
VAPID_SUBJECT=mailto:admin@twojadomena.pl
```

Web Push wymaga HTTPS poza środowiskiem `localhost`. Po uzupełnieniu wartości VAPID
uruchom aplikację ponownie, wybierz postać i użyj przycisku `Push wył.` w panelu czatu.
Na iOS/iPadOS aplikacja musi być dodana do ekranu początkowego.

> **Uwaga:** Jeśli nie podasz klucza `GEMINI_API_KEY`, aplikacja automatycznie przełączy się na inteligentny symulator narracyjny offline z generatorami wektorowych grafik runicznych, dzięki czemu możesz w pełni przetestować mechanikę gry lokalnie przed podpięciem konta Google AI Studio!

---

## 🚀 2. Uruchomienie Lokalne (Python)

Wymagania: Python 3.11+

```bash
# 1. Utwórz i aktywuj wirtualne środowisko
python3 -m venv .venv
source .venv/bin/activate

# 2. Zainstaluj zależności
pip install -r requirements.txt

# 3. Uruchom testy automatyczne
python -m pytest tests/

# 4. Uruchom serwer developerski
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Aplikacja będzie dostępna pod adresem: `http://localhost:8000`.

---

## 🐳 3. Uruchomienie Produkcyjne (Docker & Docker Compose)

Uruchomienie za pomocą jednego polecenia:

```bash
# Zbudowanie obrazu i uruchomienie w tle
docker-compose up -d --build

# Sprawdzenie logów aplikacji
docker-compose logs -f ttrpg-game

# Zatrzymanie kontenera
docker-compose down
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

W projekcie znajduje się 6 testów weryfikujących wszystkie kluczowe komponenty:
```bash
.venv/bin/python -m pytest tests/ -v
```

Zakres testów:
- `tests/test_dice.py`:
  - Dedukcja atrybutów z treści deklaracji gracza (Siła, Zręczność, Rozum, Charyzma).
  - Obliczanie modyfikatorów z aktywnego ekwipunku.
  - Wyznaczanie progów sukcesu i deterministyczny rzut k20.
- `tests/test_turn_flow.py`:
  - Pobieranie strony głównej i weryfikacja hasła do pokoju.
  - Tworzenie postaci i przydzielanie startowego ekwipunku.
  - Składanie akcji tury i sprawdzanie stanu gotowości drużyny.
- `tests/test_full_resolution.py`:
  - Pełny cykl rozstrzygnięcia tury: przejście z Tury #1 do Tury #2, zapis narracji, aktualizacja HP/XP.

---

## 📜 Licencja & Zespół
Projekt stworzony jako silnik RPG nowej generacji łączący tradycyjne reguły stołowych gier fabularnych z mocą modeli Google Gemini & Imagen.
