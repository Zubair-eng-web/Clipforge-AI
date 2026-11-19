import shutil
import subprocess

import pytest

from backend.reframing.reframe import RATIOS, compute_crop, reframe_video
from backend.video_processing.ffprobe import probe

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_compute_crop_vertical_from_wide():
    cw, ch, x, y = compute_crop(1920, 1080, "9:16")
    assert ch == 1080
    assert abs(cw / ch - 9 / 16) < 0.01
    assert x == (1920 - cw) // 2 and y == 0
    assert cw % 2 == 0 and ch % 2 == 0


def test_compute_crop_follows_face_and_stays_inside():
    cw, ch, x, _ = compute_crop(1920, 1080, "9:16", cx=100, cy=500)
    assert x == 0
    cw, ch, x, _ = compute_crop(1920, 1080, "9:16", cx=1900, cy=500)
    assert x == 1920 - cw


def test_compute_crop_square_and_wide_from_vertical():
    cw, ch, _, _ = compute_crop(1080, 1920, "1:1")
    assert cw == ch == 1080
    cw, ch, _, y = compute_crop(1080, 1920, "16:9", cy=0)
    assert cw == 1080 and y == 0 and abs(cw / ch - 16 / 9) < 0.02


def _make_video(path):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=10:duration=2",
         "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )


@needs_ffmpeg
@pytest.mark.parametrize("ratio,mode", [("9:16", "face"), ("1:1", "center"), ("16:9", "blur"), ("9:16", "blur")])
def test_reframe_output_size(tmp_path, ratio, mode):
    src = tmp_path / "in.mp4"
    dst = tmp_path / "out.mp4"
    _make_video(src)
    used = reframe_video(src, dst, ratio, mode, 2.0, 640, 360)
    info = probe(dst)
    assert (info["width"], info["height"]) == RATIOS[ratio]
    assert used in ("face", "center", "blur")
    assert src.exists()  # original untouched


def test_settings_endpoint_hides_key(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app

    monkeypatch.setenv("GEMINI_API_KEY", "secret-test-key-123")
    r = TestClient(app).get("/api/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["ai"]["gemini_key_set"] is True
    assert "secret-test-key-123" not in r.text
    assert "ffmpeg" in data["tools"] and "folders" in data["storage"]