"""
Moduł zarządzania lokalnym FFmpeg i FFprobe dla AI Video Studio.

Umożliwia:
- Wykrywanie lokalnych binariów FFmpeg w katalogu projektu (tools/ffmpeg/bin)
- Sprawdzanie dostępności i odczyt wersji programów
- Detekcję wsparcia sprzętowego kodowania NVIDIA NVENC (h264_nvenc, hevc_nvenc)
- Bezpieczne wykonywanie poleceń z obsługą błędów i logowaniem
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Konfiguracja logera modułu
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [FFmpegManager]: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class FFmpegError(Exception):
    """Bazowy wyjątek dla błędów operacji FFmpeg."""
    pass


class FFmpegNotFoundError(FFmpegError):
    """Wyjątek rzucany, gdy FFmpeg lub FFprobe nie zostaną odnalezione."""
    pass


class FFmpegExecutionError(FFmpegError):
    """Wyjątek rzucany przy niepowodzeniu wykonania polecenia FFmpeg."""
    def __init__(self, message: str, returncode: int, stderr: str):
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class FFmpegManager:
    """Klasa zarządzająca lokalnymi narzędziami FFmpeg i FFprobe."""

    def __init__(self, custom_tools_dir: Optional[Path] = None):
        """
        Inicjalizuje menedżera FFmpeg.
        
        :param custom_tools_dir: Opcjonalna ścieżka do folderu z narzędziami.
                                 Domyślnie szuka w <katalog_projektu>/tools/ffmpeg/bin.
        """
        # Wyznaczenie katalogu głównego projektu
        self.project_root = Path(__file__).resolve().parent.parent.parent
        
        if custom_tools_dir:
            self.bin_dir = Path(custom_tools_dir)
        else:
            self.bin_dir = self.project_root / "tools" / "ffmpeg" / "bin"

        self.ffmpeg_path = self.bin_dir / "ffmpeg.exe"
        self.ffprobe_path = self.bin_dir / "ffprobe.exe"

    def is_installed(self) -> bool:
        """Sprawdza, czy pliki wykonywalne ffmpeg.exe i ffprobe.exe istnieją na dysku."""
        return self.ffmpeg_path.is_file() and self.ffprobe_path.is_file()

    def get_version(self) -> Dict[str, str]:
        """
        Odczytuje i zwraca numery wersji FFmpeg oraz FFprobe.
        
        :return: Słownik zawierający wersje obu narzędzi.
        :raises FFmpegNotFoundError: Gdy pliki binarne nie istnieją.
        """
        if not self.is_installed():
            raise FFmpegNotFoundError(
                f"Nie odnaleziono FFmpeg w lokalizacji: {self.bin_dir}. "
                "Upewnij się, że binaria zostały pobrane do tools/ffmpeg/bin/."
            )

        versions = {}

        # Sprawdzenie wersji ffmpeg
        try:
            res_ffmpeg = subprocess.run(
                [str(self.ffmpeg_path), "-version"],
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
                errors="replace",
            )
            # Pierwsza linia zawiera wersję
            first_line = res_ffmpeg.stdout.splitlines()[0]
            versions["ffmpeg"] = first_line.strip()
        except subprocess.SubprocessError as e:
            versions["ffmpeg"] = f"Błąd odczytu: {e}"

        # Sprawdzenie wersji ffprobe
        try:
            res_ffprobe = subprocess.run(
                [str(self.ffprobe_path), "-version"],
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
                errors="replace",
            )
            first_line = res_ffprobe.stdout.splitlines()[0]
            versions["ffprobe"] = first_line.strip()
        except subprocess.SubprocessError as e:
            versions["ffprobe"] = f"Błąd odczytu: {e}"

        return versions

    def check_nvenc_support(self) -> Dict[str, bool]:
        """
        Sprawdza dostępność sprzętowych enkoderów NVIDIA NVENC.
        
        :return: Słownik z flagami dostępności (h264_nvenc, hevc_nvenc, av1_nvenc).
        """
        if not self.is_installed():
            return {"h264_nvenc": False, "hevc_nvenc": False, "av1_nvenc": False}

        try:
            result = subprocess.run(
                [str(self.ffmpeg_path), "-encoders"],
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
                errors="replace",
            )
            output = result.stdout
            return {
                "h264_nvenc": "h264_nvenc" in output,
                "hevc_nvenc": "hevc_nvenc" in output,
                "av1_nvenc": "av1_nvenc" in output,
            }
        except subprocess.SubprocessError as e:
            logger.error(f"Nie udało się sprawdzić enkoderów NVENC: {e}")
            return {"h264_nvenc": False, "hevc_nvenc": False, "av1_nvenc": False}

    def run_command(
        self,
        arguments: List[str],
        tool: str = "ffmpeg",
        timeout: Optional[int] = None,
    ) -> Tuple[int, str, str]:
        """
        Wykonuje polecenie FFmpeg lub FFprobe.
        
        :param arguments: Lista argumentów przekazywanych do narzędzia.
        :param tool: 'ffmpeg' lub 'ffprobe'.
        :param timeout: Opcjonalny maksymalny czas trwania procesu w sekundach.
        :return: Krotka (kod_wyjścia, stdout, stderr).
        :raises FFmpegNotFoundError: Gdy dane narzędzie nie istnieje.
        :raises FFmpegExecutionError: Gdy narzędzie zwróci kod błędu inny niż 0.
        """
        binary = self.ffmpeg_path if tool == "ffmpeg" else self.ffprobe_path

        if not binary.is_file():
            raise FFmpegNotFoundError(f"Program {tool} nie istnieje pod ścieżką: {binary}")

        full_cmd = [str(binary)] + arguments

        try:
            logger.debug(f"Uruchamianie polecenia: {' '.join(full_cmd)}")
            proc = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )

            if proc.returncode != 0:
                logger.error(f"Polecenie zakończone kodem błędu {proc.returncode}")
                logger.error(f"Komunikat błędu FFmpeg:\n{proc.stderr.strip()}")
                raise FFmpegExecutionError(
                    message=f"Błąd wykonania {tool} (kod {proc.returncode})",
                    returncode=proc.returncode,
                    stderr=proc.stderr,
                )

            return proc.returncode, proc.stdout, proc.stderr

        except subprocess.TimeoutExpired as e:
            logger.error(f"Przekroczono limit czasu ({timeout}s) dla polecenia: {full_cmd}")
            raise FFmpegError(f"Przekroczono limit czasu operacji {tool}: {e}") from e

    def get_diagnostic_report(self) -> Dict[str, object]:
        """Zwraca całościowy raport diagnostyczny o stanie FFmpeg."""
        installed = self.is_installed()
        versions = self.get_version() if installed else {}
        nvenc = self.check_nvenc_support() if installed else {}

        return {
            "installed": installed,
            "ffmpeg_path": str(self.ffmpeg_path),
            "ffprobe_path": str(self.ffprobe_path),
            "versions": versions,
            "nvenc_support": nvenc,
        }


if __name__ == "__main__":
    manager = FFmpegManager()
    print("=" * 60)
    print("AI VIDEO STUDIO - DIAGNOSTYKA FFMPEG")
    print("=" * 60)

    report = manager.get_diagnostic_report()
    print(f"Lokalizacja FFmpeg : {report['ffmpeg_path']}")
    print(f"Lokalizacja FFprobe: {report['ffprobe_path']}")
    print(f"Czy zainstalowany  : {'TAK' if report['installed'] else 'NIE'}")

    if report["installed"]:
        print(f"Wersja FFmpeg      : {report['versions'].get('ffmpeg')}")
        print(f"Wersja FFprobe     : {report['versions'].get('ffprobe')}")
        nvenc = report["nvenc_support"]
        print(f"Wsparcie H.264 NVENC: {'TAK' if nvenc.get('h264_nvenc') else 'NIE'}")
        print(f"Wsparcie HEVC NVENC : {'TAK' if nvenc.get('hevc_nvenc') else 'NIE'}")
        print(f"Wsparcie AV1 NVENC  : {'TAK' if nvenc.get('av1_nvenc') else 'NIE'}")
        print("=" * 60)
        print("Status: FFmpegManager gotowy do pracy.")
    else:
        print("=" * 60)
        print("BŁĄD: FFmpeg nie został wykryty w katalogu tools/ffmpeg/bin/.")
        sys.exit(1)
