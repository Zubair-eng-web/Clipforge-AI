import json
import shutil
import subprocess
import time

import pytest

from backend.editor.ops import edit_clip_file, has_audio, merge_clips_files
from backend.video_processing.ffprobe import probe

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _make(path, seconds=2, audio=True, size="320x180"):
    cmd = ["ffmpeg", "-hide_banner", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=10:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    cmd += ["-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    cmd.append(str(path))
    subprocess.run(cmd, check=True, capture_output=True)


def _wait_job(client, job_id, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("completed", "failed", "cancelled"):
            return j
        time.sleep(0.3)
    raise AssertionError("job did not finish in time")


@needs_ffmpeg
def test_edit_speed_and_trim(tmp_path):
    src, dst = tmp_path / "a.mp4", tmp_path / "out.mp4"
    _make(src, 2)
    out = edit_clip_file(src, dst, 0.5, 1.5, {"speed": 2.0})
    assert abs(out - 0.5) < 0.01
    assert abs(probe(dst)["duration_sec"] - 0.5) < 0.3
    assert src.exists()


@needs_ffmpeg
def test_edit_all_options_and_mute(tmp_path):
    src, dst, dst2 = tmp_path / "a.mp4", tmp_path / "o1.mp4", tmp_path / "o2.mp4"
    _make(src, 2)
    assert has_audio(src)
    edit_clip_file(src, dst, 0, 2, {"volume": 0.5, "fade": 0.3, "brightness": 0.1, "contrast": 1.1,
                                    "saturation": 1.2, "flip_h": True})
    assert has_audio(dst) and abs(probe(dst)["duration_sec"] - 2.0) < 0.4
    edit_clip_file(src, dst2, 0, 2, {"mute": True})
    assert not has_audio(dst2)


@needs_ffmpeg
def test_merge_with_and_without_audio(tmp_path):
    a, b, dst = tmp_path / "a.mp4", tmp_path / "b.mp4", tmp_path / "m.mp4"
    _make(a, 2, audio=True)
    _make(b, 1, audio=False)
    total = merge_clips_files([a, b], [2.0, 1.0], dst, "9:16")
    info = probe(dst)
    assert (info["width"], info["height"]) == (720, 1280)
    assert abs(info["duration_sec"] - total) < 0.5
    assert has_audio(dst)


def _ready_clip(client, tmp_path, name, seconds=2):
    src = tmp_path / f"{name}.mp4"
    _make(src, seconds)
    up = client.post("/api/videos/upload", files={"files": (f"{name}.mp4", src.read_bytes(), "video/mp4")})
    vid = up.json()["uploaded"][0]["id"]
    r = client.post("/api/clips", json={"video_id": vid, "start_sec": 0, "end_sec": seconds, "title": name, "mode": "accurate"})
    assert r.status_code == 200
    assert _wait_job(client, r.json()["job_id"])["status"] == "completed"
    return vid, r.json()["clip"]["id"]


@needs_ffmpeg
def test_edit_and_merge_api(client, tmp_path):
    _, c1 = _ready_clip(client, tmp_path, "one")
    _, c2 = _ready_clip(client, tmp_path, "two")

    assert client.post(f"/api/clips/{c1}/edit", json={}).status_code == 400  # nothing to change

    r = client.post(f"/api/clips/{c1}/edit", json={"speed": 2.0})
    assert r.status_code == 200
    assert _wait_job(client, r.json()["job_id"])["status"] == "completed"
    edited = client.get(f"/api/clips/{r.json()['clip_id']}").json()
    assert edited["status"] == "ready" and edited["title"].endswith("(edited)")
    assert abs(edited["duration_sec"] - 1.0) < 0.4

    assert client.post("/api/editor/merge", json={"clip_ids": [c1]}).status_code == 422
    m = client.post("/api/editor/merge", json={"clip_ids": [c1, c2], "ratio": "first"})
    assert m.status_code == 200
    assert _wait_job(client, m.json()["job_id"])["status"] == "completed"
    merged = client.get(f"/api/clips/{m.json()['clip_id']}").json()
    assert merged["status"] == "ready" and abs(merged["duration_sec"] - 4.0) < 0.6


def test_batch_validation(client):
    assert client.post("/api/batch/start", json={"video_ids": []}).status_code == 422
    assert client.post("/api/batch/start", json={"video_ids": [987654]}).status_code == 404


@needs_ffmpeg
def test_batch_end_to_end_with_existing_analysis(client, tmp_path):
    from backend.database.db import SessionLocal
    from backend.database.models import VideoAnalysis

    src = tmp_path / "long.mp4"
    _make(src, 20, audio=False, size="160x90")
    up = client.post("/api/videos/upload", files={"files": ("long.mp4", src.read_bytes(), "video/mp4")})
    vid = up.json()["uploaded"][0]["id"]
    highlights = [{"rank": 1, "start": 2.0, "end": 18.0, "duration": 16.0, "score": 80.0, "local_score": 70.0,
                   "title": "Best moment", "reason": "test", "text": "hello", "source": "local"}]
    with SessionLocal() as db:
        db.add(VideoAnalysis(video_id=vid, status="ready", language="en", transcript_json="[]", scenes_json="[]",
                             highlights_json=json.dumps(highlights), scoring_source="local"))
        db.commit()

    r = client.post("/api/batch/start", json={"video_ids": [vid], "count": 1, "mode": "fast", "use_gemini": False})
    assert r.status_code == 200 and r.json()["created"] == 1
    job = _wait_job(client, r.json()["job_ids"][0])
    assert job["status"] == "completed", job

    end = time.time() + 40
    ready = []
    while time.time() < end:
        items = client.get(f"/api/clips?video_id={vid}").json()["items"]
        ready = [c for c in items if c["status"] == "ready"]
        if ready:
            break
        time.sleep(0.5)
    assert ready, "auto clip was not exported"
    row = [x for x in client.get("/api/batch/jobs").json()["items"] if x["job_id"] == job["id"]][0]
    assert row["clips_total"] >= 1