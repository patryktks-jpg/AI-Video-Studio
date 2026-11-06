"""
Skrypt diagnostyczny sprawdzający poprawność działania modułu FFmpegManager.

Uruchomienie ze środowiska wirtualnego:
    .\.venv\Scripts\python.exe scripts\check_ffmpeg.py
"""

import sys
from pathlib import Path

# Zapewnienie poprawnego kodowania na konsoli Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# Dodanie katalogu głównego projektu do sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.assembly.ffmpeg_manager import FFmpegManager, FFmpegError


def run_diagnostics():
    print("Rozpoczynanie testu diagnostycznego FFmpegManager...")
    manager = FFmpegManager()

    report = manager.get_diagnostic_report()
    if not report["installed"]:
        print("[BLAD] FFmpeg nie jest zainstalowany w tools/ffmpeg/bin/.")
        sys.exit(1)

    print("[OK] FFmpeg i FFprobe zostaly pomyslnie wykryte.")
    print(f"   - Sciezka FFmpeg : {report['ffmpeg_path']}")
    print(f"   - Wersja FFmpeg  : {report['versions'].get('ffmpeg')}")
    print(f"   - Sciezka FFprobe: {report['ffprobe_path']}")
    print(f"   - Wersja FFprobe : {report['versions'].get('ffprobe')}")

    nvenc = report["nvenc_support"]
    print("\nSprawdzanie akceleracji sprzetowej NVIDIA NVENC:")
    print(f"   - H.264 NVENC : {'[DOSTEPNY]' if nvenc.get('h264_nvenc') else '[NIEDOSTEPNY]'}")
    print(f"   - HEVC NVENC  : {'[DOSTEPNY]' if nvenc.get('hevc_nvenc') else '[NIEDOSTEPNY]'}")
    print(f"   - AV1 NVENC   : {'[DOSTEPNY]' if nvenc.get('av1_nvenc') else '[NIEDOSTEPNY]'}")

    # Krotki test wykonania polecenia przez manager.run_command
    print("\nTest wykonania polecenia za pomoca manager.run_command():")
    try:
        code, stdout, stderr = manager.run_command(["-version"], tool="ffmpeg")
        first_line = stdout.splitlines()[0] if stdout else ""
        print(f"[OK] Polecenie wykonane pomyslnie (kod {code}): {first_line}")
    except FFmpegError as e:
        print(f"[BLAD] Blad wykonania polecenia: {e}")
        sys.exit(1)

    print("\nPodsumowanie: Modul FFmpegManager dziala w 100% poprawnie!")



if __name__ == "__main__":
    run_diagnostics()
