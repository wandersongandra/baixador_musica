"""Motor de separacao de faixas por deteccao de silencio via FFmpeg."""

import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from hyperdl.core.utils import ensure_ffmpeg

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a", ".opus", ".wma",
}

FORMAT_CODEC_MAP: dict[str, list[str]] = {
    "mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    "flac": ["-c:a", "flac"],
    "m4a": ["-c:a", "aac", "-b:a", "256k"],
    "aac": ["-c:a", "aac", "-b:a", "256k"],
    "opus": ["-c:a", "libopus", "-b:a", "128k"],
    "wav": ["-c:a", "pcm_s16le"],
    "ogg": ["-c:a", "libvorbis", "-q:a", "4"],
}

DEFAULT_THRESHOLD = "-40dB"
DEFAULT_MIN_SILENCE = 1.0
DEFAULT_MIN_TRACK = 5.0
DEFAULT_LEAD_IN = 0.15
DEFAULT_LEAD_OUT = 0.15
DEFAULT_PREFIX = "faixa"
DEFAULT_DIGITS = 2
DEFAULT_FORMAT = "mp3"
DEFAULT_OUTPUT_DIR = "separado"


@dataclass
class SplitConfig:
    output_dir: Path = Path(DEFAULT_OUTPUT_DIR)
    threshold: str = DEFAULT_THRESHOLD
    min_silence: float = DEFAULT_MIN_SILENCE
    min_track: float = DEFAULT_MIN_TRACK
    lead_in: float = DEFAULT_LEAD_IN
    lead_out: float = DEFAULT_LEAD_OUT
    fmt: str = DEFAULT_FORMAT
    prefix: str = DEFAULT_PREFIX
    digits: int = DEFAULT_DIGITS
    adaptive: bool = False


@dataclass
class Segment:
    start: float
    end: float
    index: int = 0


@dataclass
class SplitResult:
    success: bool
    input_file: Path
    output_dir: Path | None = None
    tracks: list[Path] = field(default_factory=list)
    track_count: int = 0
    segments_found: int = 0
    total_duration: float = 0.0
    audio_info: dict = field(default_factory=dict)
    error: str | None = None
    elapsed: float = 0.0


ProgressCallback = Callable[[float, str], None]
CancelCheck = Callable[[], bool]


def _ffprobe(args: list[str], timeout: int = 60) -> str:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe falhou")
    return result.stdout


def probe_audio(filepath: Path) -> dict[str, Any]:
    out = _ffprobe(
        ["-print_format", "json", "-show_format", "-show_streams", str(filepath)]
    )
    data = json.loads(out)
    fmt = data.get("format", {})
    info: dict[str, Any] = {
        "duration": float(fmt.get("duration", 0) or 0),
        "bitrate": int(fmt.get("bit_rate", 0) or 0),
        "format_name": fmt.get("format_name", ""),
    }
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "audio":
            info["codec"] = stream.get("codec_name", "")
            info["sample_rate"] = int(stream.get("sample_rate", 0) or 0)
            break
    return info


def detect_silences(
    filepath: Path,
    threshold: str = DEFAULT_THRESHOLD,
    min_silence: float = DEFAULT_MIN_SILENCE,
) -> list[tuple[float, float]]:
    result = subprocess.run(
        [
            "ffmpeg", "-i", str(filepath),
            "-af", f"silencedetect=noise={threshold}:d={min_silence}",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    silences: list[tuple[float, float]] = []
    pending: float | None = None
    for line in result.stderr.splitlines():
        m = re.search(r"silence_start:\s*([\d.]+)", line)
        if m:
            pending = float(m.group(1))
            continue
        m = re.search(r"silence_end:\s*([\d.]+)", line)
        if m and pending is not None:
            silences.append((pending, float(m.group(1))))
            pending = None
    return silences


def adaptive_threshold(filepath: Path) -> tuple[str, float]:
    result = subprocess.run(
        [
            "ffmpeg", "-i", str(filepath),
            "-af", "volumedetect",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    match = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", result.stderr)
    if match:
        mean_volume = float(match.group(1))
        threshold_db = mean_volume - 10
        return f"{threshold_db:.0f}dB", mean_volume
    return DEFAULT_THRESHOLD, -30


def build_segments(
    silences: list[tuple[float, float]],
    total_duration: float,
    lead_in: float = DEFAULT_LEAD_IN,
    lead_out: float = DEFAULT_LEAD_OUT,
    min_track: float = DEFAULT_MIN_TRACK,
) -> list[Segment]:
    cut_points: list[float] = []
    for _, silence_end in silences:
        cut_points.append(silence_end + lead_in)

    segments: list[Segment] = []
    start = 0.0
    for i, end in enumerate(cut_points):
        if end - start >= min_track:
            segments.append(
                Segment(start=max(0, start - lead_out), end=end, index=i)
            )
            start = end

    if total_duration - start >= min_track:
        segments.append(
            Segment(
                start=max(0, start - lead_out),
                end=total_duration,
                index=len(segments),
            )
        )

    return segments


def split_audio(
    filepath: Path,
    output_dir: Path,
    segments: list[Segment],
    config: SplitConfig,
    progress: ProgressCallback | None = None,
    is_cancelled: CancelCheck | None = None,
) -> tuple[list[Path], list[str]]:
    codec_args = FORMAT_CODEC_MAP.get(config.fmt, FORMAT_CODEC_MAP["mp3"])
    fmt = config.fmt.lstrip(".")
    files: list[Path] = []
    errors: list[str] = []
    total = len(segments)

    for i, seg in enumerate(segments, 1):
        if is_cancelled and is_cancelled():
            break
        out_name = f"{config.prefix}_{seg.index + 1:0{config.digits}d}.{fmt}"
        out_path = output_dir / out_name

        cmd = [
            "ffmpeg", "-y",
            "-ss", f"{seg.start:.3f}",
            "-i", str(filepath),
            "-t", f"{seg.end - seg.start:.3f}",
            "-map_metadata", "0",
        ] + codec_args + [str(out_path)]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0 or not out_path.exists():
            err_detail = result.stderr.strip().splitlines()
            err_detail = err_detail[-1] if err_detail else "falha no ffmpeg"
            errors.append(f"{out_name}: {err_detail}")
        else:
            files.append(out_path)

        if progress:
            progress(100.0 * i / total, out_name)

    return files, errors


def split_file(
    filepath: Path,
    config: SplitConfig,
    progress: ProgressCallback | None = None,
    is_cancelled: CancelCheck | None = None,
) -> SplitResult:
    start = time.time()

    if not filepath.exists():
        return SplitResult(
            success=False,
            input_file=filepath,
            error=f"Arquivo nao encontrado: {filepath}",
            elapsed=time.time() - start,
        )

    try:
        audio_info = probe_audio(filepath)
    except Exception as e:
        return SplitResult(
            success=False,
            input_file=filepath,
            error=f"Falha ao ler arquivo: {e}",
            elapsed=time.time() - start,
        )

    duration = audio_info.get("duration", 0)

    threshold = config.threshold
    if config.adaptive:
        threshold, _ = adaptive_threshold(filepath)

    silences = detect_silences(filepath, threshold, config.min_silence)
    segments = build_segments(
        silences, duration, config.lead_in, config.lead_out, config.min_track
    )

    output_dir = config.output_dir / filepath.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    tracks: list[Path] = []
    errors: list[str] = []
    if segments:
        tracks, errors = split_audio(
            filepath, output_dir, segments, config, progress, is_cancelled
        )

    return SplitResult(
        success=not errors,
        input_file=filepath,
        output_dir=output_dir,
        tracks=tracks,
        track_count=len(tracks),
        segments_found=len(segments),
        total_duration=duration,
        audio_info=audio_info,
        error="; ".join(errors) if errors else None,
        elapsed=time.time() - start,
    )


def find_audio_files(path: Path, recursive: bool = False) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    files = [
        f
        for f in path.glob(pattern)
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS
    ]
    return sorted(files)
