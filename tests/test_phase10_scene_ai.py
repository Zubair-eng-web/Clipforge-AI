import subprocess
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.database.db import SessionLocal
from backend.database.models import CategoryScene, Clip, Scene, Video
from backend.main import app
from backend.scene_ai import engine
from backend.scene_ai.categories import CATEGORIES
from backend.scene_ai.extract import write_srt
from backend.services.paths import resolve_storage
from backend.video_processing import ffmpeg_service


# ---------- pure logic ----------
def test_categories_complete():
    assert len(CATEGORIES) == 20 and "custom" in CATEGORIES
    assert all(v["label"] and v["rule"] for v in CATEGORIES.values())


def test_build_units_merge_and_split():
    shots = [{"start": 0, "end": 5}, {"start": 5, "end": 10}, {"start": 10, "end": 15}, {"start": 15, "end": 20}]
    u = engine.build_units(shots, 20)
    assert len(u) == 1 and u[0]["start"] == 0 and u[0]["end"] == 20
    long_shot = engine.build_units([{"start": 0, "end": 100}], 100)
    assert len(long_shot) == 8


def _res(scores, src="gemini"):
    return [{"scores": {"fighting": s}, "desc": "d", "source": src} for s in scores]


def test_find_segments_bridge_and_threshold():
    units = [{"start": i * 10, "end": i * 10 + 10} for i in range(5)]
    segs = engine.find_segments(units, _res([0, 80, 10, 80, 0]), "fighting", 60, merge=True)
    assert len(segs) == 1 and segs[0]["start"] == 10 and segs[0]["end"] == 40 and segs[0]["status"] == "detected"
    assert len(engine.find_segments(units, _res([0, 80, 10, 80, 0]), "fighting", 60, merge=False)) == 2
    weak = engine.find_segments(units, _res([0, 45, 45, 0, 0]), "fighting", 60)
    assert weak and weak[0]["status"] == "uncertain"
    local = engine.find_segments(units, _res([0, 90, 90, 0, 0], "local"), "fighting", 60)
    assert local[0]["status"] == "uncertain"


def test_fit_window_picks_best_part():
    units = [{"start": i * 10, "end": i * 10 + 10} for i in range(4)]
    assert engine.fit_window(units, [10, 10, 90, 90], [0, 1, 2, 3], 20) == (20, 40)
    assert engine.fit_window(units, [10, 10, 90, 90], [0, 1, 2, 3], 100) == (0, 40)  # no padding


def test_snap_range():
    assert engine.snap_range(11.2, 28.9, [0, 10, 20, 30, 40], 0, 40) == (10, 30)


def test_parse_response_and_local_scores():
    raw = '```json\n[{"id": 1, "scores": {"fighting": 150}, "description": "x"}]\n```'
    assert engine.parse_response(raw, ["fighting"])[1]["scores"]["fighting"] == 100.0
    with pytest.raises(ValueError):
        engine.parse_response("nothing", ["fighting"])
    assert engine.local_scores("fight punch kick", ["fighting"])["fighting"] <= 60


def test_write_srt(tmp_path):
    p = tmp_path / "a.srt"
    n = write_srt(p, [{"start": 5, "end": 8, "text": "hello"}, {"start": 50, "end": 52, "text": "late"}], 4, 20)
    assert n == 1 and "00:00:01,000 --> 00:00:04,000" in p.read_text(encoding="utf-8")


# ---------- API ----------
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_api_validation(client):
    assert len(client.get("/api/scene-ai/categories").json()["items"]) == 20
    assert client.post("/api/scene-ai/videos/99999999/run", json={"categories": [{"key": "fighting"}]}).status_code == 404
    assert client.post("/api/scene-ai/videos/99999999/run", json={"categories": []}).status_code == 422


# ---------- real video: detect (AI mocked), export, verify MP4 files ----------
def _wait_job(client, job_id, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("completed", "failed", "cancelled"):
            return j
        time.sleep(0.5)
    raise AssertionError("job timeout")


def _wait_clip(client, vid, scene_id, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        items = client.get(f"/api/scene-ai/videos/{vid}/scenes").json()["items"]
        s = next(x for x in items if x["id"] == scene_id)
        if s["clip_status"] in ("ready", "failed"):
            return s
        time.sleep(0.5)
    raise AssertionError("clip timeout")


def test_scene_pipeline_creates_category_clips(client, monkeypatch):
    try:
        exe = ffmpeg_service._exe()
    except Exception:
        pytest.skip("ffmpeg not available")
    rel = f"original_videos/test_p10_{uuid.uuid4().hex}.mp4"
    dst = config.STORAGE_DIR / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([exe, "-y", "-f", "lavfi", "-i", "testsrc=duration=40:size=320x240:rate=15",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=40", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(dst)], check=True, capture_output=True)
    with SessionLocal() as db:
        v = Video(original_name="p10.mp4", stored_path=rel, size_bytes=dst.stat().st_size, duration_sec=40.0,
                  width=320, height=240, format="mp4", status="uploaded")
        db.add(v)
        db.flush()
        db.add(Scene(video_id=v.id, idx=0, start_sec=0.0, end_sec=20.0))
        db.add(Scene(video_id=v.id, idx=1, start_sec=20.0, end_sec=40.0))
        db.commit()
        vid = v.id

    def fake(units, segments, cats, src, **kw):
        keys = [c["key"] for c in cats]
        res = [{"scores": {k: (90.0 if u["start"] >= 20 else 5.0) for k in keys}, "desc": "fake", "source": "gemini"}
               for u in units]
        return res, {"warnings": [], "gemini_batches": 1, "local_units": 0}

    monkeypatch.setattr(engine, "classify", fake)
    opts = {"use_vision": False, "use_speech": False, "min_scene_sec": 5}
    try:
        # 1) Complete Scene (Automatic) + auto extract
        r = client.post(f"/api/scene-ai/videos/{vid}/run",
                        json={"categories": [{"key": "fighting", "duration": "auto"}], "options": {**opts, "auto_extract": True}})
        assert _wait_job(client, r.json()["job_id"])["status"] == "completed"
        items = client.get(f"/api/scene-ai/videos/{vid}/scenes").json()["items"]
        assert len(items) == 1 and items[0]["category"] == "fighting" and items[0]["status"] == "detected"
        assert abs(items[0]["start_sec"] - 20) < 0.5 and abs(items[0]["end_sec"] - 40) < 0.5
        s = _wait_clip(client, vid, items[0]["id"])
        assert s["clip_status"] == "ready" and s["verified"] is True
        assert (config.STORAGE_DIR / "generated_clips" / "fighting" / f"{s['filename']}.mp4").is_file()

        # 2) duplicate prevention: same scene is not created again
        r = client.post(f"/api/scene-ai/videos/{vid}/run",
                        json={"categories": [{"key": "fighting"}], "options": {**opts, "auto_extract": True}})
        assert _wait_job(client, r.json()["job_id"])["status"] == "completed"
        assert len(client.get(f"/api/scene-ai/videos/{vid}/scenes").json()["items"]) == 1

        # 3) fixed 10 s duration, preview first, then extract
        r = client.post(f"/api/scene-ai/videos/{vid}/run",
                        json={"categories": [{"key": "romantic", "duration": 10}], "options": {**opts, "auto_extract": False}})
        assert _wait_job(client, r.json()["job_id"])["status"] == "completed"
        rom = [x for x in client.get(f"/api/scene-ai/videos/{vid}/scenes?category=romantic").json()["items"]]
        assert len(rom) == 1 and abs(rom[0]["duration_sec"] - 10) < 0.6
        assert client.post(f"/api/scene-ai/videos/{vid}/extract", json={"scene_ids": [rom[0]["id"]]}).json()["created"] == 1
        s2 = _wait_clip(client, vid, rom[0]["id"])
        assert s2["clip_status"] == "ready" and s2["verified"] is True
        assert (config.STORAGE_DIR / "generated_clips" / "romantic" / f"{s2['filename']}.mp4").is_file()
        assert client.get(f"/api/scene-ai/videos/{vid}/export.zip").status_code == 200
    finally:
        with SessionLocal() as db:
            for c in db.query(Clip).filter(Clip.video_id == vid).all():
                for p in (c.file_path, c.thumbnail_path):
                    if p:
                        try:
                            resolve_storage(p).unlink(missing_ok=True)
                        except (ValueError, OSError):
                            pass
                db.delete(c)
            for sc in db.query(CategoryScene).filter(CategoryScene.video_id == vid).all():
                if sc.thumbnail_path:
                    try:
                        resolve_storage(sc.thumbnail_path).unlink(missing_ok=True)
                    except (ValueError, OSError):
                        pass
            vv = db.get(Video, vid)
            if vv:
                db.delete(vv)
            db.commit()
        dst.unlink(missing_ok=True)