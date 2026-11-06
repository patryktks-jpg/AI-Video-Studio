"""
Moduł zarządzania lokalnym syntezatorem mowy Piper TTS dla AI Video Studio.

Umożliwia:
- Wykrywanie lokalnej binarki piper.exe (tools/piper/piper.exe)
- Wykrywanie i zarządzanie modelami głosowymi ONNX (models/tts/)
- Szybką i naturalną syntezę mowy na procesorze (CPU, 0 GB VRAM)
- Pełną obsługę języka polskiego i znaków diakrytycznych w UTF-8
- Zapis wygenerowanego audio bezpośrednio do nieskompresowanego formatu WAV (22050 Hz)
- Precyzyjną obsługę błędów i szczegółowe logowanie
"""

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PiperError(Exception):
    """Bazowy wyjątek dla błędów syntezy Piper TTS."""
    pass


class PiperNotFoundError(PiperError):
    """Wyjątek rzucany, gdy plik piper.exe nie zostanie odnaleziony."""
    pass


class VoiceModelNotFoundError(PiperError):
    """Wyjątek rzucany, gdy plik modelu głosu (.onnx) nie zostanie odnaleziony."""
    pass


class PiperExecutionError(PiperError):
    """Wyjątek rzucany przy niepowodzeniu procesu syntezy."""
    def __init__(self, message: str, returncode: int, stderr: str):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class PiperManager:
    """Menedżer lokalnego silnika Text-to-Speech Piper."""

    DEFAULT_VOICE_NAME = "pl_PL-darkman-medium"

    def __init__(
        self,
        custom_piper_dir: Optional[Path] = None,
        custom_models_dir: Optional[Path] = None,
    ):
        """
        Inicjalizuje instancję PiperManager.
        
        :param custom_piper_dir: Opcjonalny katalog narzędzia (domyślnie tools/piper).
        :param custom_models_dir: Opcjonalny katalog modeli (domyślnie models/tts).
        """
        self.project_root = Path(__file__).resolve().parent.parent.parent

        self.piper_dir = Path(custom_piper_dir) if custom_piper_dir else self.project_root / "tools" / "piper"
        self.piper_exe = self.piper_dir / "piper.exe"
        self.espeak_data_dir = self.piper_dir / "espeak-ng-data"

        self.models_dir = Path(custom_models_dir) if custom_models_dir else self.project_root / "models" / "tts"
        self.intermediates_dir = self.project_root / "storage" / "intermediates"
        self.intermediates_dir.mkdir(parents=True, exist_ok=True)

    def is_installed(self) -> bool:
        """Sprawdza, czy plik wykonywalny piper.exe istnieje na dysku."""
        return self.piper_exe.is_file()

    def list_available_voices(self) -> List[str]:
        """
        Zwraca listę nazw dostępnych modeli głosowych w katalogu models/tts/.
        Wyszukuje pliki z rozszerzeniem .onnx.
        """
        if not self.models_dir.is_dir():
            return []
        voices = []
        for file in self.models_dir.glob("*.onnx"):
            # Pomijamy ewentualne modele pomocnicze niebędące głosami
            if not file.name.startswith("libtashkeel"):
                voices.append(file.stem)
        return sorted(voices)

    def get_voice_path(self, voice_name: str) -> Tuple[Path, Path]:
        """
        Zwraca ścieżki do pliku modelu .onnx oraz pliku konfiguracyjnego .onnx.json.
        
        :param voice_name: Nazwa modelu, np. 'pl_PL-darkman-medium'.
        :return: Krotka (model_path, config_path).
        :raises VoiceModelNotFoundError: Gdy model nie istnieje.
        """
        model_path = self.models_dir / f"{voice_name}.onnx"
        config_path = self.models_dir / f"{voice_name}.onnx.json"

        if not model_path.is_file():
            raise VoiceModelNotFoundError(
                f"Model głosu '{voice_name}' nie został znaleziony pod ścieżką: {model_path}. "
                f"Dostępne modele: {self.list_available_voices()}"
            )
        return model_path, config_path

    def synthesize(
        self,
        text: str,
        output_wav_path: Optional[Path] = None,
        voice_name: Optional[str] = None,
        speed: float = 1.0,
        sentence_silence: float = 0.25,
    ) -> Path:
        """
        Generuje plik dźwiękowy WAV z podanego tekstu.
        
        :param text: Tekst do przeczytania (z polskimi znakami diakrytycznymi).
        :param output_wav_path: Opcjonalna ścieżka wyjściowa WAV.
        :param voice_name: Nazwa modelu (domyślnie 'pl_PL-darkman-medium').
        :param speed: Prędkość mówienia (1.0 = normalna, <1.0 = szybsza mowa, >1.0 = wolniejsza mowa).
                      Odpowiada parametrowi length_scale w Piper.
        :param sentence_silence: Czas pauzy w sekundach między zdaniami.
        :return: Ścieżka do wygenerowanego pliku WAV.
        :raises PiperNotFoundError: Gdy piper.exe nie istnieje.
        :raises VoiceModelNotFoundError: Gdy model głosu nie istnieje.
        :raises PiperExecutionError: Gdy proces Piper zakończy się błędem.
        """
        if not self.is_installed():
            raise PiperNotFoundError(
                f"Nie odnaleziono pliku piper.exe pod ścieżką: {self.piper_exe}. "
                "Upewnij się, że silnik Piper został pobrany do tools/piper/."
            )

        clean_text = text.strip()
        if not clean_text:
            raise PiperError("Tekst do syntezy nie może być pusty.")

        voice = voice_name or self.DEFAULT_VOICE_NAME
        model_path, config_path = self.get_voice_path(voice)

        if output_wav_path is None:
            output_wav_path = self.intermediates_dir / f"piper_speech_{voice}.wav"
        else:
            output_wav_path = Path(output_wav_path).resolve()

        output_wav_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(self.piper_exe),
            "--model", str(model_path),
            "--output_file", str(output_wav_path),
            "--length_scale", f"{speed:.2f}",
            "--sentence_silence", f"{sentence_silence:.2f}",
        ]

        if config_path.is_file():
            cmd.extend(["--config", str(config_path)])

        if self.espeak_data_dir.is_dir():
            cmd.extend(["--espeak_data", str(self.espeak_data_dir)])

        logger.info(f"Rozpoczynanie syntezy mowy z głosem '{voice}' (długość tekstu: {len(clean_text)} znaków)...")

        try:
            # Tekst przekazywany jest przez stdin w kodowaniu UTF-8
            proc = subprocess.run(
                cmd,
                input=clean_text.encode("utf-8"),
                capture_output=True,
                check=False,
            )

            stderr_text = proc.stderr.decode("utf-8", errors="replace")

            if proc.returncode != 0:
                logger.error(f"Piper zakończył działanie z kodem błędu {proc.returncode}")
                logger.error(f"Komunikat błędu Piper:\n{stderr_text}")
                raise PiperExecutionError(
                    message=f"Błąd syntezy mowy Piper (kod {proc.returncode})",
                    returncode=proc.returncode,
                    stderr=stderr_text,
                )

            if not output_wav_path.is_file() or output_wav_path.stat().st_size == 0:
                raise PiperError(f"Nie utworzono pliku wyjściowego audio: {output_wav_path}")

            logger.info(f"Synteza mowy zakończona sukcesem: {output_wav_path} ({output_wav_path.stat().st_size} bajtów)")
            return output_wav_path

        except subprocess.SubprocessError as e:
            raise PiperError(f"Błąd wywołania procesu Piper: {e}") from e

    def get_diagnostic_report(self) -> Dict[str, object]:
        """Zwraca całościowy raport diagnostyczny o stanie silnika Piper TTS."""
        installed = self.is_installed()
        voices = self.list_available_voices()
        default_voice_ready = self.DEFAULT_VOICE_NAME in voices

        model_info = {}
        if default_voice_ready:
            m_path, c_path = self.get_voice_path(self.DEFAULT_VOICE_NAME)
            model_info["model_path"] = str(m_path)
            model_info["model_size_mb"] = round(m_path.stat().st_size / (1024 * 1024), 2)
            if c_path.is_file():
                try:
                    with open(c_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    model_info["sample_rate"] = cfg.get("audio", {}).get("sample_rate", 22050)
                except Exception:
                    pass

        return {
            "installed": installed,
            "piper_exe": str(self.piper_exe),
            "espeak_data_present": self.espeak_data_dir.is_dir(),
            "models_dir": str(self.models_dir),
            "available_voices": voices,
            "default_voice": self.DEFAULT_VOICE_NAME,
            "default_voice_ready": default_voice_ready,
            "model_info": model_info,
        }


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    manager = PiperManager()
    print("=" * 60)
    print("AI VIDEO STUDIO - DIAGNOSTYKA PIPER TTS")
    print("=" * 60)

    diag = manager.get_diagnostic_report()
    print(f"Lokalizacja piper.exe : {diag['piper_exe']}")
    print(f"Czy zainstalowany     : {'TAK' if diag['installed'] else 'NIE'}")
    print(f"Katalog espeak-ng-data: {'TAK' if diag['espeak_data_present'] else 'NIE'}")
    print(f"Dostępne modele głosu : {diag['available_voices']}")
    print(f"Głos domyślny         : {diag['default_voice']} ({'GOTOWY' if diag['default_voice_ready'] else 'BRAK'})")

    if diag["default_voice_ready"]:
        info = diag["model_info"]
        print(f"Rozmiar modelu ONNX   : {info.get('model_size_mb')} MB")
        print(f"Częstotliwość próbkow.: {info.get('sample_rate')} Hz")
        print("=" * 60)
        print("Status: PiperManager gotowy do syntezy.")
    else:
        print("=" * 60)
        print("BŁĄD: Brak domyślnego modelu pl_PL-darkman-medium.onnx w models/tts/.")
        sys.exit(1)
