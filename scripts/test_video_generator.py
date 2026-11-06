"""
Skrypt weryfikujący moduł VideoGenerator na syntetycznych materiałach lokalnych.

Uruchomienie:
    .\.venv\Scripts\python.exe scripts\test_video_generator.py
"""

import json
import sys
from pathlib import Path

# Poprawne kodowanie konsoli Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# Dodanie katalogu projektu do sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.assembly.ffmpeg_manager import FFmpegManager
from src.assembly.video_generator import VideoGenerator


def create_synthetic_assets(manager: FFmpegManager, intermediates_dir: Path) -> tuple[Path, Path]:
    """Tworzy lokalny syntetyczny obraz i dźwięk za pomocą FFmpeg (bez pobierania z sieci)."""
    image_path = intermediates_dir / "sample_synthetic_image.png"
    audio_path = intermediates_dir / "sample_synthetic_audio.wav"

    # 1. Generowanie obrazu 1920x1080 z gradientem i wzorem geometrycznym
    print("[1/4] Generowanie syntetycznego obrazu testowego (1920x1080)...")
    img_filter = "testsrc=duration=1:size=1920x1080:rate=1"
    manager.run_command(
        ["-y", "-f", "lavfi", "-i", img_filter, "-vframes", "1", str(image_path)],
        tool="ffmpeg",
    )

    # 2. Generowanie 4-sekundowego dźwięku testowego (ton 440Hz z łagodnym wyciszeniem)
    print("[2/4] Generowanie syntetycznego dzwieku testowego (4.0s WAV)...")
    audio_filter = "sine=frequency=440:duration=4.0,afade=t=out:st=3.0:d=1.0"
    manager.run_command(
        ["-y", "-f", "lavfi", "-i", audio_filter, str(audio_path)],
        tool="ffmpeg",
    )

    return image_path, audio_path


def inspect_video_with_ffprobe(manager: FFmpegManager, video_path: Path) -> dict:
    """Odczytuje szczegółowe metadane wygenerowanego pliku MP4 za pomocą ffprobe."""
    cmd = [
        "-v", "error",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name,codec_type",
        "-show_entries", "format=duration,size",
        "-of", "json",
        str(video_path),
    ]
    _, stdout, _ = manager.run_command(cmd, tool="ffprobe")
    return json.loads(stdout)


def run_test():
    print("=" * 60)
    print("TEST MODULU VIDEOGENERATOR (AI VIDEO STUDIO)")
    print("=" * 60)

    manager = FFmpegManager()
    generator = VideoGenerator(manager)
    intermediates = generator.intermediates_dir
    outputs = generator.outputs_dir

    # Krok 1: Tworzenie surowców syntetycznych
    test_image, test_audio = create_synthetic_assets(manager, intermediates)
    print(f"   [OK] Obraz testowy : {test_image}")
    print(f"   [OK] Audio testowe : {test_audio}")

    # Krok 2: Generowanie wideo z NVENC, Ken Burns i polskimi znakami
    print("\n[3/4] Generowanie filmu MP4 (Ken Burns + polskie napisy + NVENC)...")
    polish_text = "Zażółć gęślą jaźń – AI Video Studio działa lokalnie!"
    output_nvenc = outputs / "test_video_nvenc_1080p.mp4"

    result_path = generator.create_video(
        image_path=test_image,
        audio_path=test_audio,
        output_path=output_nvenc,
        text_overlay=polish_text,
        ken_burns=True,
        use_nvenc=True,
        fps=30,
        resolution=(1920, 1080),
    )
    print(f"   [OK] Film wygenerowany: {result_path}")

    # Krok 3: Analiza ffprobe
    print("\n[4/4] Weryfikacja parametrow za pomoca ffprobe:")
    metadata = inspect_video_with_ffprobe(manager, result_path)

    v_stream = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    a_stream = next(s for s in metadata["streams"] if s["codec_type"] == "audio")
    duration = float(metadata["format"]["duration"])
    file_size_kb = int(metadata["format"]["size"]) / 1024

    print(f"   - Rozdzielczosc : {v_stream['width']}x{v_stream['height']} (Oczekiwano: 1920x1080)")
    print(f"   - Klatkaz (FPS) : {v_stream['r_frame_rate']} (Oczekiwano: 30/1)")
    print(f"   - Kodek wideo   : {v_stream['codec_name']} (Oczekiwano: h264)")
    print(f"   - Kodek audio   : {a_stream['codec_name']} (Oczekiwano: aac)")
    print(f"   - Dlugosc filmu : {duration:.2f} s (Oczekiwano: ~4.00s)")
    print(f"   - Rozmiar pliku : {file_size_kb:.1f} KB")

    # Sprawdzenie asercji
    assert v_stream["width"] == 1920 and v_stream["height"] == 1080, "Zla rozdzielczosc!"
    assert v_stream["codec_name"] == "h264", "Zly kodek wideo!"
    assert a_stream["codec_name"] == "aac", "Zly kodek audio!"
    assert 3.8 <= duration <= 4.2, f"Niepoprawny czas trwania filmu: {duration}s"

    # Krok 4: Krótki test awaryjnego enkodera libx264 (fallback)
    print("\nTest weryfikacyjny awaryjnego enkodera libx264 (CPU fallback)...")
    output_libx264 = outputs / "test_video_libx264_1080p.mp4"
    result_fallback = generator.create_video(
        image_path=test_image,
        audio_path=test_audio,
        output_path=output_libx264,
        text_overlay="Test CPU Fallback (libx264) – polskie znaki: ąęćłóśźż",
        ken_burns=True,
        use_nvenc=False,  # Wymuszenie libx264
        fps=30,
        resolution=(1920, 1080),
    )
    fallback_meta = inspect_video_with_ffprobe(manager, result_fallback)
    v_fallback = next(s for s in fallback_meta["streams"] if s["codec_type"] == "video")
    print(f"   [OK] CPU Fallback wygenerowal poprawny plik: {result_fallback}")
    print(f"   - Kodek wideo fallback: {v_fallback['codec_name']}")

    print("\n" + "=" * 60)
    print("WYNIK: Wszystkie testy ETAPU 4 zakonczone pelnym sukcesem!")
    print("=" * 60)


if __name__ == "__main__":
    run_test()
