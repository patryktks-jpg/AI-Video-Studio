# AI Video Studio – Zasady Współpracy i Standardy Projektu (AGENTS.md)

Niniejszy dokument definiuje standardy techniczne, zasady pracy i wytyczne architektoniczne dla modeli AI oraz programistów rozwijających projekt **AI Video Studio**.

---

## 1. Filozofia Projektu
1. **Lokalność i zero kosztów abonamentowych**: Cały pipeline (LLM, TTS, Image Gen, Montaż) opiera się w 100% na darmowych, lokalnych narzędziach open-source.
2. **Ścisłe poszanowanie zasobów sprzętowych**:
   - Limit: **6 GB VRAM** (RTX 3060 Laptop).
   - Zasada izolacji czasowej: Narzędzia obciążające GPU (Ollama i ComfyUI) **nie mogą działać jednocześnie pod pełnym obciążeniem**.
   - Pipeline musi działać sekwencyjnie krok po kroku (Batch / Stage-by-Stage).
3. **Prostota i czytelność**: Kod pisany z myślą o początkującym programiście – prosta struktura, wyczerpujące komentarze w języku polskim, modularny podział i brak zbędnego overengineeringu.
4. **Bezpieczeństwo i stabilność na Windows 11**:
   - Preferowane ścieżki względne lub obsługa `pathlib.Path`.
   - Zawsze sprawdzanie dostępności narzędzi zewnętrznych przed ich wywołaniem.

---

## 2. Rygorystyczne Zasady Pracy dla Agentów AI
Każdy agent współpracujący z użytkownikiem musi bezwzględnie przestrzegać poniższych reguł:
- **Zasada potwierdzenia (Ask Before Act)**: Przed rozpoczęciem instalacji zewnętrznych paczek, pobierania modeli AI lub tworzenia skomplikowanych modułów, agent przedstawia plan i prosi o akceptację użytkownika.
- **Zakaz samowolnego pobierania modeli AI**: Wagi modeli ważą od 1 GB do kilkunastu GB – SSD ma 512 GB. Pobieranie modeli odbywa się wyłącznie pod kontrolą i za zgodą użytkownika.
- **Żadnych ukrytych kosztów**: Nigdy nie proponuj rozwiązań wymagających płatnego klucza API, subskrypcji ani zewnętrznych chmur obliczeniowych jako domyślnego rozwiązania.
- **Niezależność środowiska (Virtualenv)**: Wszystkie zależności Python muszą być zamknięte w dedykowanym środowisku wirtualnym (`.venv`).
- **Nienaruszalność plików**: Nie usuwaj ani nie nadpisuj plików bez wyraźnego powodu i potwierdzenia.

---

## 3. Standardy Techniczne Kodu
- **Język wiodący**: Python 3.10+ / 3.11 (rekomendowany dla stabilności PyTorch i ComfyUI).
- **Zarządzanie procesami**: Wywoływanie narzędzi CLI (FFmpeg, Piper, Ollama) za pomocą `subprocess` z właściwą obsługą błędów, kodów wyjścia (`returncode`) i logowania.
- **Formaty danych**:
  - Konfiguracja: Pliki YAML / JSON.
  - Napisy: Format SRT / ASS generowane automatycznie z czasów trwania audio.
  - Pliki wyjściowe: MP4 z kodekiem wideo H.264 / H.265 (NVENC przy dostępności lub libx264) i audio AAC.
- **Struktura modułu**:
  - Każdy moduł (`src/tts`, `src/assembly`, etc.) powinien posiadać funkcję testową (np. `if __name__ == "__main__":`), pozwalającą przetestować dany etap w izolacji na pojedynczym pliku demonstracyjnym.

---

## 4. Ograniczenia Sprzętowe i Wybór Modeli
- **Pamięć GPU (6 GB VRAM)**:
  - Modele LLM w Ollama: Maksymalnie 7B–8B Q4_K_M (np. `qwen2.5:7b`, `llama3.1:8b`, `mistral:7b`).
  - Modele graficzne w ComfyUI: SD 1.5, SDXL Lightning / Turbo z flagami oszczędzania pamięci (`--lowvram` lub `--medvram`). Unikamy ciężkich modeli FLUX dev/full.
  - TTS (Piper): Uruchamiany na CPU (minimalne obciążenie, natychmiastowa synteza mowy w języku polskim).
  - Montaż (FFmpeg): Wykorzystanie NVENC (`h264_nvenc`) do szybkiego kodowania wideo bez zajmowania pamięci VRAM modeli.
