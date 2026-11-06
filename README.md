# AI Video Studio (Clone) 🎬🤖

Lokalna, w 100% bezpłatna fabryka wideo AI zaprojektowana dla systemu **Windows 11** i zoptymalizowana pod ograniczenia sprzętowe **NVIDIA RTX 3060 Laptop (6 GB VRAM)**.

---

## 🎯 Cel Projektu

Celem projektu jest pełna automatyzacja produkcji filmów (np. na YouTube Shorts, TikTok lub klasyczne materiały wideo) od pomysłu/hasła do finalnego pliku `.mp4`:
1. **Generowanie scenariusza** (struktura, narracja, prompty wizualne).
2. **Generowanie głosu lektora** (polski lektor lokalnie na CPU).
3. **Generowanie kadrów wizualnych** (grafiki AI w wysokiej rozdzielczości).
4. **Montaż, animacja i napisy** (efekt kamery, dynamiczne napisy, muzyka tła, renderowanie do MP4).

Projekt **nie wymaga żadnych płatnych API ani zewnętrznych subskrypcji**. Wszystkie komponenty działają lokalnie na Twoim komputerze.

---

## 💻 Środowisko Sprzętowe

- **System operacyjny:** Windows 11
- **Procesor:** Intel Core i5-11400H (6 rdzeni / 12 wątków)
- **Karta graficzna:** NVIDIA GeForce RTX 3060 Laptop GPU (6 GB VRAM)
- **Pamięć RAM:** 32 GB
- **Pamięć masowa:** SSD 512 GB

> [!IMPORTANT]
> **Zarządzanie pamięcią 6 GB VRAM:**
> Aby uniknąć błędów braku pamięci (`CUDA Out of Memory`), architektura studia opiera się na **przetwarzaniu sekwencyjnym**:
> - Modele LLM (Ollama) i modele generowania obrazu (ComfyUI) nie pracują jednocześnie.
> - Lektor (Piper TTS) działa w całości na procesorze (CPU), oszczędzając pamięć karty graficznej.
> - Składanie wideo i kodowanie (FFmpeg) korzysta z akceleracji NVENC lub CPU.

---

## 📂 Struktura Katalogów

```
AI-Video-Studio-Clone/
├── .gitattributes
├── .gitignore
├── README.md               # Główny opis projektu i instrukcja startowa
├── AGENTS.md               # Standardy techniczne i zasady pracy dla AI
├── docs/                   # Dokumentacja architektoniczna i plany
│   └── PROJECT-PLAN.md     # Szczegółowy plan etapów realizacji
├── config/                 # Pliki konfiguracyjne, presety i szablony promptów
├── scripts/                # Skrypty narzędziowe i weryfikacyjne
├── src/                    # Kod źródłowy modułów systemu
│   ├── core/               # Główny silnik sterujący (pipeline orchestrator)
│   ├── script_generator/   # Integracja z lokalnym modelem LLM (Ollama)
│   ├── tts/                # Moduł syntezy mowy (Piper TTS)
│   ├── visual/             # Moduł generowania grafiki (ComfyUI API)
│   ├── audio/              # Obsługa muzyki w tle, efektów i miksowania
│   └── assembly/           # Moduł montażu wideo i napisów (FFmpeg)
└── storage/                # Dane lokalne (wykluczone z repozytorium git)
    ├── inputs/             # Własne materiały wejściowe, tematy, grafiki
    ├── intermediates/      # Pliki tymczasowe generowane w trakcie produkcji
    └── outputs/            # Wyrenderowane, gotowe filmy MP4
```

---

## 🛠️ Zastosowany Stos Technologiczny

| Narzędzie | Rola w projekcie | Wykorzystanie zasobów |
| :--- | :--- | :--- |
| **Python** (3.10/3.11) | Język główny orkiestracji i skryptów | RAM / CPU |
| **FFmpeg** | Montaż wideo, animacje zoom/pan, miks audio, napisy | CPU + NVENC |
| **Piper TTS** | Szybka, wysokiej jakości lokalna synteza mowy PL | CPU (0 GB VRAM) |
| **Ollama** | Lokalny model LLM (scenariusze, narracja, prompty) | GPU (VRAM ~4-5 GB, sekwencyjnie) |
| **ComfyUI** | Moduł generowania obrazów (SD 1.5 / SDXL zoptymalizowane) | GPU (VRAM do 6 GB, sekwencyjnie) |

---

## 📖 Dokumentacja i Kolejne Kroki

Szczegółowy plan wdrożenia krok po kroku oraz harmonogram prac znajduje się w pliku:
👉 [docs/PROJECT-PLAN.md](file:///c:/Users/patry/OneDrive/Dokumenty/GitHub/AI-Video-Studio-Clone/docs/PROJECT-PLAN.md)

Zasady deweloperskie i wytyczne dla agentów AI znajdują się w:
👉 [AGENTS.md](file:///c:/Users/patry/OneDrive/Dokumenty/GitHub/AI-Video-Studio-Clone/AGENTS.md)

Rejestr licencji komponentów zewnętrznych (FFmpeg, Piper, modele) znajduje się w:
👉 [docs/THIRD-PARTY-LICENSES.md](file:///c:/Users/patry/OneDrive/Dokumenty/GitHub/AI-Video-Studio-Clone/docs/THIRD-PARTY-LICENSES.md)
