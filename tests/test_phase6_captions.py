"""Phase 6.1: caption builder (lines, SRT, ASS), burn-in with real FFmpeg, captions API end to end."""
import shutil
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from backend import config
from backend.captions import builder
from backend.captions.burn import burn_captions, has_subtitles_filter

FFMPEG = shutil.which("ffmpeg")
needs_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
TERMINAL = {"completed", "failed", "cancelled"}
WORDS = [{"start": round(0.3 * i, 2), "end": round(0.3 * i + 0.25, 2), "word": w}
         for i, w in enumerate("Hello world this is a small caption test for the clip".split())]


def _ff(args):
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


# ---------------- builder (pure) ----------------
def test_group_words_into_lines():
    lines = builder.build_lines(WORDS)
    assert len(lines) == 2
    for l in lines:
        assert 0 < len(l["text"]) <= 28 and l["end"] > l["start"]
    assert lines[0]["end"] <= lines[1]["start"]
    assert lines[0]["text"].startswith("Hello") and lines[1]["text"].endswith("clip")


def test_long_gap_starts_new_line():
    words = [{"start": 0.0, "end": 0.3, "word": "one"}, {"start": 3.0, "end": 3.3, "word": "two"}]
    assert len(builder.build_lines(words)) == 2


def test_sentence_end_starts_new_line():
    words = [{"start": 0.0, "end": 0.3, "word": "Hi"}, {"start": 0.3, "end": 0.6, "word": "there."},
             {"start": 0.6, "end": 0.9, "word": "Next"}, {"start": 0.9, "end": 1.2, "word": "one"}]
    lines = builder.build_lines(words)
    assert [l["text"] for l in lines] == ["Hi there.", "Next one"]


def test_srt_format():
    srt = builder.to_srt(builder.build_lines(WORDS))
    assert srt.startswith("1\n00:00:00,000 --> ")
    assert "\n2\n" in srt and "Hello world" in srt
    assert builder._srt_time(3661.5) == "01:01:01,500"


def test_ass_plain_and_karaoke():
    lines = builder.build_lines(WORDS)
    plain = builder.to_ass(lines, 1280, 720, "classic")
    assert "PlayResX: 1280" in plain and "Dialogue:" in plain and "\\kf" not in plain
    kara = builder.to_ass(lines, 1280, 720, "highlight")
    assert "\\kf" in kara
    edited = [dict(l, text="Edited text") for l in lines]  # text no longer matches the words
    assert "\\kf" not in builder.to_ass(edited, 1280, 720, "highlight")
    assert builder._ass_time(3661.5) == "1:01:01.50"


def test_ass_escapes_braces_and_positions():
    out = builder.to_ass([{"start": 0, "end": 1, "text": "bad {tag} here"}], 640, 360, "classic", "top")
    assert "{tag}" not in out and "(tag)" in out
    assert ",8," in out  # top alignment


# ---------------- burn-in (real FFmpeg + OpenCV) ----------------
@needs_ffmpeg
def test_burn_renders_visible_text(tmp_path):
    cv2 = pytest.importorskip("cv2")
    if not has_subtitles_filter():
        pytest.skip("This FFmpeg build has no subtitles (libass) filter")
    src = tmp_path / "black.mp4"
    _ff(["-f", "lavfi", "-i", "color=c=black:s=640x360:d=3:r=15", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)])
    ass = tmp_path / "captions.ass"
    ass.write_text(builder.to_ass([{"start": 0.0, "end": 3.0, "text": "HELLO WORLD"}], 640, 360, "bold", "center"),
                   encoding="utf-8")
    dst = tmp_path / "out.mp4"
    seen = []
    burn_captions(src, ass, dst, 3.0, seen.append)
    assert dst.is_file() and all(0.0 <= x <= 1.0 for x in seen)
    frame = tmp_path / "frame.png"
    _ff(["-ss", "1", "-i", str(dst), "-frames:v", "1", str(frame)])
    img = cv2.imread(str(frame))
    assert img is not None
    assert int(img.max()) > 200, "No caption pixels found: libass may be missing a font. Paste this error to the assistant."


@needs_ffmpeg
def test_burn_missing_source_raises(tmp_path):
    from backend.video_processing.ffmpeg_service import FfmpegError
    ass = tmp_path / "captions.ass"
    ass.write_text(builder.to_ass([{"start": 0, "end": 1, "text": "x"}], 320, 240), encoding="utf-8")
    with pytest.raises(FfmpegError):
        burn_captions(tmp_path / "nope.mp4", ass, tmp_path / "o.mp4", 1.0)


# ---------------- real Whisper smoke test ----------------
@needs_ffmpeg
def test_real_word_transcription_runs(tmp_path):
    pytest.importorskip("faster_whisper")
    from backend.audio_processing import transcribe as tr
    from backend.audio_processing.word_transcribe import transcribe_words
    try:
        tr._get_model()
    except Exception as e:
        pytest.skip(f"Whisper model could not be loaded: {str(e)[:120]}")
    p = tmp_path / "tone.mp4"
    _ff(["-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=15", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(p)])
    out = transcribe_words(p, 3.0)
    assert {"language", "words", "model"} <= set(out) and isinstance(out["words"], list)
    assert not list((config.STORAGE_DIR / "temporary").glob("*.wav"))


# ---------------- API end to end ----------------
@pytest.fixture(scope="module")
def client():
    from backend.database import db as dbmod
    if config.STORAGE_DIR.resolve() == (config.ROOT / "storage").resolve() or \
            dbmod.DB_PATH.resolve() == (config.ROOT / "storage" / "clipforge.db").resolve():
        pytest.skip("Tests are not using isolated storage/DB (check tests/conftest.py)")
    from backend.main import app
    with TestClient(app) as c:
        yield c


def _wait_job(client, job_id, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in TERMINAL:
            return j
        time.sleep(0.3)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


@pytest.fixture(scope="module")
def ready_clip(client, tmp_path_factory):
    if FFMPEG is None:
        pytest.skip("ffmpeg is not installed")
    p = tmp_path_factory.mktemp("capsrc") / "cap_src.mp4"
    _ff(["-f", "lavfi", "-i", "color=c=black:s=640x360:d=6:r=15", "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(p)])
    up = client.post("/api/videos/upload", files=[("files", ("cap_src.mp4", p.read_bytes(), "video/mp4"))])
    assert up.status_code == 200, up.text
    vid = up.json()["uploaded"][0]["id"]
    r = client.post("/api/clips", json={"video_id": vid, "start_sec": 0.5, "end_sec": 5.0, "title": "Cap clip", "mode": "accurate"})
    assert r.status_code == 200, r.text
    assert _wait_job(client, r.json()["job_id"])["status"] == "completed"
    return {"video_id": vid, "clip_id": r.json()["clip"]["id"]}


def _fake_words(src, duration, on_progress=None, language=None):
    if on_progress:
        on_progress(1.0)
    return {"language": "en", "duration_sec": 4.5, "model": "fake", "words": WORDS}


def test_validation(client, ready_clip):
    cid = ready_clip["clip_id"]
    assert client.post("/api/clips/999999/captions/generate", json={}).status_code == 404
    assert client.get("/api/clips/999999/captions").status_code == 404
    assert client.get(f"/api/clips/{cid}/captions").status_code == 404          # not generated yet
    assert client.get(f"/api/clips/{cid}/captions.srt").status_code == 404
    assert client.post(f"/api/clips/{cid}/captions/burn", json={}).status_code == 400   # nothing to burn
    assert client.post(f"/api/clips/{cid}/captions/burn", json={"style": "nope"}).status_code == 422


def test_generate_edit_srt_burn_delete(client, ready_clip, monkeypatch):
    from backend.workers import caption_handlers as ch
    monkeypatch.setattr(ch, "transcribe_words", _fake_words)
    cid, vid = ready_clip["clip_id"], ready_clip["video_id"]

    r = client.post(f"/api/clips/{cid}/captions/generate", json={"language": "auto"})
    assert r.status_code == 200, r.text
    assert _wait_job(client, r.json()["job_id"])["status"] == "completed"

    caps = client.get(f"/api/clips/{cid}/captions").json()
    assert caps["language"] == "en" and len(caps["lines"]) == 2
    assert caps["lines"][0]["text"].startswith("Hello") and caps["lines"][0]["has_words"] is True

    # edit one line: its word timing is dropped, the other keeps it
    lines = [{"start": l["start"], "end": l["end"], "text": l["text"]} for l in caps["lines"]]
    lines[0]["text"] = "Edited line"
    assert client.put(f"/api/clips/{cid}/captions", json={"lines": lines}).status_code == 200
    again = client.get(f"/api/clips/{cid}/captions").json()
    assert again["lines"][0]["text"] == "Edited line" and again["lines"][0]["has_words"] is False
    assert again["lines"][1]["has_words"] is True
    bad = [dict(lines[0], end=lines[0]["start"])]
    assert client.put(f"/api/clips/{cid}/captions", json={"lines": bad}).status_code == 422
    assert client.put(f"/api/clips/{cid}/captions", json={"lines": [dict(lines[0], text="   ")]}).status_code == 422

    srt = client.get(f"/api/clips/{cid}/captions.srt")
    assert srt.status_code == 200 and "-->" in srt.text and "Edited line" in srt.text
    assert ".srt" in srt.headers.get("content-disposition", "")

    if not has_subtitles_filter():
        assert client.post(f"/api/clips/{cid}/captions/burn", json={}).status_code == 400
        pytest.skip("This FFmpeg build has no subtitles (libass) filter")

    b = client.post(f"/api/clips/{cid}/captions/burn", json={"style": "highlight", "position": "bottom"})
    assert b.status_code == 200, b.text
    new_id = b.json()["clip_id"]
    assert b.json()["clip"]["status"] == "pending"
    job = _wait_job(client, b.json()["job_id"])
    assert job["status"] == "completed", job

    new = client.get(f"/api/clips/{new_id}").json()
    assert new["status"] == "ready" and new["has_file"] and new["has_thumbnail"]
    assert new["title"].endswith("(captions)") and new["video_id"] == vid
    assert client.get(f"/api/clips/{cid}").json()["status"] == "ready"   # original is untouched

    from sqlalchemy import func, select
    from backend.database.db import SessionLocal
    from backend.database.models import Clip, ClipCaption
    with SessionLocal() as db:
        fp = db.get(Clip, new_id).file_path
    assert fp.startswith("edited_clips/") and (config.STORAGE_DIR / fp).is_file()
    assert client.get(f"/api/clips/{new_id}/stream").status_code == 200

    assert client.delete(f"/api/clips/{new_id}").status_code == 200
    assert not (config.STORAGE_DIR / fp).exists()
    assert client.delete(f"/api/clips/{cid}").status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ClipCaption).where(ClipCaption.clip_id == cid)) == 0
    assert not list((config.STORAGE_DIR / "temporary").glob("*/captions.ass"))   # work folders cleaned up