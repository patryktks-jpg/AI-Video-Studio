# AI Video Studio – Plan Realizacji Projektu (PROJECT-PLAN.md)

Lokalna, bezpłatna fabryka filmów AI zoptymalizowana pod Windows 11 oraz kartę NVIDIA RTX 3060 Laptop (6 GB VRAM).

---

## 1. Analiza Środowiska i Ograniczeń Sprzętowych

| Komponent | Specyfikacja | Wpływ na Architekturę |
| :--- | :--- | :--- |
| **GPU** | NVIDIA RTX 3060 Laptop (6 GB VRAM) | **Główne wąskie gardło**. Wymaga sekwencyjnego uruchamiania modeli (nie wolno trzymać ComfyUI i Ollama jednocześnie w VRAM pod obciążeniem). Dobór modeli SD 1.5 lub zoptymalizowanych SDXL (Lightning/Turbo) z flagą `--medvram`. |
| **RAM** | 32 GB DDR4 | Duży atut. Pozwala na buforowanie danych, płynną pracę montażu FFmpeg oraz ewentualny częściowy offload wag modeli AI z GPU do pamięci systemowej w razie potrzeby. |
| **CPU** | Intel Core i5-11400H (6 rdzeni / 12 wątków) | Bardzo dobra wydajność wielowątkowa. Idealny do syntezy mowy (Piper TTS działa błyskawicznie na CPU bez obciążania GPU) oraz obróbki audio/wideo. |
| **Dysk** | 512 GB SSD | Ograniczona przestrzeń na checkpointy AI. Konieczna dyscyplina w doborze wag (GGUF, FP8, LoRA) oraz czyszczenie plików tymczasowych (`storage/intermediates`). |
| **OS** | Windows 11 | Środowisko bazowe. Wszystkie ścieżki i skrypty będą dostosowane do specyfiki Windows (PowerShell/CMD, obsługa ścieżek bez konfliktów separatorów). |

---

## 2. Architektura Przepływu Danych (Pipeline)

```
[ Temat / Pomysł ]
        │
        ▼ (Krok 1: CPU / GPU sekwencyjnie)
[ Ollama: LLM 7B/8B ] ──► Generuje: Scenariusz, Tekst Lektora, Prompty Grafik
        │
        ▼ (Zwolnienie VRAM LLM)
        │
        ▼ (Krok 2: Czyste CPU - 0% VRAM)
[ Piper TTS ] ──────────► Generuje: Pliki audio lektora (WAV) + Czas trwania
        │
        ▼ (Krok 3: CPU)
[ Parser Napisów ] ─────► Generuje: Napisy zsynchronizowane (SRT / ASS)
        │
        ▼ (Krok 4: GPU - pełne 6 GB dla grafiki)
[ ComfyUI API ] ────────► Generuje: Kadry w wysokiej rozdzielczości (PNG)
        │
        ▼ (Krok 5: CPU + NVENC)
[ FFmpeg Engine ] ──────► Łączenie kadrów, efekt Ken Burns (zoom/pan),
                          mikser audio (lektor + muzyka tła), render napisów
        │
        ▼
[ Gotowy film MP4 ]
```

---

## 3. Kolejność Wdrażania Narzędzi (Krok po Kroku)

Aby projekt był stabilny i możliwy do utrzymania przez początkującego programistę, narzędzia wdrażamy od najprostszych, niezawodnych komponentów po zaawansowane modele generatywne:

### Krok 1: Środowisko Bazowe (Python 3.10/3.11 + Git)
- **Dlaczego najpierw:** Fundament każdego projektu AI. Utworzenie czystego środowiska wirtualnego (`.venv`), które nie zaśmieca systemu.

### Krok 2: FFmpeg (Silnik renderowania wideo i audio)
- **Dlaczego teraz:** FFmpeg to kręgosłup składania wideo. Nawet bez sztucznej inteligencji pozwala łączyć zwykły obraz z plikiem MP3 i napisami w finalne MP4. Dzięki temu od razu mamy działający silnik montażu („szkielet” wyjściowy).

### Krok 3: Piper TTS (Lokalna synteza mowy lektora)
- **Dlaczego teraz:** Działa w 100% lokalnie, na CPU (0 GB VRAM!), ma świetne polskie głosy i generuje audio w ułamku sekundy. Posiadając FFmpeg i Piper TTS, możemy stworzyć pierwszy działający prototyp wideo (audiobook z planszą i napisami).

### Krok 4: Ollama (Lokalny model językowy do scenariuszy i promptów)
- **Dlaczego teraz:** Pozwala zautomatyzować wymyślanie treści i promptów graficznych. Uruchamiany lokalnie z lekkim modelem 7B/8B. Działa przed generowaniem grafiki, po czym zwalnia pamięć VRAM.

### Krok 5: ComfyUI (Lokalny generator obrazów zoptymalizowany pod 6 GB VRAM)
- **Dlaczego pod koniec:** Jest najbardziej wymagający pod kątem pamięci VRAM i dysku. Posiadając już działający montaż i scenariusze, ComfyUI posłuży do wygenerowania dokładnie takich kadrów, jakie zaplanował scenarzysta.

### Krok 6: n8n / Master Orchestrator (Opcjonalna automatyzacja)
- **Dlaczego na końcu:** Narzędzia automatyzacji mają sens dopiero wtedy, gdy poszczególne klocki (TTS, LLM, ComfyUI, FFmpeg) działają niezawodnie w sposób powtarzalny z poziomu skryptów.

---

## 4. Etapy Realizacji Projektu (Roadmap)

### Faza 1: Fundamenty i Szkielet Montażu (Krótki czas do pierwszego efektu)
- [ ] Przygotowanie struktury projektu i środowiska wirtualnego Python.
- [ ] Weryfikacja instalacji FFmpeg w systemie.
- [ ] Moduł montażu (`src/assembly`): skrypt tworzący film MP4 z obrazu statycznego i pliku audio.
- [ ] Moduł efektu Ken Burns (płynny zoom/pan na statycznych grafikach).

### Faza 2: Dźwięk i Napisy
- [ ] Wdrożenie Piper TTS (polski model głosu, działający na CPU).
- [ ] Automatyczne wyliczanie czasów i generowanie pliku napisów `.srt`.
- [ ] Stylowanie napisów w FFmpeg (wyraźne, czytelne napisy wideo).
- [ ] Dodanie ścieżki muzycznej w tle z automatycznym wyciszaniem pod głos lektora (audio ducking).

### Faza 3: Generowanie Treści i Promptów (LLM)
- [ ] Konfiguracja Ollama z modelem dopasowanym do 6 GB VRAM (`qwen2.5:7b` lub `llama3.1:8b`).
- [ ] Opracowanie szablonów promptów (tworzenie struktury filmu: wstęp, rozwinięcie, podsumowanie + prompty graficzne dla każdej sceny).
- [ ] Zapis scenariusza w ustrukturyzowanym formacie JSON.

### Faza 4: Generowanie Obrazów (ComfyUI)
- [ ] Przygotowanie lekkiego workflow w ComfyUI (SD 1.5 lub SDXL Lightning, rozdzielczość 1080p lub 720p z upscalingiem).
- [ ] Integracja Python z API ComfyUI (wysyłanie promptu, odbiór wygenerowanego pliku PNG).
- [ ] Mechanizm zwalniania pamięci VRAM między etapem LLM a ComfyUI.

### Faza 5: Integracja Końcowa i Automatyzacja
- [ ] Skrypt główny `generate_video.py` – jedno polecenie tworzy cały film od pomysłu do gotowego pliku MP4 w folderze `storage/outputs`.
- [ ] Testy jakościowe i wydajnościowe na docelowym laptopie.
