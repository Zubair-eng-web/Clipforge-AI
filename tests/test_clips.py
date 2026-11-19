import json
import shutil
import subprocess
import time

import pytest

from backend.config import STORAGE_DIR
from backend.database.db import SessionLocal
from backend.database.models import Job
from backend.video_processing import ffmpeg_service as ff
from backend.video_processing.ffprobe import probe

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)


@pytest.fixture(scope="module")
def sample_path(tmp_path_factory):
    out = tmp_path_factory.mktemp("clipmedia") / "sample6.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=15",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
         "-c:v", "libx264", "-g", "15", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)],
        check=True, capture_output=True,
    )
    return out


@pytest.fixture(scope="module")
def wav_path(tmp_path_factory):
    out = tmp_path_factory.mktemp("clipmedia") / "tone.wav"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(out)],
                   check=True, capture_output=True)
    return out


def files_in(sub):
    d = STORAGE_DIR / sub
    return {p.name for p in d.iterdir() if p.is_file() and p.name != ".gitkeep"} if d.exists() else set()


def upload(client, path, ctype="video/mp4"):
    r = client.post("/api/videos/upload", files=[("files", (path.name, path.read_bytes(), ctype))])
    assert r.status_code == 200, r.text
    return r.json()["uploaded"][0]


def wait_job(client, job_id, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("completed", "failed", "cancelled"):
            return j
        time.sleep(0.3)
    raise AssertionError("job timeout")


def export(client, video_id, start, end, mode="accurate", title=""):
    r = client.post("/api/clips", json={"video_id": video_id, "start_sec": start, "end_sec": end,
                                         "mode": mode, "title": title})
    assert r.status_code == 200, r.text
    return r.json()


# ---------- ffmpeg service ----------
def test_cut_accurate(sample_path, tmp_path):
    out = tmp_path / "a.mp4"
    ff.cut_clip(sample_path, out, 1.0, 3.0, "accurate")
    info = probe(out)
    assert 1.7 < info["duration_sec"] < 2.4
    assert info["width"] == 320 and info["height"] == 240


def test_cut_fast(sample_path, tmp_path):
    out = tmp_path / "f.mp4"
    ff.cut_clip(sample_path, out, 1.0, 4.0, "fast")
    assert 2.0 < probe(out)["duration_sec"] < 4.6


def test_progress_callback(sample_path, tmp_path):
    values = []
    ff.cut_clip(sample_path, tmp_path / "p.mp4", 0.0, 3.0, "accurate", values.append)
    assert values and all(0.0 <= v <= 1.0 for v in values)


def test_grab_frame(sample_path, tmp_path):
    out = tmp_path / "t.jpg"
    ff.grab_frame(sample_path, out, 1.0)
    assert out.stat().st_size > 0


# ---------- clips API ----------
def test_export_flow(client, sample_path):
    vid = upload(client, sample_path)
    data = export(client, vid["id"], 1.0, 3.0, title="My Test Clip")
    assert data["clip"]["status"] == "pending"
    job = wait_job(client, data["job_id"])
    assert job["status"] == "completed", job
    assert job["progress"] == 100.0

    clip = client.get(f"/api/clips/{data['clip']['id']}").json()
    assert clip["status"] == "ready"
    assert clip["has_file"] and clip["has_thumbnail"]
    assert 1.7 < clip["duration_sec"] < 2.4
    assert clip["aspect_ratio"] == "4:3"

    s = client.get(f"/api/clips/{clip['id']}/stream")
    assert s.status_code == 200 and len(s.content) > 1000
    d = client.get(f"/api/clips/{clip['id']}/download")
    assert d.status_code == 200 and "attachment" in d.headers["content-disposition"]
    t = client.get(f"/api/clips/{clip['id']}/thumbnail")
    assert t.status_code == 200 and t.headers["content-type"] == "image/jpeg"


def test_fast_mode_export(client, sample_path):
    vid = upload(client, sample_path)
    data = export(client, vid["id"], 1.0, 4.0, mode="fast")
    assert wait_job(client, data["job_id"])["status"] == "completed"
    assert client.get(f"/api/clips/{data['clip']['id']}").json()["status"] == "ready"


def test_invalid_ranges(client, sample_path):
    vid = upload(client, sample_path)
    base = {"video_id": vid["id"], "mode": "accurate"}
    assert client.post("/api/clips", json={**base, "start_sec": 3, "end_sec": 2}).status_code == 400
    assert client.post("/api/clips", json={**base, "start_sec": 1, "end_sec": 1.1}).status_code == 400
    assert client.post("/api/clips", json={**base, "start_sec": 50, "end_sec": 60}).status_code == 400
    assert client.post("/api/clips", json={**base, "start_sec": -1, "end_sec": 2}).status_code == 422
    assert client.post("/api/clips", json={"video_id": 999999, "start_sec": 0, "end_sec": 2}).status_code == 404


def test_audio_only_rejected(client, wav_path):
    vid = upload(client, wav_path, "audio/wav")
    r = client.post("/api/clips", json={"video_id": vid["id"], "start_sec": 0, "end_sec": 1})
    assert r.status_code == 400


def test_list_filter_by_video(client, sample_path):
    vid = upload(client, sample_path)
    data = export(client, vid["id"], 0.0, 2.0)
    wait_job(client, data["job_id"])
    lst = client.get("/api/clips", params={"video_id": vid["id"]}).json()
    assert lst["total"] == 1 and lst["items"][0]["id"] == data["clip"]["id"]


def test_delete_clip_removes_files(client, sample_path):
    vid = upload(client, sample_path)
    before_c, before_t = files_in("generated_clips"), files_in("thumbnails")
    data = export(client, vid["id"], 0.0, 2.0)
    wait_job(client, data["job_id"])
    assert len(files_in("generated_clips")) == len(before_c) + 1
    assert client.delete(f"/api/clips/{data['clip']['id']}").status_code == 200
    assert files_in("generated_clips") == before_c
    assert files_in("thumbnails") == before_t
    assert client.get(f"/api/clips/{data['clip']['id']}").status_code == 404


def test_delete_video_removes_clip_and_proxy_files(client, sample_path):
    before_c, before_p = files_in("generated_clips"), files_in("previews")
    vid = upload(client, sample_path)
    data = export(client, vid["id"], 0.0, 2.0)
    wait_job(client, data["job_id"])
    px = client.post(f"/api/videos/{vid['id']}/proxy").json()
    assert wait_job(client, px["job_id"])["status"] == "completed"
    assert client.delete(f"/api/videos/{vid['id']}").status_code == 200
    assert files_in("generated_clips") == before_c
    assert files_in("previews") == before_p


# ---------- proxy ----------
def test_proxy_flow(client, sample_path):
    vid = upload(client, sample_path)
    assert client.get(f"/api/videos/{vid['id']}/proxy").status_code == 404
    first = client.post(f"/api/videos/{vid['id']}/proxy").json()
    assert first["ready"] is False and first["job_id"]
    assert wait_job(client, first["job_id"])["status"] == "completed"
    r = client.get(f"/api/videos/{vid['id']}/proxy")
    assert r.status_code == 200 and len(r.content) > 1000
    assert client.post(f"/api/videos/{vid['id']}/proxy").json()["ready"] is True


# ---------- jobs ----------
def test_sse_stream_ends_with_completed(client, sample_path):
    vid = upload(client, sample_path)
    data = export(client, vid["id"], 0.0, 2.0)
    events = []
    with client.stream("GET", f"/api/jobs/{data['job_id']}/events") as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    assert events and events[-1]["status"] == "completed"


def test_cancel_rules(client, sample_path):
    vid = upload(client, sample_path)
    data = export(client, vid["id"], 0.0, 2.0)
    wait_job(client, data["job_id"])
    assert client.post(f"/api/jobs/{data['job_id']}/cancel").status_code == 409
    assert client.post("/api/jobs/999999/cancel").status_code == 404
    assert client.get("/api/jobs/999999").status_code == 404


def test_unknown_job_type_fails(client):
    with SessionLocal() as db:
        j = Job(type="nonsense", status="queued")
        db.add(j)
        db.commit()
        jid = j.id
    res = wait_job(client, jid, timeout=20)
    assert res["status"] == "failed" and "Unknown job type" in res["error"]
