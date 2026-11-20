import json
import shutil
import subprocess

import pytest

from backend.reels.engine import build_reel, choose_window, has_audio
from backend.reels.presets import PLATFORMS, check_target

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg/ffprobe not installed")


def _make_video(path, secs=20):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=1280x720:rate=25:duration={secs}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={secs}", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)], check=True)


def _make_wav(path, secs=30):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=330:duration={secs}",
                    str(path)], check=True)


def _info(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,codec_name,width,height:format=duration", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    v = [s for s in d["streams"] if s["codec_type"] == "video"][0]
    a = [s for s in d["streams"] if s["codec_type"] == "audio"]
    return v, a, float(d["format"]["duration"])


def test_choose_window_picks_loudest_part():
    en = [0.01] * 10 + [0.5] * 10 + [0.01] * 10
    assert choose_window(30, en, 10, trim_dead=False) == (10.0, 20.0)


def test_choose_window_trims_dead_time():
    en = [0.0, 0.0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.0, 0.0]
    assert choose_window(10, en, None, True) == (2.0, 8.0)


def test_choose_window_without_audio_uses_start():
    assert choose_window(30, None, 10, True) == (0.0, 10.0)


def test_platform_limits():
    assert check_target("youtube_shorts", 60)[0] is True
    assert check_target("instagram_reels", 1000)[0] is False
    assert check_target("nope", 10)[0] is False
    assert "tiktok" in PLATFORMS


@needs_ffmpeg
def test_reel_916_center_and_source_untouched(tmp_path):
    src, dst = tmp_path / "src.mp4", tmp_path / "reel.mp4"
    _make_video(src)
    before = src.stat().st_size
    res = build_reel(src, dst, src_duration=20, w=1280, h=720, ratio="9:16", size="720", mode="center", target_sec=8)
    v, a, dur = _info(dst)
    assert (v["width"], v["height"]) == (720, 1280)
    assert 6.5 <= dur <= 8.6 and a
    assert abs(res["duration"] - 8) < 1.6
    assert src.stat().st_size == before


@needs_ffmpeg
def test_reel_blur_square_and_manual(tmp_path):
    src = tmp_path / "src.mp4"
    _make_video(src, 10)
    d1, d2 = tmp_path / "blur.mp4", tmp_path / "manual.mp4"
    build_reel(src, d1, src_duration=10, w=1280, h=720, ratio="1:1", size="720", mode="blur", target_sec=5)
    v, _a, _d = _info(d1)
    assert (v["width"], v["height"]) == (720, 720)
    build_reel(src, d2, src_duration=10, w=1280, h=720, ratio="9:16", size="720", mode="manual", cx=0.1, cy=0.5,
               start=1, end=5, brightness=0.1, contrast=1.1)
    v, _a, dur = _info(d2)
    assert (v["width"], v["height"]) == (720, 1280)
    assert 3.4 <= dur <= 4.6


@needs_ffmpeg
def test_reel_face_mode_falls_back_and_works(tmp_path):
    src, dst = tmp_path / "src.mp4", tmp_path / "face.mp4"
    _make_video(src, 6)
    res = build_reel(src, dst, src_duration=6, w=1280, h=720, ratio="9:16", size="720", mode="face")
    assert res["mode_used"] in ("face", "center")
    v, _a, _d = _info(dst)
    assert (v["width"], v["height"]) == (720, 1280)


@needs_ffmpeg
def test_reel_with_music_keeps_h264_and_length(tmp_path):
    src, wav, dst = tmp_path / "src.mp4", tmp_path / "m.wav", tmp_path / "mix.mp4"
    _make_video(src, 12)
    _make_wav(wav, 30)
    track = {"path": str(wav), "tdur": 30.0, "volume": 0.5, "start": 0.0, "trim_in": 0.0, "trim_out": 0.0,
             "fade_in": 0.5, "fade_out": 0.5, "loop": True}
    res = build_reel(src, dst, src_duration=12, w=1280, h=720, ratio="9:16", size="720", mode="center",
                     target_sec=6, music=[track])
    v, a, dur = _info(dst)
    assert v["codec_name"] == "h264" and a and has_audio(dst)
    assert res["music"] is True
    assert 5.0 <= dur <= 6.8
    assert not list(tmp_path.glob("*_pre.mp4"))