"""A scenes-only run (Scene Detection page) must work without a transcript and must not
leave the video_analysis row stuck on 'processing'."""
import shutil
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from backend import config

FFMPEG = shutil.which("ffmpeg")
pytestmark = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
TERMINAL = {"completed", "failed", "cancelled"}


@pytest.fixture(scope="module")
def client():
    from backend.database import db as dbmod
    if config.STORAGE_DIR.resolve() == (config.ROOT / "storage").resolve() or \
            dbmod.DB_PATH.resolve() == (config.ROOT / "storage" / "clipforge.db").resolve():
        pytest.skip("Tests are not using isolated storage/DB (check tests/conftest.py)")
    from backend.main import app
    with TestClient(app) as c:
        yield c


def test_scenes_only_run_without_transcript(client, tmp_path):
    pytest.importorskip("scenedetect")
    pytest.importorskip("cv2")
    p = tmp_path / "scenes_only.mp4"
    subprocess.run([
        FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=320x240:d=4:r=15",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=4:r=15",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(p),
    ], check=True)
    up = client.post("/api/videos/upload", files=[("files", ("scenes_only.mp4", p.read_bytes(), "video/mp4"))])
    assert up.status_code == 200, up.text
    vid = up.json()["uploaded"][0]["id"]

    run = client.post(f"/api/analysis/videos/{vid}/run", json={"steps": ["scenes"]})
    assert run.status_code == 200, run.text
    job_id = run.json()["job_id"]
    end = time.time() + 90
    job = {}
    while time.time() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in TERMINAL:
            break
        time.sleep(0.3)
    assert job["status"] == "completed", job

    scenes = client.get(f"/api/analysis/videos/{vid}/scenes").json()
    assert scenes["total"] >= 2
    summary = client.get(f"/api/analysis/videos/{vid}").json()
    assert summary["scene_count"] >= 2 and summary["has_transcript"] is False
    assert client.get(f"/api/videos/{vid}/analysis").json()["status"] == "none"  # not stuck on 'processing'
    assert client.delete(f"/api/videos/{vid}").status_code == 200