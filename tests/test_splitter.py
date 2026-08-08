"""Testes do motor de separacao de faixas (offline, gera audio com FFmpeg)."""

import subprocess
from pathlib import Path

import pytest

from hyperdl.core import splitter

pytestmark = pytest.mark.skipif(
    not splitter.ensure_ffmpeg(), reason="FFmpeg nao encontrado"
)


def make_test_wav(path: Path) -> None:
    """Gera audio de 14s: 6s tom + 2s silencio + 6s tom."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=880:duration=6",
        "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1",
        str(path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, timeout=60)


def test_probe_audio(tmp_path):
    wav = tmp_path / "probe.wav"
    make_test_wav(wav)
    info = splitter.probe_audio(wav)
    assert info["duration"] == pytest.approx(14.0, abs=0.5)
    assert info["codec"] == "pcm_s16le"


def test_detect_silences(tmp_path):
    wav = tmp_path / "silencio.wav"
    make_test_wav(wav)
    silences = splitter.detect_silences(wav, "-40dB", 1.0)
    assert len(silences) == 1
    start, end = silences[0]
    assert 5.9 <= start < end <= 8.5


def test_split_file_generates_tracks(tmp_path):
    wav = tmp_path / "album.wav"
    make_test_wav(wav)
    cfg = splitter.SplitConfig(
        output_dir=tmp_path / "out",
        threshold="-40dB",
        min_silence=1.0,
        min_track=5.0,
    )
    result = splitter.split_file(wav, cfg)
    assert result.success
    assert result.segments_found == 2
    assert result.track_count == 2
    assert all(t.exists() for t in result.tracks)
    assert result.output_dir is not None
    assert len(list(result.output_dir.iterdir())) == 2


def test_split_file_missing():
    cfg = splitter.SplitConfig(output_dir=Path("nao_existe"))
    result = splitter.split_file(Path("arquivo_inexistente.mp3"), cfg)
    assert not result.success
    assert "nao encontrado" in (result.error or "")


def test_find_audio_files(tmp_path):
    (tmp_path / "a.mp3").touch()
    (tmp_path / "b.txt").touch()
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.flac").touch()
    assert len(splitter.find_audio_files(tmp_path)) == 1
    assert len(splitter.find_audio_files(tmp_path, recursive=True)) == 2
