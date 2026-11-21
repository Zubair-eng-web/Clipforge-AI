import os
import time

from backend import config
from backend.services import performance as perf


def _old(path, hours=10):
    t = time.time() - hours * 3600
    os.utime(path, (t, t))


def test_low_memory_on_off_restores_env(client):
    before = {k: os.environ.get(k) for k in perf.MANAGED}
    r = client.post("/api/performance", json={"low_memory": True, "frame_width": 384})
    assert r.status_code == 200
    assert os.environ["WHISPER_MODEL"] == "base" and os.environ["FRAME_WIDTH"] == "256"
    assert os.environ["SCENE_AI_BATCH"] == "4" and os.environ["SCENE_AI_MAX_UNITS"] == "80"
    assert client.get("/api/performance").json()["settings"]["low_memory"] is True
    client.post("/api/performance", json={"low_memory": False, "frame_width": 384})
    assert {k: os.environ.get(k) for k in perf.MANAGED} == before


def test_frame_width_option_and_validation(client):
    r = client.post("/api/performance", json={"low_memory": False, "frame_width": 512})
    assert r.status_code == 200 and os.environ["FRAME_WIDTH"] == "512"
    assert client.post("/api/performance", json={"low_memory": False, "frame_width": 999}).status_code == 422
    client.post("/api/performance", json={"low_memory": False, "frame_width": 384})
    assert "FRAME_WIDTH" not in os.environ or os.environ["FRAME_WIDTH"] != "512"


def test_grab_jpeg_uses_frame_width(monkeypatch):
    from backend.scene_ai import engine

    seen = {}

    class R:
        returncode = 0
        stdout = b"jpeg"

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return R()

    monkeypatch.setattr(engine.subprocess, "run", fake_run)
    monkeypatch.setenv("FRAME_WIDTH", "256")
    assert engine.grab_jpeg("x.mp4", 1.0) == b"jpeg"
    assert "scale=256:-2" in seen["cmd"]
    assert engine.grab_jpeg("x.mp4", 1.0, width=384) == b"jpeg"
    assert "scale=384:-2" in seen["cmd"]


def test_stale_temporary_cleanup_keeps_new_files(client):
    tmp = config.STORAGE_DIR / "temporary"
    (tmp / "job_a").mkdir(parents=True, exist_ok=True)
    old, new = tmp / "job_a" / "old.wav", tmp / "new.wav"
    old.write_bytes(b"x" * 1000)
    new.write_bytes(b"y" * 1000)
    _old(old)
    assert client.get("/api/performance").json()["stale_temporary_bytes"] >= 1000
    r = client.post("/api/performance/cleanup", json={"target": "stale_temporary"})
    assert r.status_code == 200 and r.json()["files"] >= 1
    assert not old.exists() and new.exists()
    assert not (tmp / "job_a").exists()  # empty folder removed
    new.unlink()


def test_peaks_cleanup_only_json_cache(client):
    peaks = config.STORAGE_DIR / "music" / "peaks"
    peaks.mkdir(parents=True, exist_ok=True)
    (peaks / "1.json").write_text("[0.1]")
    keep = config.STORAGE_DIR / "music" / "keep_me.mp3"
    keep.write_bytes(b"audio")
    r = client.post("/api/performance/cleanup", json={"target": "music_peaks"})
    assert r.status_code == 200 and r.json()["files"] >= 1
    assert not (peaks / "1.json").exists() and keep.exists()
    keep.unlink()


def test_unknown_cleanup_target(client):
    assert client.post("/api/performance/cleanup", json={"target": "originals"}).status_code == 400


def test_startup_housekeeping_never_raises():
    perf.startup_housekeeping()