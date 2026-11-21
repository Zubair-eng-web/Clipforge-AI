import json
import shutil
import subprocess

import pytest

from backend.reels.engine import build_reel, has_audio

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg/ffprobe not installed")


def _make_video(path, secs=10, audio=True):
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=1280x720:rate=25:duration={secs}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}", "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True)


def _info(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height:format=duration",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    v = [s for s in d["streams"] if s["codec_type"] == "video"][0]
    a = [s for s in d["streams"] if s["codec_type"] == "audio"]
    return v, a, float(d["format"]["duration"])


@needs_ffmpeg
def test_intro_and_outro_added(tmp_path):
    src, dst = tmp_path / "s.mp4", tmp_path / "r.mp4"
    _make_video(src)
    before = src.stat().st_size
    res = build_reel(src, dst, src_duration=10, w=1280, h=720, ratio="9:16", size="720", mode="center",
                     start=1, end=5, intro={"text": "My Channel", "seconds": 2, "bg": "#112233", "fg": "#ffffff"},
                     outro={"text": "Follow for more", "seconds": 2})
    v, a, dur = _info(dst)
    assert (v["width"], v["height"]) == (720, 1280)
    assert 7.3 <= dur <= 8.8 and a
    assert abs(res["duration"] - 8) < 0.1 and res["intro"] and res["outro"]
    assert src.stat().st_size == before
    assert not list(tmp_path.glob("*_pre.mp4")) and not list(tmp_path.glob("*_cards.mp4"))


@needs_ffmpeg
def test_only_outro_and_silent_source(tmp_path):
    src, dst = tmp_path / "s.mp4", tmp_path / "r.mp4"
    _make_video(src, 6, audio=False)
    build_reel(src, dst, src_duration=6, w=1280, h=720, ratio="1:1", size="720", mode="center",
               start=0, end=4, outro={"text": "Thanks", "seconds": 1})
    v, a, dur = _info(dst)
    assert (v["width"], v["height"]) == (720, 720)
    assert 4.6 <= dur <= 5.6 and a


@needs_ffmpeg
def test_cards_with_music(tmp_path):
    src, wav, dst = tmp_path / "s.mp4", tmp_path / "m.wav", tmp_path / "r.mp4"
    _make_video(src)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=330:duration=30", str(wav)], check=True)
    track = {"path": str(wav), "tdur": 30.0, "volume": 0.5, "start": 0.0, "trim_in": 0.0, "trim_out": 0.0,
             "fade_in": 0.5, "fade_out": 0.5, "loop": True}
    build_reel(src, dst, src_duration=10, w=1280, h=720, ratio="9:16", size="720", mode="center",
               start=0, end=4, music=[track], intro={"text": "Intro", "seconds": 1}, outro={"text": "Outro", "seconds": 1})
    v, a, dur = _info(dst)
    assert v["codec_name"] == "h264" and a and has_audio(dst)
    assert 5.4 <= dur <= 6.6


def test_card_validation():
    from pydantic import ValidationError
    from backend.api.reels_studio import ReelBody
    ok = ReelBody(clip_id=1, intro={"text": "Hi", "seconds": 3, "bg": "#000000", "fg": "#ffffff"})
    assert ok.intro.seconds == 3
    for bad in ({"text": "Hi", "seconds": 9}, {"text": "", "seconds": 2}, {"text": "Hi", "seconds": 2, "bg": "red"}):
        with pytest.raises(ValidationError):
            ReelBody(clip_id=1, outro=bad)
