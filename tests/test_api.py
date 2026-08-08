"""Testes da API web (FastAPI TestClient)."""

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hyperdl.api.app import app
from hyperdl.core import splitter

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_defaults():
    r = client.get("/api/defaults")
    assert r.status_code == 200
    assert "mp3" in r.json()["audio_formats"]


def test_settings_roundtrip():
    body = {"output_dir": "downloads", "threshold": "-45dB"}
    r = client.put("/api/settings", json=body)
    assert r.status_code == 200
    assert r.json()["threshold"] == "-45dB"
    r2 = client.get("/api/settings")
    assert r2.json()["threshold"] == "-45dB"
    client.put("/api/settings", json={"threshold": "-40dB"})


def test_download_invalid_request():
    r = client.post("/api/download", json={"urls": []})
    assert r.status_code == 400


def test_files_list_and_traversal_guard():
    r = client.get("/api/files")
    assert r.status_code == 200
    r2 = client.get("/api/files", params={"rel": "..\\..\\Windows"})
    assert r2.status_code == 403


@pytest.mark.skipif(not splitter.ensure_ffmpeg(), reason="FFmpeg nao encontrado")
def test_upload_split_flow(tmp_path):
    wav = tmp_path / "upload_test.wav"
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

    r = client.post("/api/split", json={"file": path, "min_track": 5.0})
    assert r.status_code == 200
    job_id = r.json()["id"]

    import time

    for _ in range(40):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(0.5)
    assert job["status"] == "completed"
    assert job["result"]["track_count"] == 2

    r = client.delete(f"/api/jobs/{job_id}")
    assert r.status_code == 200


def test_upload_rejects_bad_extension():
    r = client.post("/api/files/upload", files={"file": ("not_audio.exe", b"x", "application/octet-stream")})
    assert r.status_code == 400
