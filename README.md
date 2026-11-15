# Poranna Pigułka Przedsiębiorcy (Brzesko)

Autonomiczny, całkowicie darmowy (`0 zł` kosztów abonamentowych) system generujący codziennie rano o godz. **7:35–8:00** czasu polskiego praktyczny przegląd dla polskiego przedsiębiorcy (JDG / MŚP), publikowany jako lekka aplikacja webowa **PWA na iPhone’a** oraz dostarczany w formie krótkiego powiadomienia na telefon.

> [!NOTE]
> Pierwotna dokumentacja projektu **AI Video Studio** została zachowana w [docs/README-VIDEO-STUDIO.md](docs/README-VIDEO-STUDIO.md), a wszystkie pliki tamtego modułu (`src/`, `tools/ffmpeg/`, `tools/piper/`, `models/`, `storage/`, `AGENTS.md`) pozostały nienaruszone.

---

## 1. Decyzje architektoniczne podjęte na starcie

Zgodnie z wymaganiami projektowymi przed implementacją podjęto i zweryfikowano następujące decyzje:

1. **Język skryptu: Python 3.11 (czysta biblioteka standardowa)**
   - Cały backend pipeline’u oparto wyłącznie na standardowej bibliotece Pythona 3.11 (`urllib`, `xml.etree.ElementTree`, `html.parser`, `json`, `re`, `datetime`).
   - Brak zewnętrznych zależności `pip` w środowisku CI sprawia, że zadanie w GitHub Actions uruchamia się w kilka sekund, jest w pełni przewidywalne i odporne na błędy instalacji paczek.
2. **Technologia aplikacji mobilnej: PWA (HTML / CSS / ES6 JS + Service Worker) zamiast React Native / Expo**
   - **Zero kosztów i brak App Store:** natywna publikacja na iOS wymaga płatnego konta Apple Developer Program (\$99/rok) oraz cyklicznych przeglądów w App Store. PWA dodana w Safari na iPhonie opcją **„Dodaj do ekranu początkowego”** zachowuje się jak natywna aplikacja (ikona, tryb pełnoekranowy `standalone`, ciemny motyw, `safe-area`, działanie offline przez Service Worker i IndexedDB).
   - **Natywne udostępnianie iOS:** wykorzystuje systemowe Web Share API (`navigator.share`) z kopią zapasową do schowka.
3. **Hosting aplikacji: GitHub Pages (z zastrzeżeniem prywatności)**
   - GitHub Pages jest całkowicie darmowy dla repozytoriów publicznych i bezobsługowo wdrażany z poziomu GitHub Actions (`actions/deploy-pages`).
   - **Ważne zastrzeżenie:** w darmowym planie GitHuba repozytorium i wygenerowane pliki `data/RRRR-MM-DD.json` są **publiczne**. Dlatego plik `config/company_profile.json` zawiera wyłącznie anonimową charakterystykę firmy (brak NIP, REGON, nazwy i adresu).
   - **Darmowa alternatywa prywatna (gdy wymagana jest kontrola dostępu):** można przenieść folder `/app` na **Cloudflare Pages** (darmowy plan) z darmową bramką **Cloudflare Zero Trust Access** (do 50 użytkowników, logowanie jednorazowym kodem na e-mail) i zamknąć repozytorium jako prywatne (w granicach darmowych minut GitHub Actions: 2000 min/mies.).
4. **Model AI: Google Gemini API (darmowy plan) + 1-linijkowa konfiguracja**
   - Wykorzystano Google Gemini REST API w trybie JSON (`responseMimeType: "application/json"`).
   - Limity darmowego planu (RPM/TPM/RPD oraz dostępność konkretnych wersji modeli) zmieniają się po stronie Google ([dokumentacja limitów Gemini API](https://ai.google.dev/gemini-api/docs/rate-limits)), dlatego nazwa modelu jest wydzielona w jednej linii w `config/sources.json` (`"ai_model": "gemini-3.5-flash-lite"`) wraz z listą zapasową `ai_fallback_models` i opóźnieniem między zapytaniami (`"ai_delay_seconds": 2.0`).
   - Dzienne zużycie przy `max_items_per_section: 5` mieści się wygodnie w kilkunastu zapytaniach dziennie.
5. **Powiadomienia na iPhone’a: Telegram Bot / ntfy.sh zamiast Web Push (VAPID)**
   - Wariant Web Push w PWA (iOS 16.4+) wymaga trwałego serwera lub bazy KV przechowującej prywatne endpointy subskrypcji i podpisy VAPID. W architekturze bez własnego serwera (tylko GitHub Actions + statyczne GitHub Pages) **bot Telegram** (oraz opcjonalnie **ntfy.sh**) zapewnia natychmiastowe, bezpłatne powiadomienia push na iPhone’a oraz natywne alerty o awariach bez konieczności utrzymywania bazy subskrybentów.

---

## 2. Architektura i przepływ danych

```text
GitHub Actions (cron 05:35 & 06:35 UTC + strażnik strefy CET/CEST)
  ├──► Pobieranie źródeł (pełne teksty i API, bez AI):
  │      ├── Pogoda Brzesko 32-800 (Open-Meteo API)
  │      ├── Kursy walut i stopa referencyjna (NBP API / XML)
  │      ├── Terminy podatkowe i ZUS (programowo + przesunięcie świąt)
  │      ├── Interpretacje podatkowe KIS (publiczne API EUREKA MF — pełna treść)
  │      ├── Legislacja RP (Sejm API druki/procesy + ELI Dziennik Ustaw)
  │      ├── ZUS i Finanse (zus.pl, gov.pl/finanse, RSS Interia Podatki)
  │      └── Gospodarka i Świat (RSS + ekstrakcja pełnych artykułów)
  ├──► Deduplikacja i wybór (data/seen_ids.json + jawna punktacja priorytetów)
  ├──► AI Etap A: Ekstrakcja wyłącznie surowych faktów (prompts/stage_a_extract_facts.txt)
  ├──► AI Etap B: Redakcja 3-poziomowa PL (prompts/stage_b_write_synthesis.txt)
  ├──► Walidacja schematem JSON (config/pill_schema.json) + kontrola liczb/dat/sygnatur
  ├──► Zapis data/RRRR-MM-DD.json, data/index.json oraz synchronizacja do app/data/
  ├──► Wdrożenie statycznego PWA (/app) na GitHub Pages
  └──► Powiadomienie na Telegram / ntfy.sh (lub alert awaryjny w razie błędu)
```

Kluczowa zasada: **dane są całkowicie oddzielone od warstwy prezentacji**. Backend produkuje ustrukturyzowany plik `data/RRRR-MM-DD.json` (z 3 poziomami: `headline`, `summary`, `details`), a statyczna aplikacja PWA w `/app` wyłącznie go odczytuje i renderuje.

---

## 3. Struktura katalogów projektu

```text
/config
  ├── company_profile.json          # Anonimowy profil JDG do oceny istotności (relevance)
  ├── sources.json                  # Konfiguracja modelu AI, limitów i wszystkich źródeł
  ├── tax_deadlines.json            # Cykliczne i roczne terminy podatkowe / ZUS
  └── pill_schema.json              # JSON Schema wyjściowej pigułki
/prompts
  ├── stage_a_extract_facts.txt     # Prompt v1.0 – ekstrakcja surowych faktów
  └── stage_b_write_synthesis.txt   # Prompt v1.0 – redakcja trzypoziomowa z faktów
/scripts
  ├── main.py                       # Orkiestrator pipeline'u (--dry-run, --no-notify, --force-time)
  ├── ai_processor.py               # Dwuetapowy klient Gemini API + retry/backoff + klauzula KIS
  ├── deadlines_calc.py             # Kalkulator terminów z przesunięciem na dni robocze + eksport .ics
  ├── dedup.py                      # Historia ID (seen_ids.json) i punktacja ważności
  ├── notifier.py                   # Powiadomienia Telegram / ntfy.sh + alerty awaryjne (--failure)
  ├── validator.py                  # Walidator struktury JSON i spójności liczb/dat/sygnatur ze źródłem
  └── sources/                      # Niezależne moduły źródeł (każdy uruchamialny osobno):
      ├── http_utils.py, rss_utils.py
      ├── weather.py, markets.py, eureka_kis.py, legislation.py, zus_gov.py, economy_world.py
/data                               # Wygenerowane pigułki dzienne RRRR-MM-DD.json, index.json, seen_ids.json
/app                                # Aplikacja PWA (tryb ciemny, iOS, offline SW, IndexedDB, Web Share)
/tests                              # Testy jednostkowe (unittest)
/.github/workflows/morning_briefing.yml
```

---

## 4. Konfiguracja na GitHubie (jednorazowa po stronie repozytorium)

1. **GitHub Secrets (`Settings -> Secrets and variables -> Actions`):**
   - `GEMINI_API_KEY` – klucz API Google Gemini (darmowy plan z Google AI Studio).
   - `TELEGRAM_BOT_TOKEN` – token bota z `@BotFather`.
   - `TELEGRAM_CHAT_ID` – ID Twojego czatu z botem.
   - `NTFY_TOPIC` *(opcjonalnie)* – nazwa tematu w ntfy.sh, jeśli chcesz używać także ntfy.
   > **Nigdy nie wpisuj kluczy w kodzie ani w `app/`!** Lokalnie używaj wyłącznie pliku `.env` (dodanego do `.gitignore`).
2. **Włączenie GitHub Pages (`Settings -> Pages`):**
   - W sekcji **Build and deployment -> Source** wybierz **`GitHub Actions`** (zamiast *Deploy from a branch*).
3. **Instalacja PWA na iPhonie:**
   - Otwórz link z powiadomienia w **Safari** na iPhonie, stuknij ikonę **Udostępnij** i wybierz **„Dodaj do ekranu początkowego”**.

---

## 5. Jak utrzymywać i modyfikować system

- **Zmiana modelu AI (jedna linia):** w [config/sources.json](config/sources.json) zmień pole `"ai_model": "gemini-3.5-flash-lite"` na inny dostępny model Gemini.
- **Dodanie nowego źródła RSS:** w [config/sources.json](config/sources.json) dopisz wpis `{"id": "...", "name": "...", "type": "rss", "url": "..."}` w sekcji `"zus_gov.sources"` lub `"economy_world.sources"`. Moduł automatycznie pobierze kanał i pełne treści artykułów.
- **Zmiana godziny powiadomień:** w [.github/workflows/morning_briefing.yml](.github/workflows/morning_briefing.yml) zaktualizuj dwa wpisy `cron` (dla czasu letniego UTC+2 i zimowego UTC+1) oraz dopasuj przedział godzin w funkcji `check_schedule_guard` w [scripts/main.py](scripts/main.py).
- **Edycja promptów i profilu firmy:** edytuj pliki w `/prompts` oraz [config/company_profile.json](config/company_profile.json) bez ruszania kodu Pythona.
- **Obsługa i wymiana kluczy:** jeśli klucz Gemini lub Telegrama wygaśnie albo wyczerpie limit, workflow wyśle automatyczne powiadomienie o awarii (`scripts/notifier.py --failure`); wystarczy wkleić nowy sekret w `GitHub Secrets`.

---

## 6. Uruchamianie lokalne i testy (Windows 11 / Linux)

```powershell
# Uruchomienie testów jednostkowych (offline)
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Bezpieczny test pełnego pipeline'u (bez zapisu do /data i bez powiadomień)
.\.venv\Scripts\python.exe scripts/main.py --dry-run --force-time --max-per-section 2

# Wygenerowanie pigułki lokalnie bez wysyłania powiadomienia
.\.venv\Scripts\python.exe scripts/main.py --no-notify --force-time

# Test pojedynczego modułu źródła w izolacji
.\.venv\Scripts\python.exe scripts/sources/eureka_kis.py
.\.venv\Scripts\python.exe scripts/deadlines_calc.py
```

---

## 7. Zastrzeżenie prawne

> Treści prezentowane w aplikacji oraz w udostępnianych notatkach mają charakter **wyłącznie informacyjny i edukacyjny**. Nie stanowią porady prawnej, podatkowej ani księgowej. Indywidualne interpretacje podatkowe wiążą formalnie wyłącznie wnioskodawcę w jego indywidualnej sprawie.
