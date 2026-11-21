import json
import shutil
import subprocess
import time

import pytest

from backend.editor.ops import has_audio
from backend.editor.timeline import build_timeline

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg/ffprobe not installed")


def _make(path, secs=6, audio=True, size="640x360"):
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=25:duration={secs}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}", "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True)


def _info(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    v = [s for s in d["streams"] if s["codec_type"] == "video"][0]
    return v, float(d["format"]["duration"])


@needs_ffmpeg
def test_split_pieces_with_fade(tmp_path):
    a, dst = tmp_path / "a.mp4", tmp_path / "o.mp4"
    _make(a, 8)
    before = a.stat().st_size
    segs = [{"path": a, "start": 0, "end": 3}, {"path": a, "start": 3, "end": 6}, {"path": a, "start": 6, "end": 8}]
    total = build_timeline(segs, dst, 640, 360, "fade", 0.5)
    v, dur = _info(dst)
    assert abs(total - 7.0) < 1e-6 and abs(dur - 7.0) < 0.5
    assert (v["width"], v["height"]) == (640, 360) and has_audio(dst)
    assert a.stat().st_size == before


@needs_ffmpeg
def test_no_transition_mixed_audio_and_ratio(tmp_path):
    a, b, dst = tmp_path / "a.mp4", tmp_path / "b.mp4", tmp_path / "o.mp4"
    _make(a, 3)
    _make(b, 2, audio=False)
    total = build_timeline([{"path": a, "start": 0, "end": 3}, {"path": b, "start": 0.5, "end": 2}],
                           dst, 720, 1280, "none")
    v, dur = _info(dst)
    assert abs(total - 4.5) < 1e-6 and abs(dur - 4.5) < 0.5
    assert (v["width"], v["height"]) == (720, 1280) and has_audio(dst)


@needs_ffmpeg
def test_single_segment_and_silent_with_transition(tmp_path):
    a, b, d1, d2 = tmp_path / "a.mp4", tmp_path / "b.mp4", tmp_path / "o1.mp4", tmp_path / "o2.mp4"
    _make(a, 4)
    _make(b, 4, audio=False)
    assert abs(build_timeline([{"path": a, "start": 1, "end": 3}], d1, 640, 360) - 2.0) < 1e-6
    assert abs(_info(d1)[1] - 2.0) < 0.5
    total = build_timeline([{"path": b, "start": 0, "end": 2}, {"path": b, "start": 2, "end": 4}],
                           d2, 640, 360, "dissolve", 0.5)
    assert abs(total - 3.5) < 1e-6 and has_audio(d2)


def test_validation(tmp_path):
    seg = {"path": tmp_path / "x.mp4", "start": 0, "end": 2}
    with pytest.raises(ValueError):
        build_timeline([seg, seg], tmp_path / "o.mp4", 640, 360, "fade", 1.5)
    with pytest.raises(ValueError):
        build_timeline([seg], tmp_path / "o.mp4", 640, 360, "nope")
    with pytest.raises(ValueError):
        build_timeline([{"path": seg["path"], "start": 0, "end": 0.1}], tmp_path / "o.mp4", 640, 360)


def _wait(client, jid, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("completed", "failed", "cancelled"):
            return j
        time.sleep(0.3)
    raise AssertionError("job did not finish")


def _ready_clip(client, tmp_path, name, secs):
    src = tmp_path / f"{name}.mp4"
    _make(src, secs)
    up = client.post("/api/videos/upload", files={"files": (f"{name}.mp4", src.read_bytes(), "video/mp4")})
    vid = up.json()["uploaded"][0]["id"]
    r = client.post("/api/clips", json={"video_id": vid, "start_sec": 0, "end_sec": secs, "title": name, "mode": "accurate"})
    assert _wait(client, r.json()["job_id"])["status"] == "completed"
    return r.json()["clip"]["id"]


@needs_ffmpeg
def test_timeline_and_split_api(client, tmp_path):
    c1 = _ready_clip(client, tmp_path, "one", 4)
    c2 = _ready_clip(client, tmp_path, "two", 3)

    bad = client.post("/api/editor/timeline", json={"segments": [{"clip_id": c1, "start": 0, "end": 99}]})
    assert bad.status_code == 400
    assert client.post("/api/editor/timeline", json={"segments": [{"clip_id": c1}, {"clip_id": c2}],
                                                     "transition": "fade", "transition_sec": 2.0}).status_code == 400
    assert client.post("/api/editor/timeline", json={"segments": [{"clip_id": c1}], "transition": "bogus"}).status_code == 422
    assert client.post("/api/editor/timeline", json={"segments": [{"clip_id": 999999}]}).status_code == 404

    r = client.post("/api/editor/timeline", json={"segments": [{"clip_id": c1, "start": 0, "end": 2},
                                                               {"clip_id": c2}], "transition": "fade",
                                                  "transition_sec": 0.5})
    assert r.status_code == 200, r.text
    assert _wait(client, r.json()["job_id"])["status"] == "completed"
    out = client.get(f"/api/clips/{r.json()['clip_id']}").json()
    assert out["status"] == "ready" and abs(out["duration_sec"] - 4.5) < 0.6

    assert client.post("/api/editor/split", json={"clip_id": c1, "at": 0.1}).status_code == 400
    s = client.post("/api/editor/split", json={"clip_id": c1, "at": 1.5})
    assert s.status_code == 200, s.text
    for jid in s.json()["job_ids"]:
        assert _wait(client, jid)["status"] == "completed"
    p1, p2 = [client.get(f"/api/clips/{i}").json() for i in s.json()["clip_ids"]]
    assert p1["status"] == p2["status"] == "ready"
    assert abs(p1["duration_sec"] - 1.5) < 0.5 and abs(p2["duration_sec"] - 2.5) < 0.5
