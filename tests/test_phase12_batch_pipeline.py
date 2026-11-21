import json
import shutil
import subprocess
import time

import pytest

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


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


def test_pipeline_validation(client):
    assert client.post("/api/batch/pipeline", json={"video_ids": []}).status_code == 422
    assert client.post("/api/batch/pipeline", json={"video_ids": [1], "platform": "nope"}).status_code == 400
    assert client.post("/api/batch/pipeline", json={"video_ids": [1], "music": [{"track_id": 424242}]}).status_code == 404
    assert client.post("/api/batch/pipeline", json={"video_ids": [987654]}).status_code == 404
    assert client.post("/api/batch/pipeline", json={"video_ids": [1], "platform": "instagram_reels",
                                                    "target_sec": 500}).status_code == 400


@needs_ffmpeg
def test_pipeline_clips_only(client, tmp_path):
    vid = _video_with_analysis(client, tmp_path, "plain")
    r = client.post("/api/batch/pipeline", json={"video_ids": [vid], "count": 1, "mode": "fast", "use_gemini": False})
    assert r.status_code == 200 and r.json()["created"] == 1
    job = _wait_job(client, r.json()["job_ids"][0])
    assert job["status"] == "completed", job
    row = _row(client, job["id"])
    assert row["type"] == "batch_pipeline" and row["clips_ready"] == 1 and row["reels_ready"] == 0


@needs_ffmpeg
def test_pipeline_makes_clip_and_reel(client, tmp_path):
    vid = _video_with_analysis(client, tmp_path, "withreel")
    r = client.post("/api/batch/pipeline", json={
        "video_ids": [vid], "count": 1, "mode": "fast", "use_gemini": False, "make_reels": True,
        "platform": "instagram_reels", "size": "720", "reel_mode": "center"})
    assert r.status_code == 200 and r.json()["created"] == 1
    job = _wait_job(client, r.json()["job_ids"][0])
    assert job["status"] == "completed", job
    row = _row(client, job["id"])
    assert row["reels_ready"] == 1 and row["reels_failed"] == 0, row
    items = client.get(f"/api/clips?video_id={vid}").json()["items"]
    reels = [c for c in items if c["status"] == "ready" and c["height"] == 1280]
    assert reels and reels[0]["width"] == 720
    assert any(c["status"] == "ready" and c["height"] != 1280 for c in items)  # the plain clip is still there

    # the same video cannot be queued twice while a job for it is active (here it is finished, so it is allowed)
    again = client.post("/api/batch/pipeline", json={"video_ids": [vid], "count": 1, "use_gemini": False})
    assert again.status_code == 200