"""UI flow: /api/videos/{id}/analyze + /analysis, then /auto-clips on top of that analysis."""
import shutil
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from backend import config

FFMPEG = shutil.which("ffmpeg")
pytestmark = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
TERMINAL = {"completed", "failed", "cancelled"}
TEXTS = [
    "Why is this the biggest mistake people make? Never do this!",
    "okay so um yeah the thing is you know",
    "Here are 3 tips you should remember, they are easy and fast.",
    "and then we went to the shop and bought some things today.",
]


def _ff(args):
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def _fake_transcript(src, duration, on_progress=None, **kwargs):
    if on_progress:
        on_progress(1.0)
    segs = [{"start": i * 5.0, "end": (i + 1) * 5.0, "text": TEXTS[i % len(TEXTS)]} for i in range(6)]
    return {"language": "en", "language_probability": 0.99, "duration_sec": 30.0, "model": "fake",
            "text": " ".join(s["text"] for s in segs), "segments": segs}


@pytest.fixture(scope="module")
def client():
    from backend.database import db as dbmod
    if config.STORAGE_DIR.resolve() == (config.ROOT / "storage").resolve() or \
            dbmod.DB_PATH.resolve() == (config.ROOT / "storage" / "clipforge.db").resolve():
        pytest.skip("Tests are not using isolated storage/DB (check tests/conftest.py)")
    from backend.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def cuts_video(client, tmp_path_factory):
    pytest.importorskip("scenedetect")
    pytest.importorskip("cv2")
    p = tmp_path_factory.mktemp("cuts") / "ui30.mp4"
    _ff(["-f", "lavfi", "-i", "color=c=red:s=320x240:d=10:r=15",
         "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=10:r=15",
         "-f", "lavfi", "-i", "color=c=green:s=320x240:d=10:r=15",
         "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p)])
    r = client.post("/api/videos/upload", files=[("files", ("ui30.mp4", p.read_bytes(), "video/mp4"))])
    assert r.status_code == 200, r.text
    return r.json()["uploaded"][0]


def _wait_job(client, job_id, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in TERMINAL:
            return j
        time.sleep(0.3)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def _analyze(client, vid):
    r = client.post(f"/api/videos/{vid}/analyze", json={"language": None, "use_gemini": False})
    assert r.status_code == 200, r.text
    job = _wait_job(client, r.json()["job_id"])
    assert job["status"] == "completed", job


def test_unknown_video(client):
    assert client.post("/api/videos/999999/analyze", json={}).status_code == 404
    assert client.get("/api/videos/999999/analysis").status_code == 404


def test_analysis_none_before_run(client, cuts_video):
    assert client.get(f"/api/videos/{cuts_video['id']}/analysis").json()["status"] == "none"


def test_ui_analyze_flow(client, cuts_video, monkeypatch):
    from backend.workers import analysis_handlers as ah
    monkeypatch.setattr(ah, "transcribe_media", _fake_transcript)
    vid = cuts_video["id"]
    _analyze(client, vid)

    a = client.get(f"/api/videos/{vid}/analysis?include_transcript=false").json()
    assert a["status"] == "ready" and a["language"] == "en" and a["segment_count"] == 6
    assert "transcript" not in a
    assert len(a["scenes"]) >= 2 and {"index", "start", "end"} <= set(a["scenes"][0])
    assert a["scoring_source"] == "local"
    h = a["highlights"]
    assert h and h[0]["rank"] == 1
    for k in ("start", "end", "duration", "score", "local_score", "title", "reason", "text", "source"):
        assert k in h[0]
    full = client.get(f"/api/videos/{vid}/analysis").json()
    assert len(full["transcript"]) == 6


def test_autoclips_use_the_new_analysis(client, cuts_video, monkeypatch):
    from backend.workers import analysis_handlers as ah
    monkeypatch.setattr(ah, "transcribe_media", _fake_transcript)
    vid = cuts_video["id"]
    _analyze(client, vid)
    r = client.post(f"/api/videos/{vid}/auto-clips", json={"count": 1, "min_score": 0, "mode": "accurate"})
    assert r.status_code == 200, r.text
    end = time.time() + 120
    items = []
    while time.time() < end:
        items = client.get(f"/api/clips?video_id={vid}").json()["items"]
        if items and all(c["status"] not in ("pending", "processing") for c in items):
            break
        time.sleep(0.5)
    assert items and all(c["status"] == "ready" for c in items), items
    assert items[0]["ai_score"] is not None


def test_deleting_video_removes_video_analysis(client, cuts_video, monkeypatch):
    from backend.workers import analysis_handlers as ah
    monkeypatch.setattr(ah, "transcribe_media", _fake_transcript)
    data = client.get(f"/api/videos/{cuts_video['id']}/stream").content
    up = client.post("/api/videos/upload", files=[("files", ("copy_ui.mp4", data, "video/mp4"))]).json()["uploaded"][0]
    _analyze(client, up["id"])
    assert client.delete(f"/api/videos/{up['id']}").status_code == 200
    assert client.get(f"/api/videos/{up['id']}/analysis").status_code == 404
    from sqlalchemy import func, select
    from backend.database.db import SessionLocal
    from backend.database.models import VideoAnalysis
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(VideoAnalysis).where(VideoAnalysis.video_id == up["id"])) == 0