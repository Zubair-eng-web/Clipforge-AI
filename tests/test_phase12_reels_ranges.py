import shutil
import subprocess
import time

import pytest

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _make(path, seconds=20):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-y", "-f", "lavfi", "-i", f"testsrc=size=320x180:rate=10:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True, capture_output=True)


def _wait_job(client, job_id, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("completed", "failed", "cancelled"):
            return j
        time.sleep(0.4)
    raise AssertionError("job did not finish in time")


def _ready_clip(client, tmp_path, seconds=20):
    src = tmp_path / "src.mp4"
    _make(src, seconds)
    up = client.post("/api/videos/upload", files={"files": ("src.mp4", src.read_bytes(), "video/mp4")})
    vid = up.json()["uploaded"][0]["id"]
    r = client.post("/api/clips", json={"video_id": vid, "start_sec": 0, "end_sec": seconds, "title": "src", "mode": "accurate"})
    assert _wait_job(client, r.json()["job_id"])["status"] == "completed"
    return r.json()["clip"]["id"]


@needs_ffmpeg
def test_two_reels_from_two_ranges_and_limit(client, tmp_path):
    cid = _ready_clip(client, tmp_path)
    base = {"clip_id": cid, "platform": "youtube_shorts", "size": "720", "mode": "center"}

    too_long = client.post("/api/reels-studio/create", json={**base, "platform": "instagram_reels", "start_sec": 0, "end_sec": 200})
    assert too_long.status_code == 400

    ids = []
    for s, e in ((0, 8), (8, 16)):
        r = client.post("/api/reels-studio/create", json={**base, "start_sec": s, "end_sec": e, "title": f"part {s}"})
        assert r.status_code == 200
        ids.append((r.json()["job_id"], r.json()["clip_id"]))
    for job_id, clip_id in ids:
        assert _wait_job(client, job_id)["status"] == "completed"
        c = client.get(f"/api/clips/{clip_id}").json()
        assert c["status"] == "ready" and (c["width"], c["height"]) == (720, 1280)
        assert 6.5 <= c["duration_sec"] <= 9.5