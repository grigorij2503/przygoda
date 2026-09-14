# ADR 0001: Wersjonowane, deklaratywne pakiety świata

- Status: zaakceptowana decyzja kierunkowa
- Data: 2026-09-14
- Zakres wdrożenia: etapy 4-9 roadmapy światów

## Kontekst

Obecna aplikacja implementuje jedną kampanię Dark Fantasy. Nazwy klas, księgi
zdolności, startery, łup, słowniki intencji, mapa, instrukcje Gemini i oprawa są
rozproszone między backendem, frontendem i szablonem. Bez ustanowienia granicy
domenowej każdy kolejny świat powodowałby mnożenie warunków i ryzyko regresji
istniejącej rozgrywki.

## Decyzja

Wprowadzimy jeden silnik mechaniczny oraz rejestr wersjonowanych `WorldPack`.
Pakiety będą deklaratywnymi plikami repozytorium walidowanymi przez Pydantic przy
starcie aplikacji. Kampania będzie przypięta do dokładnego `world_pack_id` i
`world_pack_version`.

Pakiet definiuje:

- słownictwo i treść świata;
- klasy, startery, szybkie akcje i księgi zdolności;
- katalog zdolności odwołujący się do kontrolowanych efektów silnika;
- profile łupu, przedmiotów, przeciwników, mapy, kroniki i narratora;
- bezpieczny identyfikator motywu i statycznych zasobów.

Pakiet nie definiuje:

- kodu Python lub JavaScript;
- dowolnego HTML albo CSS;
- zapytań SQL;
- niezaufanych zewnętrznych zasobów;
- podstawowego cyklu tury, trwałości danych ani synchronizacji.

Pierwszy pakiet `dark_fantasy@1` ma odwzorować istniejącą rozgrywkę bez zmian.
Ogólne nazwy `ability_book` i `ability_id` zastąpią domenowe `magic_book` oraz
`magic_ability_id`, ale stare pola pozostaną czasowo jako adaptery.

## Wersjonowanie

- wersja jest częścią tożsamości pakietu;
- opublikowana wersja jest niemutowalna;
- poprawka zmieniająca mechanikę, treść zapisaną w kampanii albo identyfikatory
  tworzy nową wersję;
- migracja kampanii między wersjami wymaga jawnej procedury;
- brak przypiętej wersji w historycznej kampanii jest migrowany do
  `dark_fantasy@1`;
- nieznany pakiet lub wersja powoduje czytelny błąd administracyjny.

## Ruleset i zdolności

Pierwsze światy używają wspólnego `d20_v1`. Zdolność zawiera stabilne dane:

- `intent`;
- `tested_stat`;
- `targeting`;
- `mechanic_key`;
- zwalidowane `mechanic_params`.

Silnik posiada zamknięty rejestr implementacji `mechanic_key`. Dzięki temu
Wskrzeszenie, leczenie, hack, skan lub zakłócenie nie wymagają porównywania nazw
klasy i ID świata w routerach.

## Motywy

Pakiet wskazuje `theme_id`. Motyw jest zdefiniowany w kodzie statycznym za pomocą
semantycznych tokenów CSS oraz zatwierdzonych fontów, ikon i tekstur. Pakiet nie
może przekazać dowolnego CSS ani URL. Manifest PWA pozostaje neutralną tożsamością
silnika, a bieżąca strona może aktualizować własny `theme-color`.

## Konsekwencje

Pozytywne:

- nowe światy są głównie pracą nad zawartością;
- historyczne kampanie są odporne na zmianę domyślnego świata;
- jeden kontrakt API i Gemini obsługuje wszystkie kampanie;
- walidacja przy starcie wykrywa uszkodzony pakiet przed rozgrywką;
- ograniczamy ryzyko wstrzyknięcia kodu i niekontrolowanego CSS.

Koszty:

- początkowa migracja wszystkich hardkodów jest rozległa;
- potrzebna jest warstwa kompatybilności dla starych danych i nazw API;
- różne mechaniki światów wymagają projektowania ogólnych efektów, a nie
  kopiowania modułów;
- pakiety muszą być utrzymywane jako niemutowalne wersje.

## Odrzucone alternatywy

### Osobna aplikacja dla każdego świata

Prowadzi do duplikacji mechaniki, poprawek bezpieczeństwa, PWA i synchronizacji.

### Warunki zależne od świata w istniejących modułach

Szybkie na początku, lecz skaluje liczbę kombinacji i utrudnia ochronę obecnej
kampanii przed regresją.

### Pakiety jako kod wykonywalny

Pozwalają na dowolność, ale zwiększają ryzyko bezpieczeństwa, utrudniają walidację
i nie dają stabilnego kontraktu danych.

### Natychmiastowa migracja do Reacta

Nie rozwiązuje sprzężenia domenowego backendu, promptów, mapy i danych. Najpierw
modularizujemy obecną warstwę Alpine/Jinja.

