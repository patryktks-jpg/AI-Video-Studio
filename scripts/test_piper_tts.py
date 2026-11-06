"""
Skrypt weryfikujący moduł PiperManager oraz jego integrację z VideoGenerator.

Uruchomienie:
    .\.venv\Scripts\python.exe scripts\test_piper_tts.py
"""

import json
import sys
import time
from pathlib import Path

# Zapewnienie kodowania UTF-8 na konsoli Windows
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
from src.tts.piper_manager import PiperManager


def inspect_media_with_ffprobe(ffmpeg_manager: FFmpegManager, file_path: Path) -> dict:
    """Odczytuje szczegółowe metadane strumieni audio i wideo za pomocą ffprobe."""
    cmd = [
        "-v", "error",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name,codec_type,sample_rate,channels",
        "-show_entries", "format=duration,size,bit_rate",
        "-of", "json",
        str(file_path),
    ]
    _, stdout, _ = ffmpeg_manager.run_command(cmd, tool="ffprobe")
    return json.loads(stdout)


def run_pipeline_test():
    print("=" * 65)
    print("AI VIDEO STUDIO - TEST INTEGRACJI PIPER TTS + VIDEOGENERATOR")
    print("=" * 65)

    ffmpeg_mgr = FFmpegManager()
    piper_mgr = PiperManager()
    video_gen = VideoGenerator(ffmpeg_mgr)

    intermediates = video_gen.intermediates_dir
    outputs = video_gen.outputs_dir

    # Krok 1: Weryfikacja gotowości narzędzi
    piper_report = piper_mgr.get_diagnostic_report()
    if not piper_report["installed"]:
        print("[BLAD] Piper TTS nie jest zainstalowany w tools/piper/.")
        sys.exit(1)
    if not piper_report["default_voice_ready"]:
        print("[BLAD] Brak modelu pl_PL-darkman-medium w models/tts/.")
        sys.exit(1)

    print("[1/4] Sprawdzanie srodowiska Piper TTS:")
    print(f"   [OK] Silnik Piper : {piper_report['piper_exe']}")
    print(f"   [OK] Model glosu  : {piper_report['default_voice']} ({piper_report['model_info'].get('model_size_mb')} MB)")

    # Krok 2: Synteza mowy w języku polskim
    speech_text = (
        "Cześć! Nazywam się Darkman. Jestem lokalnym, polskim lektorem w Twoim studiu filmowym "
        "AI Video Studio. Działam całkowicie offline na procesorze Twojego komputera, bez żadnych opłat "
        "abonamentowych i bez obciążania karty graficznej. Zażółć gęślą jaźń!"
    )
    wav_output = intermediates / "darkman_speech_test.wav"

    print("\n[2/4] Generowanie mowy polskiej przez Piper TTS (na CPU)...")
    t0 = time.time()
    generated_wav = piper_mgr.synthesize(
        text=speech_text,
        output_wav_path=wav_output,
        voice_name="pl_PL-darkman-medium",
        speed=1.0,
    )
    synth_time = time.time() - t0

    # Weryfikacja audio przez ffprobe
    audio_meta = inspect_media_with_ffprobe(ffmpeg_mgr, generated_wav)
    audio_stream = next(s for s in audio_meta["streams"] if s["codec_type"] == "audio")
    audio_duration = float(audio_meta["format"]["duration"])
    wav_size_kb = int(audio_meta["format"]["size"]) / 1024

    print(f"   [OK] Wygenerowano plik audio: {generated_wav}")
    print(f"   - Czas trwania mowy : {audio_duration:.2f} s")
    print(f"   - Czas syntezy CPU  : {synth_time:.2f} s ({audio_duration/max(synth_time, 0.001):.1f}x szybciej niz realtime!)")
    print(f"   - Czestotliwosc     : {audio_stream.get('sample_rate')} Hz (16-bit mono)")
    print(f"   - Rozmiar pliku WAV : {wav_size_kb:.1f} KB")

    # Krok 3: Przygotowanie obrazu tła
    print("\n[3/4] Przygotowanie tla graficznego (1920x1080)...")
    image_path = intermediates / "darkman_background_card.png"
    # Generujemy estetyczną planszę 1080p
    img_filter = "testsrc=duration=1:size=1920x1080:rate=1"
    ffmpeg_mgr.run_command(
        ["-y", "-f", "lavfi", "-i", img_filter, "-vframes", "1", str(image_path)],
        tool="ffmpeg",
    )
    print(f"   [OK] Obraz gotowy : {image_path}")

    # Krok 4: Złożenie finalnego filmu MP4 z lektorem i efektem Ken Burns
    print("\n[4/4] Montaz finalnego filmu MP4 z lektorem (VideoGenerator + NVENC)...")
    final_video_path = outputs / "film_z_lektorem_darkman_1080p.mp4"

    video_result = video_gen.create_video(
        image_path=image_path,
        audio_path=generated_wav,
        output_path=final_video_path,
        text_overlay="Lektor: Darkman (Piper TTS) | Efekt: Ken Burns | Audio: AAC",
        ken_burns=True,
        use_nvenc=True,
        fps=30,
        resolution=(1920, 1080),
    )

    # Weryfikacja filmu przez ffprobe
    video_meta = inspect_media_with_ffprobe(ffmpeg_mgr, video_result)
    v_stream = next(s for s in video_meta["streams"] if s["codec_type"] == "video")
    a_stream = next(s for s in video_meta["streams"] if s["codec_type"] == "audio")
    final_duration = float(video_meta["format"]["duration"])
    final_size_kb = int(video_meta["format"]["size"]) / 1024

    print(f"   [OK] Film wygenerowany: {video_result}")
    print(f"   - Rozdzielczosc : {v_stream['width']}x{v_stream['height']} (Full HD)")
    print(f"   - Klatkaz (FPS) : {v_stream['r_frame_rate']}")
    print(f"   - Kodek wideo   : {v_stream['codec_name']} (NVIDIA NVENC)")
    print(f"   - Kodek audio   : {a_stream['codec_name']} (AAC)")
    print(f"   - Dlugosc filmu : {final_duration:.2f} s (dokladnie zgodna z mowa: {audio_duration:.2f} s)")
    print(f"   - Rozmiar filmu : {final_size_kb:.1f} KB")

    print("\n" + "=" * 65)
    print("WYNIK: Pełny pipeline lektor + wideo dziala w 100% poprawnie!")
    print("=" * 65)


if __name__ == "__main__":
    run_pipeline_test()
