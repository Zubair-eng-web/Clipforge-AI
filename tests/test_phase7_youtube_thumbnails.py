import base64
import shutil
import subprocess
import time
from pathlib import Path

import pytest

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _wait_job(client, job_id, timeout=40):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("completed", "failed", "cancelled"):
            return j
        time.sleep(0.3)
    raise AssertionError("job did not finish in time")


def test_youtube_import_needs_confirmation_and_valid_url(client):
    r = client.post("/api/youtube/import", json={"url": "https://example.com/v", "confirm_rights": False})
    assert r.status_code == 400
    r = client.post("/api/youtube/import", json={"url": "ftp://example.com/v", "confirm_rights": True})
    assert r.status_code == 400


def test_youtube_info_maps_errors(client, monkeypatch):
    import backend.api.youtube as api
    from backend.importers.youtube import YoutubeError

    monkeypatch.setattr(api, "fetch_info", lambda url: {"title": "T", "duration": 10.0, "is_live": False})
    ok = client.post("/api/youtube/info", json={"url": "https://example.com/watch?v=1"})
    assert ok.status_code == 200 and ok.json()["title"] == "T"

    def boom(url):
        raise YoutubeError("boom")

    monkeypatch.setattr(api, "fetch_info", boom)
    bad = client.post("/api/youtube/info", json={"url": "https://example.com/watch?v=1"})
    assert bad.status_code == 400 and "boom" in bad.json()["detail"]


@needs_ffmpeg
def test_youtube_import_job_end_to_end(client, tmp_path, monkeypatch):
    src = tmp_path / "src.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=2",
         "-pix_fmt", "yuv420p", str(src)], check=True, capture_output=True)
    import backend.workers.youtube_handlers as yh

    monkeypatch.setattr(yh, "fetch_info", lambda url: {"title": "Fake", "duration": 2.0, "is_live": False})

    def fake_download(url, dest_dir, name, on_progress=None):
        p = Path(dest_dir) / f"{name}.mp4"
        shutil.copy(src, p)
        return p, "Fake Title"

    monkeypatch.setattr(yh, "download_video", fake_download)
    r = client.post("/api/youtube/import", json={"url": "https://example.com/watch?v=abc", "confirm_rights": True})
    assert r.status_code == 200
    job = _wait_job(client, r.json()["job_id"])
    assert job["status"] == "completed", job
    assert job["video_id"]
    v = client.get(f"/api/videos/{job['video_id']}").json()
    assert v["name"].startswith("Fake Title") and v["has_video"]


def test_thumbnail_upload_download_delete(client):
    r = client.post("/api/thumbnails", files={"file": ("t.png", PNG, "image/png")}, data={"title": "My thumb"})
    assert r.status_code == 200
    tid = r.json()["id"]
    assert any(i["id"] == tid for i in client.get("/api/thumbnails").json()["items"])
    f = client.get(f"/api/thumbnails/{tid}/file")
    assert f.status_code == 200 and f.content == PNG
    assert client.delete(f"/api/thumbnails/{tid}").status_code == 200
    assert client.get(f"/api/thumbnails/{tid}/file").status_code == 404


def test_thumbnail_rejects_non_image(client):
    r = client.post("/api/thumbnails", files={"file": ("x.txt", b"hello world", "text/plain")})
    assert r.status_code == 400


def test_frame_unknown_clip_is_404(client):
    assert client.get("/api/clips/999999/frame?t=1").status_code == 404