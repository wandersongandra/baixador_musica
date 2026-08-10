"""Testes da API web (FastAPI TestClient)."""

import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hyperdl.api import files as files_api
from hyperdl.api.app import app
from hyperdl.core.utils import ensure_ffmpeg
from hyperdl.settings import settings as settings_mgr

client = TestClient(app)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Isola settings.json e as areas de arquivos em um diretorio temporario."""
    monkeypatch.setattr(settings_mgr, "path", tmp_path / "settings.json")
    monkeypatch.setattr(files_api, "BASE_DIR", tmp_path)
    monkeypatch.setattr(files_api, "UPLOAD_DIR", tmp_path / "downloads" / "uploads")
    return tmp_path


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_defaults():
    r = client.get("/api/defaults")
    assert r.status_code == 200
    body = r.json()
    assert "mp3" in body["audio_formats"]
    assert body["max_upload_mb"] == files_api.MAX_UPLOAD_MB


def test_settings_roundtrip(isolated):
    r = client.put("/api/settings", json={"threshold": "-45dB"})
    assert r.status_code == 200
    assert r.json()["threshold"] == "-45dB"
    r2 = client.get("/api/settings")
    assert r2.json()["threshold"] == "-45dB"


def test_settings_partial_update_preserves_other_keys(isolated):
    client.put("/api/settings", json={"output_dir": "musicas", "threshold": "-45dB"})
    client.put("/api/settings", json={"threshold": "-40dB"})
    r = client.get("/api/settings")
    assert r.json()["threshold"] == "-40dB"
    assert r.json()["output_dir"] == "musicas"
    assert r.json()["split_dir"] == "separado"
    assert r.json()["min_silence"] == 1.0


def test_settings_rejects_invalid_values(isolated):
    r = client.put("/api/settings", json={"audio_format": "xyz"})
    assert r.status_code == 422


def test_download_invalid_request():
    r = client.post("/api/download", json={"urls": []})
    assert r.status_code == 422
    r2 = client.post("/api/download", json={"urls": ["  "], "audio_format": "xyz"})
    assert r2.status_code == 422


def test_files_list_and_traversal_guard(isolated):
    r = client.get("/api/files")
    assert r.status_code == 200
    r2 = client.get("/api/files", params={"rel": "..\\..\\Windows"})
    assert r2.status_code == 403


def test_download_restricted_to_content_dirs(isolated):
    secret = isolated / "segredo.txt"
    secret.write_text("segredo", encoding="utf-8")
    r = client.get("/api/files/download", params={"path": "segredo.txt"})
    assert r.status_code == 403


@pytest.mark.skipif(not ensure_ffmpeg(), reason="FFmpeg nao encontrado")
def test_upload_split_flow(isolated):
    wav = isolated / "upload_test.wav"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=880:duration=6",
        "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1",
        str(wav),
    ]
    subprocess.run(cmd, capture_output=True, check=True, timeout=60)

    with wav.open("rb") as f:
        r = client.post("/api/files/upload", files={"file": ("album_test.wav", f, "audio/wav")})
    assert r.status_code == 200
    path = r.json()["path"]
    assert Path(path).parts[:2] == ("downloads", "uploads")

    r = client.post(
        "/api/split",
        json={"file": path, "min_track": 5.0, "output_dir": str(isolated / "out")},
    )
    assert r.status_code == 200
    job_id = r.json()["id"]

    for _ in range(40):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.5)
    assert job["status"] == "completed"
    assert job["result"]["track_count"] == 2

    r = client.delete(f"/api/jobs/{job_id}")
    assert r.status_code == 200
    assert (isolated / "out" / "album_test").is_dir()


def test_upload_rejects_bad_extension():
    r = client.post("/api/files/upload", files={"file": ("not_audio.exe", b"x", "application/octet-stream")})
    assert r.status_code == 400
