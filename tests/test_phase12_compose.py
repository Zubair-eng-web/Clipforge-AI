import json
import shutil
import subprocess
import time

import pytest

from backend.captions.burn import has_subtitles_filter
from backend.editor.ops import has_audio

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg/ffprobe not installed")


def _make(path, secs=5):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=25:duration={secs}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}", "-c:a", "aac", "-shortest",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)


def _wait(client, jid, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("completed", "failed", "cancelled"):
            return j
        time.sleep(0.3)
    raise AssertionError("job did not finish")


def _clip(client, tmp_path, secs=5):
    src = tmp_path / "src.mp4"
    _make(src, secs)
    up = client.post("/api/videos/upload", files={"files": ("src.mp4", src.read_bytes(), "video/mp4")})
    vid = up.json()["uploaded"][0]["id"]
    r = client.post("/api/clips", json={"video_id": vid, "start_sec": 0, "end_sec": secs, "title": "base", "mode": "accurate"})
    assert _wait(client, r.json()["job_id"])["status"] == "completed"
    return r.json()["clip"]["id"]


def _track(client, tmp_path):
    wav = tmp_path / "m.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=330:duration=20", str(wav)], check=True)
    r = client.post("/api/music/upload", files={"files": ("m.wav", wav.read_bytes(), "audio/wav")})
    return r.json()["uploaded"][0]["id"]


def _download(client, cid, path):
    path.write_bytes(client.get(f"/api/clips/{cid}/stream").content)
    return path


@needs_ffmpeg
def test_compose_validation(client, tmp_path):
    cid = _clip(client, tmp_path)
    assert client.post("/api/editor/compose", json={"clip_id": cid}).status_code == 400
    assert client.post("/api/editor/compose", json={"clip_id": 999999, "overlays": [{"text": "x", "start": 0, "end": 1}]}).status_code == 404
    assert client.post("/api/editor/compose", json={"clip_id": cid, "music": [{"track_id": 999999}]}).status_code == 404
    assert client.post("/api/editor/compose", json={"clip_id": cid, "overlays": [{"text": "x", "start": 2, "end": 1}]}).status_code == 400
    assert client.post("/api/editor/compose", json={"clip_id": cid, "overlays": [{"text": "x", "start": 99, "end": 100}]}).status_code == 400
    assert client.post("/api/editor/compose", json={"clip_id": cid, "overlays": [{"text": "", "start": 0, "end": 1}]}).status_code == 422
    assert client.post("/api/editor/compose", json={"clip_id": cid, "overlays": [{"text": "x", "start": 0, "end": 1}],
                                                    "style": {"primary": "red"}}).status_code == 422


@needs_ffmpeg
@pytest.mark.skipif(not has_subtitles_filter(), reason="no libass")
def test_overlay_only_changes_picture(client, tmp_path):
    cid = _clip(client, tmp_path)
    r = client.post("/api/editor/compose", json={
        "clip_id": cid, "overlays": [{"text": "BOSS FIGHT", "start": 0, "end": 3, "position": "center"}],
        "style": {"primary": "#FFE600", "uppercase": True, "animation": "fade"}})
    assert r.status_code == 200, r.text
    assert _wait(client, r.json()["job_id"])["status"] == "completed"
    new = r.json()["clip_id"]
    out = client.get(f"/api/clips/{new}").json()
    assert out["status"] == "ready" and abs(out["duration_sec"] - 5.0) < 0.6
    a = client.get(f"/api/clips/{cid}/frame?t=1").content
    b = client.get(f"/api/clips/{new}/frame?t=1").content
    assert a and b and a != b
    assert has_audio(_download(client, new, tmp_path / "o.mp4"))


@needs_ffmpeg
@pytest.mark.skipif(not has_subtitles_filter(), reason="no libass")
def test_overlay_plus_two_music_tracks(client, tmp_path):
    cid = _clip(client, tmp_path)
    t1, t2 = _track(client, tmp_path), _track(client, tmp_path)
    r = client.post("/api/editor/compose", json={
        "clip_id": cid, "overlays": [{"text": "Hello", "start": 1, "end": 4, "position": "top"}],
        "music": [{"track_id": t1, "volume": 40, "fade_in": 0.5, "loop": True},
                  {"track_id": t2, "volume": 30, "start_sec": 1.0, "trim_in": 2, "trim_out": 6}],
        "original_volume": 60})
    assert r.status_code == 200, r.text
    assert _wait(client, r.json()["job_id"])["status"] == "completed"
    out = client.get(f"/api/clips/{r.json()['clip_id']}").json()
    assert out["status"] == "ready" and abs(out["duration_sec"] - 5.0) < 0.6
    assert has_audio(_download(client, r.json()["clip_id"], tmp_path / "o2.mp4"))


@needs_ffmpeg
def test_music_only_original_off(client, tmp_path):
    cid = _clip(client, tmp_path)
    t1 = _track(client, tmp_path)
    r = client.post("/api/editor/compose", json={"clip_id": cid, "music": [{"track_id": t1, "volume": 70}],
                                                 "original_on": False})
    assert r.status_code == 200, r.text
    assert _wait(client, r.json()["job_id"])["status"] == "completed"
    out = client.get(f"/api/clips/{r.json()['clip_id']}").json()
    assert out["status"] == "ready"
