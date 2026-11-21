import json
import shutil
import subprocess
import time

import pytest

from backend.captions.burn import has_subtitles_filter

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
needs_libass = pytest.mark.skipif(not has_subtitles_filter(), reason="FFmpeg has no libass")


def _make(path, seconds=20, size="320x180"):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=10:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
        check=True, capture_output=True)


def _wait_job(client, job_id, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("completed", "failed", "cancelled"):
            return j
        time.sleep(0.4)
    raise AssertionError("job did not finish in time")


def _video_with_analysis(client, tmp_path, name):
    from backend.database.db import SessionLocal
    from backend.database.models import VideoAnalysis

    src = tmp_path / f"{name}.mp4"
    _make(src, 20)
    up = client.post("/api/videos/upload", files={"files": (f"{name}.mp4", src.read_bytes(), "video/mp4")})
    vid = up.json()["uploaded"][0]["id"]
    highlights = [{"rank": 1, "start": 2.0, "end": 18.0, "duration": 16.0, "score": 80.0, "local_score": 70.0,
                   "title": "Best moment", "reason": "test", "text": "hello", "source": "local"}]
    with SessionLocal() as db:
        db.add(VideoAnalysis(video_id=vid, status="ready", language="en", transcript_json="[]", scenes_json="[]",
                             highlights_json=json.dumps(highlights), scoring_source="local"))
        db.commit()
    return vid


def _row(client, job_id):
    return [x for x in client.get("/api/batch/jobs").json()["items"] if x["job_id"] == job_id][0]


def _fake_words(src, duration_sec=0.0, on_progress=None, language=None):
    if on_progress:
        on_progress(1.0)
    return {"language": "en", "duration_sec": duration_sec, "model": "fake", "words": [
        {"start": 0.5, "end": 1.0, "word": "Hello"}, {"start": 1.0, "end": 1.5, "word": "brave"},
        {"start": 1.5, "end": 2.0, "word": "world"}]}


def _no_words(src, duration_sec=0.0, on_progress=None, language=None):
    return {"language": "en", "duration_sec": duration_sec, "model": "fake", "words": []}


def test_pipeline_rejects_unknown_caption_preset(client):
    r = client.post("/api/batch/pipeline", json={"video_ids": [1], "captions": True, "caption_preset": "nope"})
    assert r.status_code == 400


@needs_ffmpeg
@needs_libass
def test_pipeline_burns_captions_on_clip(client, tmp_path, monkeypatch):
    import backend.workers.caption_handlers as ch
    monkeypatch.setattr(ch, "transcribe_words", _fake_words)
    vid = _video_with_analysis(client, tmp_path, "capclip")
    r = client.post("/api/batch/pipeline", json={"video_ids": [vid], "count": 1, "mode": "fast", "use_gemini": False,
                                                 "captions": True, "caption_preset": "gaming"})
    assert r.status_code == 200 and r.json()["created"] == 1
    job = _wait_job(client, r.json()["job_ids"][0])
    assert job["status"] == "completed", job
    row = _row(client, job["id"])
    assert row["captions_ready"] == 1 and row["captions_skipped"] == 0, row
    items = client.get(f"/api/clips?video_id={vid}").json()["items"]
    assert any(c["status"] == "ready" and c["title"].endswith("(captions)") for c in items)
    assert any(c["status"] == "ready" and not c["title"].endswith("(captions)") for c in items)  # original clip kept


@needs_ffmpeg
@needs_libass
def test_pipeline_no_speech_keeps_clip_without_captions(client, tmp_path, monkeypatch):
    import backend.workers.caption_handlers as ch
    monkeypatch.setattr(ch, "transcribe_words", _no_words)
    vid = _video_with_analysis(client, tmp_path, "nospeech")
    r = client.post("/api/batch/pipeline", json={"video_ids": [vid], "count": 1, "mode": "fast", "use_gemini": False,
                                                 "captions": True})
    job = _wait_job(client, r.json()["job_ids"][0])
    assert job["status"] == "completed", job
    row = _row(client, job["id"])
    assert row["captions_ready"] == 0 and row["captions_skipped"] == 1 and row["clips_ready"] == 1, row
    items = client.get(f"/api/clips?video_id={vid}").json()["items"]
    assert not any(c["title"].endswith("(captions)") for c in items)


@needs_ffmpeg
@needs_libass
def test_pipeline_reel_then_captions(client, tmp_path, monkeypatch):
    import backend.workers.caption_handlers as ch
    monkeypatch.setattr(ch, "transcribe_words", _fake_words)
    vid = _video_with_analysis(client, tmp_path, "reelcap")
    r = client.post("/api/batch/pipeline", json={
        "video_ids": [vid], "count": 1, "mode": "fast", "use_gemini": False, "make_reels": True,
        "platform": "instagram_reels", "size": "720", "reel_mode": "center",
        "captions": True, "caption_preset": "viral_reels"})
    job = _wait_job(client, r.json()["job_ids"][0])
    assert job["status"] == "completed", job
    row = _row(client, job["id"])
    assert row["reels_ready"] == 1 and row["captions_ready"] == 1, row
    items = client.get(f"/api/clips?video_id={vid}").json()["items"]
    capped = [c for c in items if c["status"] == "ready" and c["title"].endswith("(captions)")]
    assert capped and capped[0]["height"] == 1280  # captions were burned on the reel, not the plain clip