"""Phase 3.5: FFmpeg service unit tests + clip export end-to-end tests (real FFmpeg, tiny generated videos)."""
import shutil
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.video_processing.ffmpeg_service import FfmpegError, cut_clip, grab_frame, make_proxy
from backend.video_processing.ffprobe import probe

FFMPEG = shutil.which("ffmpeg")
pytestmark = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
TERMINAL = {"completed", "failed", "cancelled"}


def _ff(args):
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="module")
def sample_video(tmp_path_factory):
    p = tmp_path_factory.mktemp("media") / "sample.mp4"
    _ff(["-f", "lavfi", "-i", "testsrc=duration=4:size=320x240:rate=15",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "15", "-c:a", "aac", "-shortest", str(p)])
    return p


@pytest.fixture(scope="module")
def sample_wav(tmp_path_factory):
    p = tmp_path_factory.mktemp("media_audio") / "sample.wav"
    _ff(["-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(p)])
    return p


# ---------------- FFmpeg service (no server needed) ----------------
def test_probe_sample(sample_video):
    info = probe(sample_video)
    assert info["width"] == 320 and info["height"] == 240
    assert 3.5 < info["duration_sec"] < 4.5


def test_cut_accurate_keeps_original_untouched(sample_video, tmp_path):
    size_before = sample_video.stat().st_size
    dst = tmp_path / "accurate.mp4"
    seen = []
    cut_clip(sample_video, dst, 1.0, 3.0, "accurate", seen.append)
    info = probe(dst)
    assert abs(info["duration_sec"] - 2.0) < 0.3
    assert info["width"] == 320
    assert all(0.0 <= x <= 1.0 for x in seen)
    assert sample_video.stat().st_size == size_before


def test_cut_fast_mode(sample_video, tmp_path):
    dst = tmp_path / "fast.mp4"
    cut_clip(sample_video, dst, 1.0, 3.0, "fast")
    assert 1.4 < probe(dst)["duration_sec"] < 3.2


def test_cut_rejects_bad_range(sample_video, tmp_path):
    with pytest.raises(ValueError):
        cut_clip(sample_video, tmp_path / "x.mp4", 3.0, 3.0)


def test_cut_missing_source_raises(tmp_path):
    with pytest.raises(FfmpegError):
        cut_clip(tmp_path / "nope.mp4", tmp_path / "x.mp4", 0.0, 1.0)


def test_grab_frame(sample_video, tmp_path):
    dst = tmp_path / "frame.jpg"
    grab_frame(sample_video, dst, 1.0)
    assert dst.is_file() and dst.stat().st_size > 0


def test_make_proxy(sample_video, tmp_path):
    dst = tmp_path / "proxy.mp4"
    make_proxy(sample_video, dst, 4.0)
    info = probe(dst)
    assert info["height"] <= 720 and info["height"] % 2 == 0


# ---------------- API end to end (real worker thread) ----------------
@pytest.fixture(scope="module")
def client():
    from backend.database import db as dbmod
    if config.STORAGE_DIR.resolve() == (config.ROOT / "storage").resolve() or \
            dbmod.DB_PATH.resolve() == (config.ROOT / "storage" / "clipforge.db").resolve():
        pytest.skip("Tests are not using isolated storage/DB (check tests/conftest.py)")
    from backend.main import app
    with TestClient(app) as c:
        yield c


def _wait_job(client, job_id, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in TERMINAL:
            return j
        time.sleep(0.3)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


def _upload(client, path, name, mime):
    r = client.post("/api/videos/upload", files=[("files", (name, path.read_bytes(), mime))])
    assert r.status_code == 200, r.text
    return r.json()["uploaded"][0]


def _clip_paths(clip_id):
    from backend.database.db import SessionLocal
    from backend.database.models import Clip
    with SessionLocal() as db:
        c = db.get(Clip, clip_id)
        return c.file_path, c.thumbnail_path


def _make_clip(client, video_id, start, end, mode="accurate", title="t"):
    r = client.post("/api/clips", json={"video_id": video_id, "start_sec": start, "end_sec": end,
                                         "title": title, "mode": mode})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="module")
def video(client, sample_video):
    return _upload(client, sample_video, "sample.mp4", "video/mp4")


def test_export_accurate_end_to_end(client, video):
    body = _make_clip(client, video["id"], 1.0, 3.0, "accurate", "E2E clip")
    clip_id, job_id = body["clip"]["id"], body["job_id"]
    assert body["clip"]["status"] == "pending"

    job = _wait_job(client, job_id)
    assert job["status"] == "completed", job

    clip = client.get(f"/api/clips/{clip_id}").json()
    assert clip["status"] == "ready" and clip["has_file"] and clip["has_thumbnail"]
    assert clip["width"] == 320 and clip["aspect_ratio"] == "4:3"
    assert abs(clip["duration_sec"] - 2.0) < 0.3

    s = client.get(f"/api/clips/{clip_id}/stream")
    assert s.status_code == 200 and s.headers["content-type"].startswith("video/mp4") and len(s.content) > 1000
    d = client.get(f"/api/clips/{clip_id}/download")
    assert d.status_code == 200 and ".mp4" in d.headers.get("content-disposition", "")
    t = client.get(f"/api/clips/{clip_id}/thumbnail")
    assert t.status_code == 200 and t.headers["content-type"].startswith("image/jpeg")

    assert '"status": "completed"' in client.get(f"/api/jobs/{job_id}/events").text
    assert client.post(f"/api/jobs/{job_id}/cancel").status_code == 409  # already finished

    items = client.get(f"/api/clips?video_id={video['id']}").json()["items"]
    assert clip_id in [c["id"] for c in items]

    fp, tp = _clip_paths(clip_id)
    assert (config.STORAGE_DIR / fp).is_file() and (config.STORAGE_DIR / tp).is_file()
    assert client.delete(f"/api/clips/{clip_id}").status_code == 200
    assert not (config.STORAGE_DIR / fp).exists() and not (config.STORAGE_DIR / tp).exists()
    assert client.get(f"/api/clips/{clip_id}").status_code == 404


def test_export_fast_mode(client, video):
    body = _make_clip(client, video["id"], 1.0, 3.0, "fast")
    assert _wait_job(client, body["job_id"])["status"] == "completed"
    clip = client.get(f"/api/clips/{body['clip']['id']}").json()
    assert clip["status"] == "ready" and clip["has_file"]
    client.delete(f"/api/clips/{clip['id']}")


def test_end_is_clamped_to_video_length(client, video):
    body = _make_clip(client, video["id"], 1.0, 999.0)
    assert body["clip"]["end_sec"] <= video["duration_sec"] + 0.01
    _wait_job(client, body["job_id"])
    client.delete(f"/api/clips/{body['clip']['id']}")


def test_clip_validation(client, video):
    vid = video["id"]
    assert client.post("/api/clips", json={"video_id": vid, "start_sec": 100, "end_sec": 101}).status_code == 400
    assert client.post("/api/clips", json={"video_id": vid, "start_sec": 1.0, "end_sec": 1.2}).status_code == 400
    assert client.post("/api/clips", json={"video_id": vid, "start_sec": -1, "end_sec": 2}).status_code == 422
    assert client.post("/api/clips", json={"video_id": vid, "start_sec": 0, "end_sec": 0}).status_code == 422
    assert client.post("/api/clips", json={"video_id": 999999, "start_sec": 0, "end_sec": 2}).status_code == 404
    assert client.get("/api/clips/999999").status_code == 404
    assert client.post("/api/jobs/999999/cancel").status_code == 404


def test_audio_only_cannot_be_clipped(client, sample_wav):
    a = _upload(client, sample_wav, "sample.wav", "audio/wav")
    assert a["has_video"] is False
    assert client.post("/api/clips", json={"video_id": a["id"], "start_sec": 0, "end_sec": 1.5}).status_code == 400
    assert client.post(f"/api/videos/{a['id']}/proxy").status_code == 400
    client.delete(f"/api/videos/{a['id']}")


def test_proxy_flow(client, video):
    r = client.post(f"/api/videos/{video['id']}/proxy").json()
    if not r["ready"]:
        assert _wait_job(client, r["job_id"])["status"] == "completed"
    p = client.get(f"/api/videos/{video['id']}/proxy")
    assert p.status_code == 200 and p.headers["content-type"].startswith("video/mp4")
    assert client.post(f"/api/videos/{video['id']}/proxy").json()["ready"] is True


def test_deleting_video_removes_its_clips_and_files(client, sample_video):
    v = _upload(client, sample_video, "to_delete.mp4", "video/mp4")
    body = _make_clip(client, v["id"], 0.5, 2.5)
    assert _wait_job(client, body["job_id"])["status"] == "completed"
    clip_id = body["clip"]["id"]
    fp, tp = _clip_paths(clip_id)
    assert (config.STORAGE_DIR / fp).is_file()

    assert client.delete(f"/api/videos/{v['id']}").status_code == 200
    assert client.get(f"/api/clips/{clip_id}").status_code == 404
    assert not (config.STORAGE_DIR / fp).exists()
    if tp:
        assert not (config.STORAGE_DIR / tp).exists()