# ⚔️ Gemini TTRPG Master (Multiplayer Turn-Based Web Game)

Wieloosobowy silnik rozgrywek turowych z 15 wersjonowanymi światami kampanii, w tym **Dark Fantasy**, **NeoKatowice 3077** (fikcyjny cyberpunk w Polsce), horrorem kosmicznym, zagadką detektywistyczną i humorystycznym RPG. Rozgrywkę prowadzi sztuczna inteligencja (**Gemini 3.8 Flash** jako Mistrz Gry). Backend odpowiada za rzuty, walkę, rozwój postaci, ekwipunek i stan kampanii, a klienci synchronizują się w czasie rzeczywistym. Aplikacja obsługuje również mapę kampanii, kategoryzowaną kronikę, zdolności klasowe, łup, postój z handlem i craftingiem, czat, Web Push i generowanie ilustracji na żądanie (**Imagen 3**).

---

## 🌟 Główne Funkcjonalności

1. **AI Mistrz Gry (Gemini 3.8 Flash):**
   - Wymuszone formatowanie **Strict Structured Output JSON** (Pydantic).
   - Gemini interpretuje wyniki rzutów wykonanych przez backend i tworzy filmową narrację.
   - Narracja uwzględnia mechaniczne konsekwencje tury, rozwój postaci, walkę i stan świata zapisany przez backend. Model nie ustala ani nie zmienia HP, XP, ekwipunku, statusów ani mechanicznego ruchu na mapie; otrzymuje gotowy dziennik zdarzeń i opisuje jego rezultat.
   - Sugerowanie plastycznych promptów dla sceny w języku angielskim dla Imagen 3.
2. **Serwerowy Silnik Rzutów d20:**
   - Kryptograficznie bezpieczny generator liczb losowych (`secrets` w Pythonie); wynik jest losowy, a nie deterministyczny.
   - Narracyjny opis gracza jest podstawowym źródłem zamiaru i testowanej cechy; ważone reguły rozpoznają dominującą czynność oraz sposób wykonania zamiast wybierać pierwszy napotkany wyraz.
   - Poboczne ozdobniki, takie jak okrzyk podczas ataku, nie przebijają fizycznej metody działania; przy niejednoznacznym ataku silnik korzysta z cechy używanej broni, a następnie z najlepiej pasującej cechy postaci.
   - Brak jeszcze niezapisanej lub historycznie nieuzupełnionej wartości cechy jest bezpiecznie traktowany jak `0`, także po dodaniu Percepcji do starszych postaci.
   - Formularz na bieżąco pokazuje nieblokującą interpretację (`zamiar • cecha`), poziom niskiej pewności i krótkie uzasadnienie; gracz może opcjonalnie skorygować oba pola przed zatwierdzeniem bez rezygnowania ze swobodnego opisu.
   - Atak na członka drużyny wskazuje cel w opisie akcji, bez listy celów ataku. Podgląd pokazuje rozpoznaną postać; przy niejednoznacznym „koledze” w większej drużynie trzeba dopisać imię.
   - Podgląd interpretacji działa przez osobny endpoint, a formularz czytelnie obsługuje zarówno błędy JSON, jak i tekstowe odpowiedzi serwera przy zatwierdzaniu akcji.
   - Dynamiczne kalkulowanie modyfikatorów cech oraz założonego, istotnego dla deklaracji ekwipunku ($\text{Wynik} = d20 + \text{Cecha} + \text{Ekwipunek}$). Broń i tarcza nie dodają premii do niezwiązanej czynności, jeden rzut korzysta najwyżej z jednej broni, a jawnie wymieniony oręż ma pierwszeństwo; klątwy pozostają aktywne podczas noszenia.
   - Klasyfikacja: *Krytyczny Sukces* (nat 20), *Sukces* ($\ge$ DC), *Częściowy Sukces* (DC-2 do DC-1), *Porażka*, *Krytyczna Porażka* (nat 1); domyślny próg to DC 12, lecz mechanika może go zmienić.
   - XP jest deterministycznie przypisane do zapisanego poziomu wyniku (`120/80/60/50/40`), więc ponowienie narracji nie zmienia nagrody.
   - Wyzwania poza walką mają zapisany poziom: zwykłe DC 12, trudne DC `min(25, 15 + średni poziom drużyny // 2)`, kulminacyjne DC `min(30, 18 + średni poziom drużyny // 2)`. Gemini wybiera poziom dla opisanego wyzwania, a serwer wylicza próg. W trybie offline trudniejsza próba przypada co trzecią turę, a kulminacyjna co piątą.
3. **Turn Gating (Blokada Tury):**
   - Tura rozstrzyga się dopiero, gdy **wszyscy żywi i aktywni gracze** w pokoju zatwierdzą swoje akcje.
   - Licznik gotowości w czasie rzeczywistym (`X/Y graczy gotowych`).
   - Podczas generowania narracji przez Gemini formularz akcji jest blokowany.
   - Po określonym czasie drużyna może zagłosować nad akcją zastępczą aktywnej postaci bez deklaracji; gracz może ją nadpisać przed rozstrzygnięciem.
  - MG może wysłać bohatera na odwracalną przerwę. Poziom, XP, HP, monety, ekwipunek i statusy pozostają bez zmian, a postać nie blokuje tur, nie otrzymuje rozwoju ani łupu, nie jest celem mechanik i nie trafia do bieżącego kontekstu narratora. Powrót włącza ją od otwartej tury bez przeliczania HP, pancerza ani DC już ustalonego starcia. Lista drużyny oznacza taką postać niebieskim statusem „Na przerwie”, a postać obezwładnioną stanem agonii/stabilizacji/śmierci zamiast „Czeka”; żadna z nich nie udostępnia głosowania nad ruchem zastępczym.
4. **Ilustracje na Żądanie (Imagen 3):**
   - Przycisk *„🎨 Generuj ilustrację z tej tury”* przy każdej ukończonej turze.
   - Każda kampania może wygenerować jedną ilustrację w ciągu dnia kalendarzowego; trwały, atomowo egzekwowany limit odnawia się o północy w strefie `Europe/Warsaw` i jest widoczny w interfejsie jako czas pozostały do kolejnej generacji.
   - Generowanie panoramicznych grafik 16:9 z podglądem pełnoekranowym (Lightbox).
   - Fallback ilustracji zgodny z motywem świata, dostępny bez klucza API.
5. **Karta Postaci w Czasie Rzeczywistym:**
   - Animowany pasek życia (HP) z pulsującym efektem krwi.
   - Pasek postępu doświadczenia (XP) i automatyczny **Level Up** (wyższe HP i rozwój atrybutów).
   - Zarządzanie ekwipunkiem: dwie dłonie (broń dwuręczna zajmuje obie), pancerz, osobne sloty hełmu i butów, pięć aktywnych przedmiotów oraz mikstury leczące. Hełm jest nad głową sylwetki, buty pod stopami, a nazwy i premie broni mieszczą się w kartach bez ucinania. Dark Fantasy pokazuje sylwetkę fantasy, NeoKatowice sylwetkę techniczną, Norki sylwetkę mieszkańca wzgórz, a pozostałe światy neutralną.
   - Plecak pozwala natychmiast przekazać wybraną liczbę sztuk żyjącej postaci z tej samej kampanii, bez akcji w turze; operacja jest niedostępna podczas rozstrzygania tury. Dostęp do pokoju jest potwierdzany podpisanym ciasteczkiem, ale aplikacja nadal nie ma osobnych kont przypisanych do postaci.
   - Każda postać ma trwałe saldo środków. Nagroda za pokonanie przeciwnika lub udane przeszukanie trafia do odbiorcy łupu; MG może dodać lub odjąć środki oraz nadać hełm albo buty z premią co najwyżej +1. Środki można wydawać podczas postoju.
6. **Wiele Równoległych Pokoi i Kreator Postaci:**
   - Brama przyjmuje kod pokoju i jego własne hasło. Każdy stół ma niezależną kampanię, świat, postacie, tury, mapę, kronikę, czat, postój, powiadomienia i dzienny limit ilustracji.
   - MG może utworzyć kolejny stół bezpośrednio na ekranie wejścia, wybierając świat, scenariusz i ton oraz podając nowy kod, hasło graczy i `GM_PIN`. Wybrany scenariusz jest zapisany od początku lobby. Link `/?room=kod-pokoju` otwiera właściwy stół, a powiadomienia Web Push prowadzą do przypisanej kampanii.
   - Hasła nowych stołów są zapisywane wyłącznie jako skróty PBKDF2. Podpisane ciasteczko wskazuje konkretny pokój; API i WebSocket odrzucają próbę użycia dostępu do innej kampanii.
   - Istniejąca `kampania-1` oraz jej postacie i postęp pozostają bez zmian. Przy pierwszym logowaniu dotychczasowy `ROOM_PASSWORD` zostaje przeniesiony do skrótu hasła tej sesji.
   - Wybór istniejącej postaci lub kreator z alokacją punktów atrybutów, startowym ekwipunkiem i formą narracji: męską, żeńską albo neutralną. To ustawienie wpływa wyłącznie na język opowieści; nie zmienia statystyk, klasy ani mechaniki i nie jest odgadywane z imienia.
   - Generator Wstępu do Kampanii AI (wybór scenariusza i motywu, generowanie wstępu i natychmiastowy reset stołu).
7. **Powiadomienia Web Push bez Firebase:**
   - Systemowe powiadomienia po zakończeniu tury oraz przy wzmiankach `@postać` i `@all`.
   - Subskrypcje są przypisane do wybranej postaci i działają po zamknięciu PWA.
8. **Mapa Kampanii:**
   - Proceduralna mapa powiązana z sesją, odkrywanie lokacji i przechodzenie wyłącznie pomiędzy sąsiednimi węzłami.
   - Udana deklaracja przejścia wskazuje sąsiednią lokację również wtedy, gdy odpowiedź narratora nie zawiera poprawnego ruchu mapy; jawnie nazwana sąsiednia lokacja ma pierwszeństwo. Narrator uzupełnia kronikę, ale nie może sam przenieść drużyny po nieudanym rzucie. Opis poprzedniego pokoju pozostaje przypisany do jego węzła.
   - Historia odkrytych miejsc jest przechowywana w bazie i synchronizowana między graczami.
   - Widok automatycznie kadruje odkryty obszar, obsługuje powiększanie, pomniejszanie, przeciąganie oraz szybki powrót do pozycji drużyny. Przebyte połączenia i drzwi są odróżnione od niezbadanych przejść.
9. **Starcia i Efekty Statusu:**
   - HP nowego głównego zagrożenia odpowiada około 3–4 turam oczekiwanych obrażeń żywej drużyny, z uwzględnieniem trafień k20, wyposażenia i pancerza. Parametry starcia są ustalane przy jego rozpoczęciu; pancerz, DC obrony, fazy, cechy specjalne i zapowiadane akcje nadal działają. Spokojniejsze kampanie mogą prowadzić tury bez starcia.
  - Wróg odpowiada raz przy 1–2 żywych graczach, dwa razy przy 3–4 i trzy razy przy co najmniej 5; wybiera różne cele. Liczba zapisana przy utworzeniu starcia jest maksimum, a każda odpowiedź i jej zapowiedź są ograniczane do aktualnej liczby uczestniczących żywych postaci. Samotny bohater otrzymuje słabszy pojedynczy cios. Trwające wcześniej starcia bez zapisanego licznika zachowują najwyżej jedną odpowiedź na turę.
   - Osobne rozstrzyganie ataku, obrony, wsparcia wskazanego sojusznika i efektów czasowych postaci oraz przeciwnika.
   - Jawna próba ugaszenia płomieni lub uwolnienia się z lodu jest obroną. Sukces usuwa status przed jego obrażeniami w tej turze, częściowy sukces go osłabia, a porażka pozostawia efekt aktywny. Późniejszy cios przeciwnika może nałożyć efekt ponownie, co jest pokazane jako osobne zdarzenie.
   - Trafienie w członka drużyny odejmuje HP przez silnik, także poza starciem z głównym przeciwnikiem; rzut kamieniem ma niższe obrażenia improwizowane. Leczenie i oczyszczenie mogą wskazywać samego rzucającego, wskrzeszenie pozostaje skierowane do innej poległej postaci.
   - Zwykłe wsparcie, takie jak odwrócenie uwagi, daje ochronę zamiast nieuzasadnionego leczenia. HP przywraca tylko deklaracja leczenia lub zdolność lecznicza, a oczyszczenie usuwa wyłącznie wskazane statusy.
  - Jawne stany `agonia → stabilny / śmierć`: postać w agonii otrzymuje jedną porażkę śmierci na turę, trzecia oznacza zgon; każda udana zwykła akcja wsparcia może ją ustabilizować bez przywracania PW, a zdolność lecząca może ją podnieść. Gdy cała aktywna drużyna jest obezwładniona, panel tury przechodzi w tryb kryzysowy: MG może zakończyć kampanię albo zarządzić awaryjny odwrót, który zamyka starcie, usuwa szkodliwe efekty i przywraca postacie w agonii/stabilne z 1 PW bez wskrzeszania poległych i bez zmiany postaci na przerwie.
  - Zakończona tura rozdziela „cel akcji” od niezależnych konsekwencji i pokazuje mechaniczny zapis premii ekwipunku, zdjętych/osłabionych statusów, udanego lub nieskutecznego wsparcia i zdolności, obrażeń ze statusów, ciosów przeciwnika i redukcji obrony. Łączna zmiana zdrowia jest oznaczona jako bilans całej tury, więc sukces działania nie wygląda jak źródło późniejszego kontrataku.
10. **Zdolności Klasowe:**
    - Każda klasa używa księgi właściwej swojemu światu: od czarów Czarodzieja i modlitw Kleryka po hacki, dedukcję lub komediowe sztuczki.
    - Zdolności odblokowywane poziomami, walidowane po stronie backendu i powiązane z właściwą cechą postaci.
    - Szybkie akcje są dopasowane do klasy wybranego bohatera; Wojownik i Łotrzyk nie otrzymują propozycji czarów, a Czarodziej i Kleryk widzą wśród skrótów wyłącznie odblokowane zdolności ze swojej księgi lub modlitw.
    - Drużynowe podpowiedzi Gemini pozostają niemagiczne i dostępne dla każdej klasy; magia jest deklarowana wyłącznie przez wybór konkretnej zdolności klasowej.
    - Wybrana zdolność jawnie ustala swój zamiar i cechę rzucania; tych wartości nie zastępuje automatyczna interpretacja ozdobników dopisanych przez gracza.
    - Kleryk od 7. poziomu otrzymuje Wskrzeszenie, które jako jedyne zwykłe działanie może przywrócić poległego bohatera (25% PW, a przy krytycznym sukcesie 50% PW).
11. **Łup, Ekwipunek i Crafting:**
    - Jedna próba przeszukania na pomieszczenie, także po porażce. Udana próba może trafić na pustą lokację (20%); znaleziony przedmiot i monety otrzymuje przeszukujący. Nagroda po pokonaniu głównego przeciwnika pozostaje wspólna. Narracja znalezisk jest uzgadniana z zapisem mechaniki.
    - Część znalezionych przedmiotów jest przeklęta: premia co najmniej +2 do cechy głównej i kara −1 do innej cechy działają tylko po założeniu; obie wartości widać w ekwipunku.
    - Typy, rzadkość, obrażenia, zajęte ręce i limity wyposażenia są egzekwowane przez backend.
    - Hełmy i buty mają osobne typy i sloty. Opublikowane pakiety v1 zachowują swoje tabele łupu, dlatego nowe elementy ochronne nadaje MG; trzy przedmioty tego samego typu można później wykorzystać w craftingu.
    - Crafting zużywa trzy zgodne przedmioty i jest dostępny przez jedną turę po pokonaniu bossa.
    - W turze postoju po bossie pojawia się warsztat, a z 60% szansą również nazwany handlarz zapisany w Kronice. MG może ręcznie otworzyć postój z handlarzem między starciami. Oferta jest ustalana raz przez serwer na podstawie przypiętego świata, poziomu i wyposażenia drużyny; zakup, sprzedaż jednej sztuki z plecaka i jednorazowe negocjacje aktualizują stan oferty oraz saldo transakcyjnie. Ceny sprzedaży wynoszą około 30% wartości bazowej.
    - Karta handlarza pokazuje stojącą postać w stylu wybranego świata. Aplikacja dostarcza lokalne portrety dla wszystkich 15 motywów i pokazuje ikonę zastępczą, jeśli plik portretu jest niedostępny.
    - W warsztacie wybiera się trzy konkretne przedmioty z plecaka; ich identyfikatory trafiają do akcji tury, a zużycie następuje po udanym rozstrzygnięciu. Kradzież nie ma przycisku: wymaga jawnego opisu zamiaru i nazwania towaru. Serwer dopuszcza jedną trudną próbę na wizytę; przyłapanie oznacza karę pieniężną do wysokości salda oraz odmowę handlu teraz i podczas następnego spotkania z handlarzem.
    - Deklaracja użycia konkretnego wyposażenia jest walidowana również dla polskich znaków, np. „łuk”; niezapisane jeszcze przedmioty zachowują domyślną ilość jednej sztuki podczas rozliczania craftingu.
12. **Narzędzia Społecznościowe i MG:**
    - Trwały czat drużyny, wzmianki, osobiste notatki oraz wspólne nadawanie nazw elementom świata.
    - Kronika Świata zawiera domyślnie zwinięty „Cel wyprawy”: główną misję, aktualny trop i kontrolowany stan postępu. Główna misja powstaje z jawnie wybranego scenariusza, a aktualny trop wyłącznie z wyzwania już pokazanego graczom, dlatego wpis nie ujawnia sekretów narratora. Kronika automatycznie porządkuje też nazwane odkrycia w działach: bossowie, miejsca, napotkani NPC, oręż i artefakty oraz ataki drużynowe. Nazwany NPC zachowuje lokację pierwszego spotkania, wybrane przez gracza usposobienie, opcjonalny cel i powiedzonko; narrator dostaje te cechy w kolejnych turach.
    - Nową technikę ataku można odkryć dopiero od tury 8, po udanym ataku i nie częściej niż raz na 8 tur. Propozycja narratora dla NPC lub ataku musi wskazać fragment rozegranej sceny; fallback offline także rozpoznaje udany manewr w walce. Technika trafia do księgi postaci, która ją odkryła; wybrana w walce daje +1 obrażenie przy trafieniu i nie łączy się ze zdolnością klasową. MG może ręcznie wywołać okazję do nazwania ataku lub NPC.
    - Potwierdzone rozpoczęcie nowego scenariusza lub reset kampanii usuwa wpisy Kroniki Świata z poprzedniej kampanii oraz oczekującą propozycję nazwania; istniejące wpisy bieżącej kampanii pozostają dostępne do czasu resetu.
    - Panel narzędzi administracyjnych jest odblokowywany osobnym `GM_PIN`; zawiera m.in. konfigurację scenariusza, reset kampanii, ponowienie i ręczne rozstrzygnięcie tury.
    - MG może awaryjnie skorygować bazowe atrybuty dowolnej postaci w zakresie `0–12`; panel pokazuje zmianę łącznej puli, wymaga potwierdzenia i synchronizuje korektę z graczami. Bonusy ekwipunku, niewydane punkty awansu i już złożone akcje nie są przeliczane.
    - Panel MG pozwala skorygować saldo bez zejścia poniżej zera oraz nadać hełm lub buty do plecaka wskazanej postaci.
    - Panel MG pozwala także wysłać postać na przerwę i przywrócić ją w trwającej kampanii. Rozpoczęcie przerwy usuwa jej ewentualną deklarację i głosowanie zastępcze z nierozstrzygniętej tury; zmiana jest blokowana podczas samego rozstrzygania.
    - MG może zapisać epilog i zakończyć kampanię po osiągnięciu celu scenariusza. Kronika oraz postacie pozostają widoczne, a składanie akcji, głosowanie zastępcze i rozstrzyganie następnych tur są zamknięte do nowego scenariusza.
    - Interfejs działa jako instalowalna PWA z service workerem, zwijanym nagłówkiem sesji i panelem akcji na telefonach oraz ekranach komputerowych do 1799 px, czytelniejszą typografią, semantycznymi modalami, obsługą klawiatury i trybem ograniczonego ruchu. Po złożeniu akcji przez wszystkich aktywnych graczy przycisk generowania kolejnej tury z AI pozostaje na górze panelu, także gdy jego treść jest zwinięta.
    - Po powrocie z uśpionej karty, zminimalizowanej przeglądarki lub zablokowanego urządzenia klient odtwarza WebSocket i pobiera aktualny stan tury; po co najmniej dwóch minutach nieobecności pokazuje krótkie powitanie wybranej postaci.
13. **Jądro Wersjonowanych Światów:**
    - Deklaratywne, niemutowalne modele Pydantic walidują identyfikatory, wersje, klasy, zdolności, startery, mapę, motyw, terminologię, kronikę, profile przeciwnika, tabele łupu, crafting, statusy i odwołania pakietu przy imporcie aplikacji.
    - Rejestr zawiera 16 wersjonowanych pakietów `d20_v1` dla 15 światów. Katalog `GET /api/worlds` pokazuje tylko najnowszą wersję każdego świata, dlatego nowe kampanie wybierają rozszerzony `archipelag_korsarzy@2` z sześcioma klasami, a `archipelag_korsarzy@1` pozostaje wyłącznie do odczytu historycznych zapisów. Narzędzia MG pozwalają wybrać pakiet dla nowego lobby przy potwierdzonym restarcie, ale nie przełączają trwającej rozgrywki w locie. Generowane kampanie zaczynają się spokojnym spotkaniem i prostym lokalnym zadaniem; poważne zagrożenie narasta dopiero w kolejnych turach.
    - Nowe światy deklaruje zwarty, kontrolowany JSON `recipe_v1`. Loader rozwija go do tego samego niemutowalnego `WorldPack` i waliduje przy starcie; nie wykonuje kodu z pakietu. Każdy ma własne klasy, księgi, mapę, łup, profil narracji i oprawę. Norki pod Zielonym Wzgórzem, Szepty Zatopionej Gwiazdy i Zagadka Gazowej Latarni nie wprowadzają automatycznie wroga w fallbacku offline, więc można prowadzić spokojną lub śledczą turę.
    - Każda kampania jest trwale przypięta do `world_pack_id` i `world_pack_version`, a postacie i zdolności zapisują stabilne `class_id` i `ability_id`. Dotychczasowe `character_class` oraz `magic_ability_id` pozostają adapterami zgodności.
    - Percepcja (`perception`, `PER`) jest piątą pełnoprawną cechą w bazie, API, kreatorze, karcie, lobby, awansie, korekcie MG, ekwipunku i interpretacji działań. Historyczne postacie otrzymują `0`, bez zmiany pozostałych cech, HP, XP ani poziomu.
    - Klasy, startery, szybkie akcje, ogólne księgi zdolności (`ability_book`), wskazówki cechy dla słownictwa świata, profile mapy, łup, rzadkości, crafting, etykiety statusów, prolog, narracja, kierunek ilustracji i fallback offline są pobierane z przypiętej wersji pakietu. `magic_book` i nazwy pól bossa pozostają adapterami dla dotychczasowej gry.
    - Frontend otrzymuje klasy, pięć etykiet cech, startery, księgi i akcje z API. Nieznany identyfikator klasy lub zdolności kończy się błędem bez podstawienia Kleryka. Zmiana świata aktywnej kampanii jest blokowana, a nieznana jawna wersja kończy się błędem.
    - Motyw pakietu używa trzynastu semantycznych kolorów oraz kontrolowanych ID fontu, tekstury, ikon i kształtu. Dodatkowy moduł `theme-art.css` nadaje 15 motywom odrębną typografię nagłówków, tekstury i obramowania. Dark Fantasy ma wąskie metalowe okucia i nity w narożnikach kart. NeoKatowice używają rzeczywistego ID motywu `neo_katowice`: prawie czarnych paneli, cienkich turkusowych konturów, neonowej poświaty nagłówków i stonowanego światła narracji. Neutralny znak w nagłówku i lobby oraz ikony akcji zastępują zamkowy/szermierczy motyw poza klasyczną oprawą. Pozostałe światy zachowują oprawy atlasu, archiwum, baśni lub komiksu. Dłuższa narracja ma czytelny krój i ograniczoną szerokość; na telefonie cienie i odstępy nagłówków są łagodniejsze. Serwer ustawia `data-theme`/`data-shape` i meta `theme-color` przed pobraniem sesji; klient pamięta ostatni motyw dla odświeżenia offline. Narzędzia MG pozwalają lokalnie podejrzeć motyw wybranego następnego świata przed resetem oraz podgląd Neon; podgląd nie zmienia kampanii i może zostać przywrócony do jej motywu. Nowe fonty są pobierane z Google Fonts przy dostępie do sieci i mają lokalne kroje zapasowe.
    - Widok NeoKatowice i lokalny podgląd Neon używają technicznych nagłówków Rajdhani, metadanych monospace oraz czytelnej narracji Space Grotesk bez ozdobnego inicjału. Aktywna sytuacja ma ramkę transmisji z numerem tury i stanem sygnału, formularz akcji przypomina konsolę, a księgi zdolności pokazują moduły z jawną dostępnością i wymaganym poziomem. Pasek zagrożenia ma zwartą oprawę HUD; cyjan oznacza akcję, fiolet moduły, bursztyn ostrzeżenia, a czerwień przeciwnika. Style pozostają w plikach aplikacji i nie zmieniają opublikowanego pakietu świata.
    - Poza Dark Fantasy ramki i tła ksiąg zdolności, slotów hełmu, butów oraz aktywnych przedmiotów korzystają z palety wybranego świata. Norki pod Zielonym Wzgórzem mają ciepłą, zaokrągloną oprawę księgi i ekwipunku oraz własną rysunkową sylwetkę mieszkańca; pozostałe nowe światy pokazują miększą neutralną sylwetkę zamiast stalowego manekina. Ilustracje SVG i reguły CSS należą do aplikacji, bez zmian w opublikowanych pakietach.
    - Pilot NeoKatowice osadza przygodę w fikcyjnym Śląsku roku 3077. Haker, Neurotechnik, Egzoochroniarz i Fixer mają własne startery, szybkie akcje i księgi hacków, neuroprotokołów, systemów bojowych lub kontaktów. Pakiet dostarcza dzielnice i ikony mapy, cybernetyczny łup, zagrożenia, teksty lobby, prolog, instrukcje narratora oraz kierunek ilustracji bez treści fantasy; fallback SVG używa kanciastego motywu.
    - Manifest PWA opisuje neutralny silnik „Przygoda”, a wersjonowane CSS/JS i service worker cache'ują także motyw. Adres manifestu i ikon jest wersjonowany; karta przeglądarki używa osobnego PNG 32×32, a ikony instalowanej PWA po zmianie adresów są ponownie wykrywane przez przeglądarkę. Schemat jest wersjonowany przez Alembic. Kontener wykonuje `alembic upgrade head` przed uruchomieniem serwera; bezpośredni start przez `uvicorn` zachowuje tymczasowy fallback dla starszych lokalnych baz.

---

## 📂 Struktura Projektu

```
├── app/
│   ├── __init__.py
│   ├── config.py              # Konfiguracja Pydantic V2 i zmienne .env
│   ├── database.py            # Asynchroniczny silnik SQLAlchemy i zgodnościowe uzupełnianie kolumn przy lokalnym starcie
│   ├── models.py              # Modele ORM sesji, udziału/przerwy postaci, tur, nazwanych elementów świata, czatu, mapy, push i głosowań
│   ├── schemas.py             # Schematy Pydantic i Structured Output JSON dla Gemini
│   ├── dice.py                # Serwerowe rzuty d20 i dedukcja atrybutów z kontrolowanymi wskazówkami pakietu
│   ├── combat.py              # Skalowanie zagrożenia i DC wyzwań, zdolności, wsparcie, agonia/śmierć i statusy
│   ├── inventory.py           # Sloty, zajęte ręce i aktywny ekwipunek
│   ├── loot.py                # Łup, przeszukiwanie i crafting według pakietu świata
│   ├── targeting.py           # Odczyt celu ataku na postać z treści deklaracji
│   ├── magic.py               # Ogólne księgi zdolności i adaptery dawnej magii
│   ├── map_generator.py       # Mapa grafowa generowana z profilu świata
│   ├── gemini_service.py      # Integracja Google GenAI (Gemini 3.8 Flash + Imagen 3)
│   ├── push_service.py        # Wysyłanie powiadomień Web Push
│   ├── generate_vapid_keys.py # Generator kluczy VAPID
│   ├── websocket_manager.py   # Menedżer WebSockets i broadcast zdarzeń
│   ├── main.py                # Składanie FastAPI, middleware, mounty i rejestracja routerów
│   ├── api/
│   │   └── routers/           # Routery UI, auth, push, admin, sesji, postaci, tur, akcji, postoju, ilustracji, czatu i katalogu światów
│   ├── services/
│   │   ├── runtime.py         # Wspólne reguły pomocnicze, inicjalizacja i lifespan
│   │   ├── session_service.py # Odczyt, konfiguracja, reset i prolog kampanii
│   │   ├── character_service.py # Postacie, gotowość, rozwój, notatki, ekwipunek i przekazywanie przedmiotów
│   │   ├── admin_service.py   # PIN MG, korekty postaci i przełączanie aktywność/przerwa
│   │   ├── room_access.py     # Skróty haseł oraz podpisany, związany z kodem dostęp do pokoju
│   │   ├── market_service.py  # Postój, oferta, ceny, handel, negocjacje i konsekwencje kradzieży
│   │   ├── turn_service.py    # Interpretacja akcji i rozstrzyganie tur
│   │   ├── chat_service.py    # Trwały czat i obsługa WebSocket
│   │   ├── image_service.py   # Generowanie ilustracji oraz limit kampanii
│   │   └── world_service.py   # Publiczny katalog i deklaratywne dane świata dla UI
│   ├── worlds/
│   │   ├── models.py          # Niemutowalny kontrakt WorldPack i typy składowe
│   │   ├── registry.py        # Walidowany rejestr oraz kontrolowany fallback
│   │   ├── recipes.py         # Kontrolowana deklaracja recipe_v1 -> pełny WorldPack
│   │   └── packs/             # 2 pełne pakiety v1 oraz 13 deklaratywnych recipe_v1
│   ├── static/
│   │   ├── css/style.css      # Punkt wejścia kaskady CSS
│   │   ├── css/modules/       # Tokeny, baza, komponenty, ekwipunek, postój, mapa, kronika, komunikaty, responsywność i motywy
│   │   ├── js/theme-bootstrap.js # Ustawienie motywu i kontrolowanego kształtu przed CSS
│   │   ├── js/app.js          # Składanie głównego komponentu Alpine `rpgGame`
│   │   ├── js/modules/        # Stan, PWA, auth/MG, sesja/postać, mapa/historia, realtime/czat, akcje, ekwipunek i postój
│   │   ├── img/merchants/     # Lokalne portrety handlarzy, po jednym PNG na identyfikator motywu
│   │   ├── manifest.json      # Neutralny manifest instalowalnej PWA
│   │   ├── sw.js              # Service worker, cache modułów i obsługa Web Push
│   │   └── icons/             # Wektorowe logo d20 i komplet ikon PWA (192, 512, maskable, apple-touch, favicon)
│   └── templates/
│       ├── index.html         # Szkielet dokumentu i kolejność zasobów
│       └── partials/          # Brama, lobby, stół, panele funkcjonalne i osobne modale Jinja
├── tests/
│   ├── conftest.py            # Wspólna izolowana kampania Dark Fantasy dla testów integracyjnych
│   ├── test_combat.py         # Testy walki, gaszenia/osłabiania efektów i zapisu statusów
│   ├── test_encounter_difficulty.py # HP i odpowiedzi wroga oraz poziomy DC przeszkód
│   ├── test_current_world_contract.py # Kontrakt regresyjny bieżącego świata, tras, klas, ksiąg, mapy i UI
│   ├── test_dice.py           # Testy rzutów i istotnych dla deklaracji modyfikatorów ekwipunku
│   ├── test_frontend_module_contract.py # Partiale, zasoby, kaskada CSS, kolejność skryptów i cache PWA
│   ├── test_inventory_transfer.py # Sloty hełmu/butów oraz przekaz stosu w izolowanej bazie
│   ├── test_full_resolution.py # Test pełnego cyklu tury i awansu
│   ├── test_lobby_flow.py     # Testy lobby, gotowości i uprawnień MG
│   ├── test_loot.py           # Testy łupu oraz craftingu
│   ├── test_market.py         # Handel i konsekwencje kradzieży w izolowanej bazie
│   ├── test_multi_room_access.py # Niezależne hasła, izolacja pokoi i zachowanie starej kampanii
│   ├── test_character_breaks.py # Przerwa postaci, zachowanie postępu i powrót do gry
│   ├── test_character_targets.py # Atak na postać, samoleczenie i ochronne wsparcie bez leczenia
│   ├── test_turn_flow.py      # Testy API, autoryzacji i akcji
│   ├── test_stage6_world_content.py # Próbny pakiet: klasy, księga, mapa, przeciwnik i walidacja mechanik
│   ├── test_stage7_theme_selection.py # Kontrolowane motywy i wybór świata tylko przy restarcie
│   ├── test_stage8_neokatowice_pilot.py # Klasy, księgi, startery, mapa, motyw i przypięta wersja pilota
│   ├── test_stage9_world_recipes.py # Kontrakt 13 nowych światów, map, ksiąg i walidacji przepisów
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
├── alembic/                   # Migracje 0001–0009, w tym wiele pokoi, scenariusz sesji i formę narracji
├── alembic.ini                # Konfiguracja migracji korzystająca z DATABASE_URL
├── Dockerfile                 # Zoptymalizowany obraz produkcyjny Python 3.12-slim
├── docker-compose.yml         # Konfiguracja uruchomieniowa kontenera
├── requirements.txt           # Zależności Python, w tym Alembic i dane stref czasowych
├── .env.example               # Wzór pliku środowiskowego
└── README.md                  # Dokumentacja techniczna
```

Etapy 6–9 i skalowanie trudności nie dodają zmiennych `.env` ani osobnego buildu frontendu. Domyślny
pozostaje `dark_fantasy@1`; pozostałe 14 światów wybiera się dla nowej kampanii,
a lokalne podglądy motywów nie zmieniają świata zapisanego w kampanii. Weryfikacja resetu,
tworzenia postaci i tur musi korzystać z osobnej bazy przez `DATABASE_URL` lub
z kopii zapisu, nie z aktywnej bazy. Ręczna checklista odbioru etapu 9, z
osobną ścieżką dla każdego świata i jego motywu, jest w `docs/WORLD_PACK_ROADMAP.md`.

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

# Hasło startowe zachowanej kampanii `kampania-1`; nowe pokoje dostają własne hasła w UI
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

Po uruchomieniu dotychczasowa gra jest dostępna pod kodem `kampania-1` i starym
`ROOM_PASSWORD`. Aby uruchomić drugą kampanię, na bramie wybierz
`UTWÓRZ NOWY STÓŁ JAKO MG`, podaj unikalny kod (małe litery, cyfry i myślniki),
hasło graczy oraz `GM_PIN`, a także wybierz świat, scenariusz i ton opowieści.
Nowy pokój startuje jako niezależne lobby z już zapisanym wyborem. Przeglądarka przechowuje kod
ostatniego pokoju, ale nie zapisuje hasła graczy w `localStorage`.
Jedna przeglądarka utrzymuje naraz jedno ciasteczko pokoju; przełączenie kodu wymaga
ponownego logowania, ale nie wpływa na stan żadnej kampanii. Różne grupy i urządzenia
mogą równolegle korzystać z różnych stołów na tym samym serwerze.

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
Migracja `0002_encounter_difficulty` dodaje poziom trudności do tur; istniejące tury zachowują zwykły poziom DC 12. Migracja `0003_inventory_wallet` dodaje saldo `coins` i nadaje historycznym postaciom `0`, bez zmiany ich ekwipunku. Migracja `0004_lore_discoveries` dodaje wybierane ataki postaci, cechy NPC i kontekst oczekującej propozycji nazwania bez usuwania dotychczasowej Kroniki. Migracja `0005_campaign_endings_cursed_items` dodaje zapis epilogu i karę przeklętych przedmiotów, zachowując dotychczasowy ekwipunek. Migracja `0006_market_post` dodaje stan wizyty handlarza i identyfikatory składników craftingu do akcji, bez zmiany starych tur. Migracja `0007_character_breaks` dodaje kontrolowany status udziału i numer rozpoczęcia przerwy; wszystkie historyczne postacie pozostają aktywne z niezmienionym poziomem i postępem. Migracja `0008_multi_room_access` dodaje nullable skrót hasła pokoju bez resetowania sesji, postaci ani tur. Migracja `0009_scenario_narrative_form` zapisuje scenariusz sesji i kontrolowaną formę narracji postaci; historyczne kampanie zachowują przebieg, a ich postacie otrzymują formę neutralną. Migracja `0010_campaign_goal` dodaje główną misję, aktualny trop i kontrolowany stan celu bez zmiany historii kampanii. Bezpośredni start przez `uvicorn` uzupełnia wymagane kolumny w starszych lokalnych bazach bez historii Alembic; późniejsze `alembic upgrade head` zapisuje formalną wersję schematu. Nie są potrzebne nowe zmienne `.env`. Przed migracją istniejącej kampanii wykonaj kopię bazy SQLite. `SECRET_KEY` podpisuje ciasteczko związane z kodem pokoju i używane przez chronione operacje HTTP oraz WebSocket.

Własny portret handlarza można dostarczyć jako PNG z przezroczystym tłem, zastępując odpowiedni plik w `app/static/img/merchants/`. Nazwa pliku to `theme_id` świata, np. `archipelag_korsarzy.png` lub `neo_katowice.png` (identyfikator motywu NeoKatowic różni się od ID pakietu). Interfejs wybiera portret według przypiętego świata, bez zmian w JSON pakietów i bez dodatkowej zmiennej `.env`. Po podmianie zasobu trzeba odświeżyć wersję adresu portretu w `app/static/js/modules/market.js` oraz wersję modułu i cache PWA, aby przeglądarki pobrały nowy plik.

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

Testy przepływu lobby, akcji, pełnego rozstrzygnięcia i czatu WebSocket korzystają
ze wspólnej fixture z tymczasową bazą SQLite oraz jawnie przypiętym
`dark_fantasy@1`. Nie odczytują ani nie modyfikują lokalnego `ttrpg_game.db`.

Zakres testów:
- `tests/test_current_world_contract.py`:
  - Chroni publiczną tabelę tras HTTP i WebSocket oraz nazwy zdarzeń czasu rzeczywistego przed przypadkową zmianą podczas modularizacji.
  - Rozwija routery dołączane leniwie przez FastAPI, dzięki czemu porównuje faktyczne endpointy z aktualną fixture również po podziale backendu.
  - Utrwala obecne klasy, startowy ekwipunek, księgi Czarodzieja i Kleryka, profil mapy Dark Fantasy, kształt odpowiedzi sesji (w tym poznane ataki, saldo i status przerwy), endpoint udziału MG, zdarzenia WebSocket wraz z `MARKET_UPDATED`, trasy oraz kluczowe elementy renderowanego UI.
  - Korzysta z fixture `tests/fixtures/dark_fantasy_v1_contract.json`, która jest punktem odniesienia dla przyszłego pakietu `dark_fantasy@1`.
  - Sprawdza kluczowe markery UI już po złożeniu wszystkich partiali Jinja.
  - Lokalizuje finał mapy przez stabilne `final_node_id`, niezależnie od kolejności dopisanych odnóg.
- `tests/test_combat.py`:
  - Rozpoznawanie dominującej intencji, w tym gaszenia płomieni oraz zdań zawierających mylące przysłowia, skalowanie bossów, obrażenia, usuwanie efektów przed ich tyknięciem i walidacja używanego ekwipunku z polskimi znakami.
- `tests/test_encounter_difficulty.py`:
  - Zależność HP od szansy trafienia, pancerza i wyposażenia, osobne cele odpowiedzi wroga, utrwalenie maksymalnej liczby ataków, dynamiczny limit aktualnej drużyny, rozbicie redukcji obrony oraz serwerowe DC trzech poziomów wyzwania.
- `tests/test_dice.py`:
  - Dedukcja atrybutów z treści deklaracji gracza (Siła, Zręczność, Rozum, Charyzma i Percepcja), z ignorowaniem słabych ozdobników narracyjnych przy fizycznym ataku oraz rozdzieleniem obserwacji od analizy.
  - Obliczanie modyfikatorów z aktywnego ekwipunku istotnego dla deklaracji, bez sumowania dwóch broni do jednego rzutu i z pierwszeństwem jawnie użytego oręża.
  - Wyznaczanie progów sukcesu i kontrolowany testowo rzut k20.
- `tests/test_full_resolution.py`:
  - Pełny cykl rozstrzygnięcia tury, zapis narracji, mechaniczna aktualizacja HP, deterministyczne XP według poziomu wyniku i awans w izolowanej kampanii Dark Fantasy.
- `tests/test_frontend_module_contract.py`:
  - Renderowanie wszystkich partiali Jinja i istnienie wskazanych zasobów lokalnych.
  - Kolejność modułów CSS i skryptów Alpine oraz kompletność wersjonowanego cache PWA.
- `tests/test_inventory_transfer.py`:
  - Niezależne sloty hełmu i butów, dostęp do pokoju, częściowy przekaz stosu oraz odrzucenie obcej kampanii, założonego przedmiotu i przekazu podczas rozstrzygania tury.
- `tests/test_lobby_flow.py`:
  - Konfiguracja lobby z jawnie wybranym `dark_fantasy@1`, gotowość graczy oraz kontrola dostępu do narzędzi MG w izolowanej bazie.
- `tests/test_loot.py`:
  - Przyznawanie łupu i środków, jednorazowe przeszukiwanie lokacji, pustą lokację po sukcesie, usunięcie nieprzyznanego artefaktu z narracji, premię i karę założonego przeklętego przedmiotu oraz zasady craftingu.
- `tests/test_market.py`:
  - Zakup i sprzedaż z aktualizacją salda, stanu oferty i plecaka oraz kara i odmowa handlu po nieudanej kradzieży w izolowanej bazie.
- `tests/test_character_breaks.py`:
  - Odwracalna przerwa przez endpoint MG, zachowanie poziomu/XP/HP/salda, usunięcie deklaracji i głosowania zastępczego z otwartej tury oraz awaryjny odwrót całkowicie obezwładnionej aktywnej drużyny w izolowanej bazie.
- `tests/test_character_targets.py`:
  - Odczyt celu ataku na postać z opisu, obrażenia improwizowanym kamieniem, leczenie własnej postaci oraz ochronne wsparcie bez sztucznego odnawiania HP.
- `tests/test_multi_room_access.py`:
  - Niezależne hasła i stan równoległych pokoi, przypięcie świata/scenariusza przy tworzeniu oraz zachowanie historycznej kampanii i neutralnej formy narracji.
- `tests/test_turn_flow.py`:
  - Pobieranie strony głównej i weryfikacja hasła do pokoju.
  - Tworzenie postaci i przydzielanie startowego ekwipunku.
  - Składanie akcji tury i sprawdzanie stanu gotowości drużyny.
  - Izolowana kampania Dark Fantasy i ponowne użycie tury 1 po wyczyszczeniu znaczników wcześniejszego rozstrzygnięcia.
- `tests/test_websocket_chat.py`:
  - Wymiana wiadomości czatu przez WebSocket prawidłowej postaci klasy Kleryk w izolowanej bazie, z obsługą opcjonalnego początkowego snapshotu `CHAT_HISTORY`.
- `tests/test_world_registry.py`:
  - Ładowanie wszystkich 16 wersji pakietów dla 15 światów z domyślnym `dark_fantasy@1`, publikowanie tylko najnowszej wersji świata w katalogu, pięć kanonicznych cech rulesetu i zachowanie obecnych klas, starterów, ksiąg, mapy oraz narracji.
  - Odrzucanie nieznanej jawnej wersji i błędnych referencji oraz kontrakt odpowiedzi `GET /api/worlds`.
- `tests/test_stage8_neokatowice_pilot.py`:
  - Zawartość fikcyjnego Śląska, cztery księgi, startery potrzebne do zdolności, ikony mapy, kontrolowany kształt i przypięcie wersji świata.
- `tests/test_stage9_world_recipes.py`:
  - Komplet 13 nowych pakietów, ekspansja przepisu do `WorldPack`, księgi, motywy, mapa, spokojne fallbacki i odrzucanie niedozwolonych danych.
- `tests/test_world_migration.py`:
  - Uruchomienie Alembic na historycznej bazie i kontrola addytywnego backfillu bez zmiany postępu postaci; obecny head to `0009_scenario_narrative_form`, który dodaje scenariusz sesji i neutralną formę narracji historycznych postaci.

---

## 🧭 Roadmapa silnika wielu światów

Rozwój kampanii cyberpunkowych, pirackich, pustynnych, historyczno-okultystycznych, słowiańskich, wikińskich, westernowych, space-grimdark, infernalnych, pastoralnych, kosmiczno-horrorowych, detektywistycznych i humorystycznych jest podzielony na niezależnie odbierane etapy. Pełny plan i nazwy wszystkich pakietów znajdują się w [`docs/WORLD_PACK_ROADMAP.md`](docs/WORLD_PACK_ROADMAP.md), decyzja architektoniczna w [`docs/adr/0001-versioned-world-packs.md`](docs/adr/0001-versioned-world-packs.md), a granica między silnikiem i światem w [`docs/WORLD_DEPENDENCY_INVENTORY.md`](docs/WORLD_DEPENDENCY_INVENTORY.md).

Etapy 1–8 są zakończone; etap 9 jest zaimplementowany i czeka na osobny ręczny
odbiór 13 nowych światów. Kontrakt `dark_fantasy_v1` utrwala obecną rozgrywkę,
backend i frontend są podzielone na moduły, a walidowany rejestr ładuje 16
wersji pakietów dla 15 światów, publikując w katalogu tylko najnowszą wersję
każdego świata. Kampania zapisuje ID i wersję pakietu, klasy oraz zdolności mają
stabilne identyfikatory, a Alembic migruje historyczne dane. Percepcja działa
w całej ścieżce gry.

Ruleset używa pięciu kanonicznych atrybutów: Siły, Zręczności, Intelektu, Charyzmy i Percepcji. Migracja nadaje istniejącym postaciom Percepcję `0` bez zmiany pozostałych cech, HP, XP i poziomu. Roadmapa zawiera przy każdym etapie osobną checklistę ręcznego odbioru po lokalnym zbudowaniu aplikacji oraz instrukcję użycia izolowanej bazy `manual_review.db`.

---

## 📝 Utrzymanie Dokumentacji

Każda zakończona zmiana w projekcie musi obejmować aktualizację `README.md` oraz `AGENTS.md` o informacje opisujące nowy lub zmieniony stan aplikacji. Dotyczy to również zmian funkcjonalnych, konfiguracji, struktury projektu, komend i procesu pracy. Na końcu podsumowania każdej zmiany należy zaproponować krótką, opisową nazwę commitu w języku angielskim.

Automatyczny agent nie uruchamia ani nie proponuje uruchamiania testów bez wyraźnej prośby użytkownika w bieżącej rozmowie. Polecenia wdrożenia, naprawy, weryfikacji lub zakończenia zmiany nie stanowią takiej zgody. Po każdej zakończonej zmianie agent podaje propozycję angielskiej nazwy commitu, ale nie tworzy commita bez osobnego polecenia.

---

## 📜 Licencja & Zespół
Projekt stworzony jako silnik RPG nowej generacji łączący tradycyjne reguły stołowych gier fabularnych z mocą modeli Google Gemini & Imagen.
