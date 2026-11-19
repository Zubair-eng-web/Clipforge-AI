"""Phase 4 tests: highlight scoring, Gemini retry/fallback, scene detection, transcription, analysis API."""
import json
import re
import shutil
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.ai import gemini_client
from backend.ai import highlights as hl

FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
TERMINAL = {"completed", "failed", "cancelled"}

TEXTS = [
    "Why is this the biggest mistake people make? Never do this!",
    "okay so um yeah the thing is you know",
    "Here are 3 tips you should remember, they are easy and fast.",
    "and then we went to the shop and bought some things today.",
]


def _segments(n=12, length=5.0):
    return [{"start": i * length, "end": (i + 1) * length, "text": TEXTS[i % len(TEXTS)]} for i in range(n)]


def _fake_gemini(prompt):
    ids = re.findall(r"^\[(\d+)\]", prompt, flags=re.M)
    return json.dumps([{"id": int(i), "score": 90, "title": f"T{i}", "reason": "good"} for i in ids])


# ---------------- pure logic (no ffmpeg / server) ----------------
def test_build_candidates_lengths():
    cands = hl.build_candidates(_segments())
    assert cands
    for c in cands:
        assert 15 <= c["end"] - c["start"] <= 60
        assert c["text"]


def test_build_candidates_too_short_gives_nothing():
    assert hl.build_candidates(_segments(n=2)) == []


def test_local_score_prefers_hooks():
    good = hl.local_score("Why is this the biggest mistake? Never do this! Remember these 3 tips.", 20)
    bad = hl.local_score("um okay so yeah the thing is um", 20)
    assert 0 <= bad < good <= 100


def test_local_score_empty():
    assert hl.local_score("", 20) == 0.0
    assert hl.local_score("hello", 0) == 0.0


def test_parse_gemini_json_handles_fences():
    raw = '```json\n[{"id": 2, "score": 150, "title": "A", "reason": "r"}, {"bad": 1}]\n```'
    out = hl.parse_gemini_json(raw)
    assert out == {2: {"score": 100.0, "title": "A", "reason": "r"}}
    with pytest.raises(ValueError):
        hl.parse_gemini_json("no json here")


def test_local_only_when_gemini_not_requested():
    items, info = hl.analyze_highlights(_segments(), use_gemini=False)
    assert items and all(i["source"] == "local" for i in items)
    assert info["gemini_used"] is False
    assert [i["score"] for i in items] == sorted([i["score"] for i in items], reverse=True)


def test_gemini_rescoring(monkeypatch):
    monkeypatch.setattr(gemini_client, "is_configured", lambda: True)
    monkeypatch.setattr(gemini_client, "ask", _fake_gemini)
    items, info = hl.analyze_highlights(_segments(), use_gemini=True, sleep_between=0)
    assert info["gemini_used"] is True and info["gemini_scored"] >= 1
    assert any(i["source"] == "gemini" and i["title"].startswith("T") for i in items)
    assert all(0 <= i["score"] <= 100 for i in items)


def test_gemini_permission_error_falls_back_to_local(monkeypatch):
    calls = []

    def boom(prompt):
        calls.append(1)
        raise RuntimeError("403 PERMISSION_DENIED free tier not available")

    monkeypatch.setattr(gemini_client, "is_configured", lambda: True)
    monkeypatch.setattr(gemini_client, "ask", boom)
    items, info = hl.analyze_highlights(_segments(), use_gemini=True, sleep_between=0)
    assert items and all(i["source"] == "local" for i in items)
    assert info["gemini_used"] is False and info["warnings"]
    assert len(calls) == 1  # permanent error: no retry, no hammering


def test_gemini_503_is_retried(monkeypatch):
    calls = []

    def flaky(prompt):
        calls.append(1)
        if len(calls) <= 2:
            raise RuntimeError("503 UNAVAILABLE high demand")
        return _fake_gemini(prompt)

    monkeypatch.setattr(gemini_client, "is_configured", lambda: True)
    monkeypatch.setattr(gemini_client, "ask", flaky)
    monkeypatch.setattr(hl.time, "sleep", lambda s: None)
    items, info = hl.analyze_highlights(_segments(), use_gemini=True, sleep_between=0)
    assert len(calls) >= 3
    assert info["gemini_used"] is True


def test_no_gemini_key_is_reported(monkeypatch):
    monkeypatch.setattr(gemini_client, "is_configured", lambda: False)
    items, info = hl.analyze_highlights(_segments(), use_gemini=True)
    assert items and info["warnings"] and info["gemini_used"] is False


# ---------------- media tests (real FFmpeg / PySceneDetect / Whisper) ----------------
def _ff(args):
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def _make_color_cuts(path, seconds_each=10):
    d = str(seconds_each)
    _ff(["-f", "lavfi", "-i", f"color=c=red:s=320x240:d={d}:r=15",
         "-f", "lavfi", "-i", f"color=c=blue:s=320x240:d={d}:r=15",
         "-f", "lavfi", "-i", f"color=c=green:s=320x240:d={d}:r=15",
         "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)])


@needs_ffmpeg
def test_detect_scenes_on_color_cuts(tmp_path):
    pytest.importorskip("scenedetect")
    pytest.importorskip("cv2")
    from backend.scene_detection.detector import detect_scenes
    p = tmp_path / "cuts.mp4"
    _make_color_cuts(p, 4)
    seen = []
    scenes = detect_scenes(p, 12.0, seen.append)
    assert len(scenes) >= 2
    assert scenes[0]["start"] == 0.0
    assert abs(scenes[-1]["end"] - 12.0) < 1.0
    assert all(0.0 <= x <= 1.0 for x in seen)


@needs_ffmpeg
def test_real_whisper_runs(tmp_path):
    pytest.importorskip("faster_whisper")
    from backend.audio_processing import transcribe as tr
    try:
        tr._get_model()
    except Exception as e:
        pytest.skip(f"Whisper model could not be loaded: {str(e)[:120]}")
    p = tmp_path / "tone.mp4"
    _ff(["-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=15",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(p)])
    out = tr.transcribe_media(p, 4.0)
    assert {"language", "text", "segments", "duration_sec", "model"} <= set(out)
    assert isinstance(out["segments"], list)
    assert not list((config.STORAGE_DIR / "temporary").glob("*.wav"))  # temp audio cleaned up


# ---------------- analysis API end to end (real worker, fake transcription) ----------------
@pytest.fixture(scope="module")
def client():
    from backend.database import db as dbmod
    if config.STORAGE_DIR.resolve() == (config.ROOT / "storage").resolve() or \
            dbmod.DB_PATH.resolve() == (config.ROOT / "storage" / "clipforge.db").resolve():
        pytest.skip("Tests are not using isolated storage/DB (check tests/conftest.py)")
    from backend.main import app
    with TestClient(app) as c:
        yield c


def _wait_job(client, job_id, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in TERMINAL:
            return j
        time.sleep(0.3)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


@pytest.fixture(scope="module")
def cuts_video(client, tmp_path_factory):
    if FFMPEG is None:
        pytest.skip("ffmpeg is not installed")
    pytest.importorskip("scenedetect")
    pytest.importorskip("cv2")
    p = tmp_path_factory.mktemp("cuts") / "cuts30.mp4"
    _make_color_cuts(p, 10)
    r = client.post("/api/videos/upload", files=[("files", ("cuts30.mp4", p.read_bytes(), "video/mp4"))])
    assert r.status_code == 200, r.text
    return r.json()["uploaded"][0]


def _fake_transcript(src, duration, on_progress=None):
    if on_progress:
        on_progress(1.0)
    segs = [{"start": i * 5.0, "end": (i + 1) * 5.0, "text": TEXTS[i % len(TEXTS)]} for i in range(6)]
    return {"language": "en", "language_probability": 0.99, "duration_sec": 30.0, "model": "fake",
            "text": " ".join(s["text"] for s in segs), "segments": segs}


def test_analysis_status(client):
    s = client.get("/api/analysis/status").json()
    assert s["whisper_model"] and "gemini_configured" in s


def test_analysis_validation(client, cuts_video):
    vid = cuts_video["id"]
    assert client.post("/api/analysis/videos/999999/run", json={}).status_code == 404
    assert client.get("/api/analysis/videos/999999").status_code == 404
    assert client.post(f"/api/analysis/videos/{vid}/run", json={"steps": ["nope"]}).status_code == 422
    assert client.post(f"/api/analysis/videos/{vid}/run", json={"steps": []}).status_code == 400
    assert client.post(f"/api/analysis/videos/{vid}/run", json={"steps": ["highlights"]}).status_code == 400
    assert client.get(f"/api/analysis/videos/{vid}/transcript").status_code == 404


def test_full_analysis_pipeline(client, cuts_video, monkeypatch):
    from backend.workers import analysis_handlers as ah
    monkeypatch.setattr(ah, "transcribe_media", _fake_transcript)
    vid = cuts_video["id"]

    r = client.post(f"/api/analysis/videos/{vid}/run", json={"use_gemini": False})
    assert r.status_code == 200, r.text
    job = _wait_job(client, r.json()["job_id"])
    assert job["status"] == "completed", job

    s = client.get(f"/api/analysis/videos/{vid}").json()
    assert s["has_transcript"] and s["language"] == "en"
    assert s["scene_count"] >= 2
    assert s["highlight_count"] >= 1
    assert s["highlight_sources"].get("local", 0) >= 1
    assert s["active_job_id"] is None

    t = client.get(f"/api/analysis/videos/{vid}/transcript").json()
    assert len(t["segments"]) == 6 and t["text"]
    sc = client.get(f"/api/analysis/videos/{vid}/scenes").json()
    assert sc["items"][0]["start_sec"] == 0.0
    h = client.get(f"/api/analysis/videos/{vid}/highlights").json()
    scores = [x["score"] for x in h["items"]]
    assert scores == sorted(scores, reverse=True)
    assert all(x["end_sec"] > x["start_sec"] for x in h["items"])
    assert client.get(f"/api/analysis/videos/{vid}/highlights?min_score=101").json()["total"] == 0

    # second run: only highlights, uses the stored transcript (no transcription call)
    def must_not_run(*a, **k):
        raise AssertionError("transcription should not run again")
    monkeypatch.setattr(ah, "transcribe_media", must_not_run)
    r2 = client.post(f"/api/analysis/videos/{vid}/run", json={"steps": ["highlights"], "use_gemini": False})
    assert _wait_job(client, r2.json()["job_id"])["status"] == "completed"

    # clear
    assert client.delete(f"/api/analysis/videos/{vid}").status_code == 200
    s2 = client.get(f"/api/analysis/videos/{vid}").json()
    assert not s2["has_transcript"] and s2["scene_count"] == 0 and s2["highlight_count"] == 0


def test_deleting_video_removes_analysis(client, cuts_video, monkeypatch):
    from backend.workers import analysis_handlers as ah
    monkeypatch.setattr(ah, "transcribe_media", _fake_transcript)
    r = client.post("/api/videos/upload", files=[("files", ("again.mp4", b"", "video/mp4"))])
    # empty file is rejected, so reuse a fresh copy of the cuts video instead
    vid_src = client.get(f"/api/videos/{cuts_video['id']}/stream").content
    up = client.post("/api/videos/upload", files=[("files", ("copy.mp4", vid_src, "video/mp4"))]).json()["uploaded"][0]
    job = client.post(f"/api/analysis/videos/{up['id']}/run", json={"use_gemini": False}).json()["job_id"]
    assert _wait_job(client, job)["status"] == "completed"
    assert client.delete(f"/api/videos/{up['id']}").status_code == 200
    assert client.get(f"/api/analysis/videos/{up['id']}").status_code == 404
    from backend.database.db import SessionLocal
    from backend.database.models import Highlight, Scene, Transcript
    from sqlalchemy import func, select
    with SessionLocal() as db:
        for m in (Transcript, Scene, Highlight):
            assert db.scalar(select(func.count()).select_from(m).where(m.video_id == up["id"])) == 0