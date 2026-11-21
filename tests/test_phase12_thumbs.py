import shutil
import subprocess
import time

import numpy as np
import pytest

from backend.thumbs import suggest as sg

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg/ffprobe not installed")


def test_score_prefers_sharp_and_lit():
    import cv2
    sharp = np.random.default_rng(1).integers(0, 255, (240, 320, 3), dtype=np.uint8)
    blur = cv2.GaussianBlur(sharp, (31, 31), 0)
    black = np.zeros_like(sharp)
    assert sg.score_image(sharp) > sg.score_image(blur) >= 0
    assert sg.score_image(sharp) > sg.score_image(black)


def test_text_ideas_local_gemini_and_fallback(monkeypatch):
    t, src, w = sg.suggest_texts("Police chase on the bridge tonight", "", False)
    assert src == "local" and t and all(x == x.upper() and len(x) <= 40 for x in t)
    monkeypatch.setattr(sg, "is_configured", lambda: True)
    monkeypatch.setattr(sg, "ask", lambda p: '["Big Chase", "Wild Ride"]')
    t, src, w = sg.suggest_texts("x", "y", True)
    assert src == "gemini" and "BIG CHASE" in t and w is None
    monkeypatch.setattr(sg, "ask", lambda p: "nonsense")
    t, src, w = sg.suggest_texts("x", "", True)
    assert src == "local" and "could not be read" in w

    def boom(p):
        raise RuntimeError("quota")
    monkeypatch.setattr(sg, "ask", boom)
    t, src, w = sg.suggest_texts("x", "", True)
    assert src == "local" and "quota" in w


def test_platforms(client):
    d = client.get("/api/thumbnails/platforms").json()["platforms"]
    assert d["youtube"]["w"] == 1280 and d["shorts"]["h"] == 1920


def _wait(client, jid, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("completed", "failed", "cancelled"):
            return j
        time.sleep(0.3)
    raise AssertionError("job did not finish")


def _clip(client, tmp_path, secs=5):
    src = tmp_path / "t.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=25:duration={secs}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    up = client.post("/api/videos/upload", files={"files": ("t.mp4", src.read_bytes(), "video/mp4")})
    vid = up.json()["uploaded"][0]["id"]
    r = client.post("/api/clips", json={"video_id": vid, "start_sec": 0, "end_sec": secs, "title": "Chase scene", "mode": "accurate"})
    assert _wait(client, r.json()["job_id"])["status"] == "completed"
    return r.json()["clip"]["id"]


@needs_ffmpeg
def test_suggest_endpoint_and_frame_size(client, tmp_path):
    cid = _clip(client, tmp_path)
    r = client.post("/api/thumbnails/suggest", json={"clip_id": cid, "count": 3, "use_gemini": False})
    assert r.status_code == 200, r.text
    d = r.json()
    assert 1 <= len(d["frames"]) <= 3 and d["texts"] and d["source"] == "local"
    assert all(0 <= f["t"] <= 5 and f["score"] >= 0 for f in d["frames"])
    assert client.post("/api/thumbnails/suggest", json={"clip_id": 999999}).status_code == 404
    import cv2
    jpg = client.get(f"/api/clips/{cid}/frame?t=1&size=320")
    assert jpg.status_code == 200
    img = cv2.imdecode(np.frombuffer(jpg.content, np.uint8), cv2.IMREAD_COLOR)
    assert img.shape[1] == 320
