# AI Video Studio – Rejestr Licencji Zewnętrznych i Analiza Prawno-Techniczna (THIRD-PARTY-LICENSES.md)

Niniejszy dokument stanowi szczegółowy audyt techniczno-prawny komponentów, bibliotek, binariów oraz modeli sztucznej inteligencji wykorzystywanych lokalnie w projekcie **AI Video Studio**.

> [!CAUTION]
> **Zastrzeżenie prawne (Disclaimer):**
> Niniejszy dokument stanowi analizę inżynierską konfiguracji oprogramowania i nie jest formalną poradą prawną. W przypadku planowania komercyjnej dystrybucji oprogramowania (zwłaszcza w modelach zamkniętych / *proprietary*) zaleca się konsultację z wyspecjalizowanym prawnikiem ds. własności intelektualnej i prawa nowych technologii.

---

## 1. Zestawienie Komponentów: Źródła, Licencje Projektów i Licencje Binariów

W prawie autorskim oprogramowania open-source kluczowe jest rozróżnienie pomiędzy **licencją kodu źródłowego projektu** a **licencją gotowego pliku binarnego**, który powstał w wyniku kompilacji łączącej różne moduły.

| Komponent / Plik w repozytorium | Dokładna wersja pobrana | Licencja kodu projektu (Upstream) | Licencja gotowego pliku binarnego (Composite Binary) | Oficjalne źródło dokładnie tej wersji |
| :--- | :--- | :--- | :--- | :--- |
| **`ffmpeg.exe`** oraz **`ffprobe.exe`** (`tools/ffmpeg/bin/`) | `9.0.2-essentials_build-www.gyan.dev` | Projekt bazowy: **LGPL v2.1+** | **GNU GPL v3.0 or later** *(ze względu na włączone moduły GPL: libx264, libx265, vidstab, rubberband)* | Kod źródłowy kompilacji: [gyan.dev git](https://github.com/GyanD/codexffmpeg) / [ffmpeg.org](https://ffmpeg.org/releases/ffmpeg-release-essentials.zip) |
| **`piper.exe`** (`tools/piper/`) | `2023.11.14-2` (Win64) | **MIT License** | **GNU GPL v3.0 or later** *(złożona binarka: linkuje do `espeak-ng.dll` bez linking exception)* | Kod źródłowy: [rhasspy/piper tag 2023.11.14-2](https://github.com/rhasspy/piper/releases/tag/2023.11.14-2) |
| **`piper_phonemize.dll`** (`tools/piper/`) | `2023.11.14` | **MIT License** | **GNU GPL v3.0 or later** *(linkuje do eSpeak NG)* | Kod źródłowy: [rhasspy/piper-phonemize](https://github.com/rhasspy/piper-phonemize) |
| **`espeak-ng.dll`** oraz **`espeak-ng-data/`** (`tools/piper/`) | `1.51+` | **GNU GPL v3.0** | **GNU GPL v3.0** | Kod źródłowy: [espeak-ng/espeak-ng](https://github.com/espeak-ng/espeak-ng) |
| **`onnxruntime.dll`** oraz **`onnxruntime_providers_shared.dll`** (`tools/piper/`) | `1.14.1` | **MIT License** | **MIT License** | Kod źródłowy: [microsoft/onnxruntime](https://github.com/microsoft/onnxruntime/releases/tag/v1.14.1) |
| **`libtashkeel_model.ort`** (`tools/piper/`) | Snapshot 2023 | **MIT License** *(wymaga weryfikacji)* | **MIT** *(nieużywany w pipeline PL)* | Kod/Model: [rhasspy/libtashkeel](https://github.com/rhasspy/libtashkeel) |
| **`pl_PL-darkman-medium.onnx`** (`models/tts/`) | Snapshot Hugging Face (commit `main`) | **MIT License** | **MIT License** | Wagi modelu: [rhasspy/piper-voices (darkman)](https://huggingface.co/rhasspy/piper-voices/tree/main/pl/pl_PL/darkman/medium) |
| **Dataset nagrań głosu Darkman** | Zbiór NabuCasa | **CC0 1.0 Universal (Public Domain)** | **CC0 1.0 (Public Domain)** | Nagrania: [OHF-Voice/voice-datasets](https://github.com/OHF-Voice/voice-datasets) |

---

## 2. Szczegółowa Weryfikacja Konfiguracji Kompilacji FFmpeg

Weryfikacja lokalnej binarki poleceniami `ffmpeg -version`, `ffmpeg -buildconf` oraz `ffmpeg -L` wykazała jednoznacznie:

1. **Flagi kompilacji GPL:**
   Kompilacja została zbudowana z flagami:
   `--enable-gpl --enable-version3 --enable-libx264 --enable-libx265 --enable-libxvid --enable-libvidstab --enable-librubberband --enable-avisynth`.
2. **Deklaracja licencyjna binarki (`ffmpeg -L`):**
   > *„ffmpeg is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 3 of the License, or (at your option) any later version.”*
3. **Wniosek:**
   Pobrana kompilacja **nie jest wersją LGPL**, lecz pełną kompilacją **GPLv3**.

---

## 3. Szczegółowa Weryfikacja Paczki Piper TTS Standalone

Paczka `piper_windows_amd64.zip` (wydanie `2023.11.14-2`) jest zestawem wielokomponentowym:
1. **Kod rdzenny Pipera (`piper.exe`):** Pochodzi z repozytorium na licencji **MIT**.
2. **Kluczowa zależność fonetyczna (`espeak-ng.dll` + słowniki):** Jest licencjonowana na zasadach **GNU GPL v3.0**.
3. **Charakter powiązania binarnego:**
   Program `piper.exe` w trakcie działania dynamicznie ładuje `piper_phonemize.dll`, która bezpośrednio wywołuje API `espeak-ng.dll`.  
   Zgodnie z doktryną licencji GPL, połączenie to sprawia, że **gotowy skompilowany pakiet binarny Pipera (jako całość redystrybuowana w archiwum) podlega wymogom licencji GPLv3**.

---

## 4. Analiza Prawna: Architektura `subprocess` a Obowiązki Licencyjne

W projekcie AI Video Studio kluczowe znaczenie ma rozróżnienie dwóch poziomów prawnych:

### Poziom 1: Ochrona Autorskiego Kodu Pythona (`src/`)
Nasz kod aplikacji (moduły `video_generator.py`, `ffmpeg_manager.py`, `piper_manager.py`) komunikuje się z `ffmpeg.exe` i `piper.exe` wyłącznie poprzez standardowe mechanizmy międzyprocesowe systemu operacyjnego (`subprocess.run` / potoki `stdin`, `stdout` oraz pliki na dysku):
- Kod Pythona **nie współdzieli przestrzeni adresowej pamięci** z procesami FFmpeg ani Piper.
- Zgodnie ze stanowiskiem Free Software Foundation (FSF FAQ dot. *fork & exec* / *pipes*), taka izolacja procesowa zapobiega rozprzestrzenianiu się „wirusowego” copyleftu na nadrzędny kod skryptowy.
- **Wniosek:** Autorski kod Pythona w katalogu `src/` pozostaje Twoją wyłączną własnością intelektualną i nie musi być licencjonowany na GPLv3.

### Poziom 2: Obowiązki Dotyczące Samych Binariów przy Redystrybucji
Sam fakt wywoływania programów przez `subprocess` **NIE zwalnia dystrybutora z obowiązków GPL w odniesieniu do samych binariów**, jeśli są one dostarczane w jednej paczce z aplikacją:
Jeżeli redystrybuujesz klientom gotowy instalator (np. `setup.exe`) zawierający katalogi `tools/ffmpeg/` oraz `tools/piper/`:
1. **Obowiązek dostarczenia licencji:** Musisz dołączyć pełny tekst licencji GPLv3 dla FFmpeg i eSpeak NG oraz licencji MIT dla Pipera i ONNX Runtime.
2. **Obowiązek udostępnienia kodu źródłowego komponentów GPL:**
   Musisz zapewnić odbiorcom kopię kodu źródłowego (lub pisemną ofertę dostarczenia kodu) dokładnie tych wersji `ffmpeg` (wraz z konfiguracją gyan.dev), `espeak-ng` oraz `piper`.
3. **Zakaz dodatkowych ograniczeń (GPLv3 §10):**
   Nie możesz nałożyć na użytkownika ograniczeń uniemożliwiających mu podmianę, modyfikację czy dekompilację samych binariów `ffmpeg.exe` czy `piper.exe`.

---

## 5. Podsumowanie Ryzyk Prawnych i Rekomendacje dla Dystrybucji Komercyjnej

### Główne Ryzyka w Scenariuszu Tradycyjnego Instalatora (*Bundling*)
- **Ryzyko sporu o integralność produktu:** Jeśli aplikacja komercyjna jest sprzedawana w jednym zamkniętym pakiecie instalacyjnym z binariami GPLv3, organizacje strzegące wolnego oprogramowania (np. SFC – Software Freedom Conservancy) mogą zakwestionować stopień izolacji i domagać się otwarcia całości kodu.
- **Konieczność utrzymywania repozytorium źródeł:** Obowiązek hostowania kodów źródłowych zewnętrznych narzędzi przez min. 3 lata.

---

### Rekomendowane Strategie Komercyjne (Zero GPL Risk)

W celu całkowitego wyeliminowania ryzyka prawnego przy przyszłej komercjalizacji aplikacji rekomenduje się zastosowanie jednej z poniższych architektur:

#### Strategia A: Model *BYOB* (Bring Your Own Binary / Dynamic First-Run Download) – **Najbardziej Rekomendowana**
- Gotowy program komercyjny jest dystrybuowany **bez folderów `tools/ffmpeg/` i `tools/piper/`** w paczce instalatora (jest lekki i w 100% autorski).
- Przy pierwszym uruchomieniu wbudowany asystent konfiguracyjny (lub skrypt instalacyjny) pobiera oficjalne binaria bezpośrednio z serwerów gyan.dev i GitHuba na komputer użytkownika.
- **Skutek prawny:** Ty jako twórca **nie jesteś redystrybutorem binariów GPLv3**. Użytkownik pobiera je na własny użytek (*Private Use*), co w 100% zdejmuje z Ciebie obowiązki licencyjne dystrybutora GPL.

#### Strategia B: Zmiana Kompilacji FFmpeg na LGPL (dla wariantu bundling)
- W przypadku konieczności dołączenia FFmpeg do instalatora: zastąpienie kompilacji Essentials kompilacją **FFmpeg LGPL v2.1/v3** (pozbawioną libx264/libx265, opartą o kodek OpenH264 od Cisco lub sprzętowy enkoder NVENC karty graficznej).
- Sprzętowy enkoder `h264_nvenc` karty NVIDIA **nie jest biblioteką GPL**, lecz interfejsem sterownika GPU, co czyni go w pełni bezpiecznym komercyjnie.

#### Strategia C: Alternatywny Silnik TTS z Permisywną Licencją (np. Apache 2.0)
- Jeśli w przyszłości konieczne będzie rozprowadzanie silnika TTS w instalatorze bez komponentu GPL (`espeak-ng`), można rozważyć silnik mowy oparty o czysty ONNX (np. *Sherpa-ONNX* na licencji Apache 2.0).
