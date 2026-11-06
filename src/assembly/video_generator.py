"""
Moduł generatora wideo (VideoGenerator) dla AI Video Studio.

Umożliwia:
- Składanie filmu Full HD (1920x1080) z pojedynczego obrazu oraz pliku audio
- Dopasowanie czasu trwania wideo do czasu nagrania dźwiękowego
- Płynny efekt przybliżenia kamery (Ken Burns - zoom-in) z zachowaniem proporcji obrazu
- Nakładanie napisów na ekran z pełną obsługą polskich znaków diakrytycznych
- Sprzętowe kodowanie H.264 z wykorzystaniem NVIDIA NVENC (h264_nvenc)
- Automatyczny, bezpieczny fallback do enkodera programowego (libx264) w razie błędu GPU
- Kodowanie audio w formacie AAC (192 kbps)
"""

import logging
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from src.assembly.ffmpeg_manager import FFmpegExecutionError, FFmpegManager, FFmpegNotFoundError

logger = logging.getLogger(__name__)


class VideoGeneratorError(Exception):
    """Bazowy wyjątek dla błędów generatora wideo."""
    pass


class VideoValidationError(VideoGeneratorError):
    """Wyjątek rzucany przy niepoprawnych danych wejściowych."""
    pass


class VideoGenerator:
    """Główna klasa odpowiedzialna za produkcję wideo w oparciu o FFmpeg."""

    SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".aac", ".ogg", ".flac", ".m4a"}

    def __init__(self, ffmpeg_manager: Optional[FFmpegManager] = None):
        """
        Inicjalizuje generator wideo.
        
        :param ffmpeg_manager: Opcjonalna instancja FFmpegManager.
        """
        self.manager = ffmpeg_manager or FFmpegManager()
        if not self.manager.is_installed():
            raise FFmpegNotFoundError(
                "Nie odnaleziono binariów FFmpeg w projekcie. Uruchom najpierw konfigurację narzędzi."
            )
        self.project_root = self.manager.project_root
        self.outputs_dir = self.project_root / "storage" / "outputs"
        self.intermediates_dir = self.project_root / "storage" / "intermediates"

        # Upewnienie się, że katalogi docelowe istnieją
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.intermediates_dir.mkdir(parents=True, exist_ok=True)

    def validate_inputs(self, image_path: Path, audio_path: Path) -> None:
        """
        Weryfikuje poprawność istnienia i formatów plików wejściowych.
        
        :raises VideoValidationError: Gdy pliki nie istnieją lub mają nieobsługiwane rozszerzenie.
        """
        if not image_path.is_file():
            raise VideoValidationError(f"Plik obrazu nie istnieje: {image_path}")
        if image_path.suffix.lower() not in self.SUPPORTED_IMAGE_EXTENSIONS:
            raise VideoValidationError(
                f"Nieobsługiwany format obrazu '{image_path.suffix}'. "
                f"Dozwolone formaty: {', '.join(sorted(self.SUPPORTED_IMAGE_EXTENSIONS))}"
            )

        if not audio_path.is_file():
            raise VideoValidationError(f"Plik audio nie istnieje: {audio_path}")
        if audio_path.suffix.lower() not in self.SUPPORTED_AUDIO_EXTENSIONS:
            raise VideoValidationError(
                f"Nieobsługiwany format audio '{audio_path.suffix}'. "
                f"Dozwolone formaty: {', '.join(sorted(self.SUPPORTED_AUDIO_EXTENSIONS))}"
            )

    def get_audio_duration(self, audio_path: Path) -> float:
        """
        Odczytuje dokładny czas trwania pliku audio w sekundach za pomocą ffprobe.
        
        :param audio_path: Ścieżka do pliku audio.
        :return: Czas trwania w sekundach (float).
        :raises VideoGeneratorError: Gdy nie uda się pobrać metadanych audio.
        """
        cmd_args = [
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ]
        try:
            _, stdout, _ = self.manager.run_command(cmd_args, tool="ffprobe")
            duration_str = stdout.strip()
            duration = float(duration_str)
            if duration <= 0:
                raise VideoGeneratorError(f"Nieprawidłowy czas trwania audio: {duration}s")
            return duration
        except (ValueError, FFmpegExecutionError) as e:
            raise VideoGeneratorError(f"Błąd podczas odczytu czasu trwania pliku audio {audio_path}: {e}") from e

    def _prepare_text_file(self, text: str) -> Path:
        """
        Zapisuje tekst napisów w pliku UTF-8 w katalogu intermediates,
        co gwarantuje 100% poprawne wyświetlanie polskich znaków w filtrze drawtext.
        """
        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".txt",
            dir=str(self.intermediates_dir),
            delete=False,
        )
        temp_file.write(text.strip())
        temp_file.close()
        return Path(temp_file.name)

    def _build_filter_graph(
        self,
        duration: float,
        fps: int,
        width: int,
        height: int,
        ken_burns: bool,
        zoom_rate: float,
        text_file_path: Optional[Path] = None,
    ) -> str:
        """
        Buduje łańcuch filtrów FFmpeg:
        1. Skalowanie z zachowaniem proporcji i wypełnieniem (bez deformacji obrazu)
        2. Efekt Ken Burns (płynny zoom-in)
        3. Opcjonalny napis na ekranie (drawtext z obsługą polskich znaków)
        """
        filters = []
        total_frames = max(1, int(duration * fps))

        # Krok 1: Skalowanie z zachowaniem proporcji (cover) bez deformacji
        # Obraz jest powiększany tak, by pokryć 1920x1080 i centralnie kadrowany
        filters.append(
            f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
        )

        # Krok 2: Efekt Ken Burns
        if ken_burns:
            # Płynny zoom ze środka kadru od 1.0 do maksymalnie 1.25
            filters.append(
                f"zoompan=z='min(zoom+{zoom_rate:.5f},1.25)':d={total_frames}:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={width}x{height}:fps={fps}"
            )

        # Krok 3: Dodanie tekstu (jeśli podano)
        if text_file_path and text_file_path.is_file():
            # Przygotowanie bezpiecznej ścieżki do pliku dla filtru FFmpeg na Windows
            # Zastępujemy backslashe ukośnikami i escapujemy dwukropek po literze dysku
            safe_text_path = str(text_file_path.resolve()).replace("\\", "/")
            safe_text_path = re.sub(r"^([a-zA-Z]):", r"\1\\:", safe_text_path)

            font_path = "C\\:/Windows/Fonts/arial.ttf"
            drawtext_filter = (
                f"drawtext=fontfile='{font_path}':"
                f"textfile='{safe_text_path}':"
                f"fontcolor=white:fontsize=48:line_spacing=10:"
                f"box=1:boxcolor=black@0.65:boxborderw=14:"
                f"x=(w-text_w)/2:y=h-th-80"
            )
            filters.append(drawtext_filter)

        return ",".join(filters)

    def create_video(
        self,
        image_path: Path,
        audio_path: Path,
        output_path: Optional[Path] = None,
        text_overlay: Optional[str] = None,
        ken_burns: bool = True,
        zoom_rate: float = 0.0012,
        use_nvenc: bool = True,
        fps: int = 30,
        resolution: Tuple[int, int] = (1920, 1080),
    ) -> Path:
        """
        Tworzy plik wideo MP4 z podanego obrazu i ścieżki audio.
        
        :param image_path: Ścieżka do obrazu wejściowego (PNG/JPG).
        :param audio_path: Ścieżka do pliku audio (WAV/MP3).
        :param output_path: Opcjonalna ścieżka do pliku wyjściowego MP4.
        :param text_overlay: Opcjonalny tekst do wyświetlenia na ekranie.
        :param ken_burns: Czy zastosować płynny efekt zoom-in.
        :param zoom_rate: Prędkość zoomu na klatkę (domyślnie 0.0012).
        :param use_nvenc: Czy preferować sprzętowe kodowanie NVIDIA NVENC.
        :param fps: Liczba klatek na sekundę (domyślnie 30).
        :param resolution: Rozdzielczość (szerokość, wysokość), domyślnie 1920x1080.
        :return: Ścieżka do wygenerowanego pliku MP4.
        """
        image_path = Path(image_path).resolve()
        audio_path = Path(audio_path).resolve()

        # 1. Walidacja wejść
        self.validate_inputs(image_path, audio_path)

        # 2. Wyznaczenie ścieżki wyjściowej
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.outputs_dir / f"video_{timestamp}.mp4"
        else:
            output_path = Path(output_path).resolve()

        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 3. Odczytanie czasu trwania audio
        duration = self.get_audio_duration(audio_path)
        logger.info(f"Wykryto czas trwania audio: {duration:.2f} s")

        # 4. Przygotowanie pliku z tekstem (jeśli dotyczy)
        temp_text_file: Optional[Path] = None
        if text_overlay and text_overlay.strip():
            temp_text_file = self._prepare_text_file(text_overlay)

        # 5. Budowa filtrów wideo
        width, height = resolution
        filter_graph = self._build_filter_graph(
            duration=duration,
            fps=fps,
            width=width,
            height=height,
            ken_burns=ken_burns,
            zoom_rate=zoom_rate,
            text_file_path=temp_text_file,
        )

        # 6. Sprawdzenie dostępności NVENC
        nvenc_support = self.manager.check_nvenc_support()
        can_use_nvenc = use_nvenc and nvenc_support.get("h264_nvenc", False)

        def _execute_render(with_nvenc: bool) -> None:
            """Pojedyncza próba renderowania z wybranym enkoderem."""
            vcodec = "h264_nvenc" if with_nvenc else "libx264"
            codec_options = [
                "-c:v", vcodec,
                "-pix_fmt", "yuv420p",
            ]
            if with_nvenc:
                codec_options.extend(["-preset", "p4", "-cq", "23"])
            else:
                codec_options.extend(["-preset", "fast", "-crf", "22"])

            cmd = [
                "-y",                           # Nadpisanie pliku wyjściowego jeśli istnieje
                "-loop", "1",                   # Zapętlenie obrazu statycznego
                "-framerate", str(fps),         # Klatkaż wejściowy
                "-t", f"{duration:.3f}",        # Dokładny czas trwania obrazu
                "-i", str(image_path),          # Wejście wideo (obraz)
                "-i", str(audio_path),          # Wejście audio
                "-filter_complex", filter_graph,
                *codec_options,
                "-c:a", "aac",                  # Kodowanie audio AAC
                "-b:a", "192k",                 # Bitrate audio
                "-t", f"{duration:.3f}",        # Ograniczenie czasu całego pliku wyjściowego
                "-shortest",                    # Zakończenie na najkrótszym strumieniu
                str(output_path),
            ]

            logger.info(f"Rozpoczynanie renderowania wideo (enkoder: {vcodec})...")
            self.manager.run_command(cmd, tool="ffmpeg")

        try:
            if can_use_nvenc:
                try:
                    _execute_render(with_nvenc=True)
                    logger.info(f"Wideo wyrenderowane pomyślnie za pomocą h264_nvenc: {output_path}")
                except FFmpegExecutionError as nvenc_err:
                    logger.warning(
                        f"Renderowanie h264_nvenc nie powiodło się: {nvenc_err}. "
                        "Przełączanie na awaryjny enkoder programowy libx264..."
                    )
                    _execute_render(with_nvenc=False)
                    logger.info(f"Wideo wyrenderowane pomyślnie za pomocą libx264 (fallback): {output_path}")
            else:
                if use_nvenc and not nvenc_support.get("h264_nvenc"):
                    logger.info("NVENC niedostępny na tym urządzeniu. Używanie libx264...")
                _execute_render(with_nvenc=False)
                logger.info(f"Wideo wyrenderowane pomyślnie za pomocą libx264: {output_path}")

        finally:
            # Czyszczenie pliku tymczasowego z tekstem
            if temp_text_file and temp_text_file.is_file():
                try:
                    temp_text_file.unlink()
                except OSError:
                    pass

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise VideoGeneratorError(f"Nie udało się wygenerować pliku wideo: {output_path}")

        return output_path
