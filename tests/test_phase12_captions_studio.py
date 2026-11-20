import re
import subprocess

import pytest

from backend.captions.burn import has_subtitles_filter
from backend.captions.presets import PRESETS, HEX, list_presets, regroup, resolve, to_ass_studio, to_vtt
from backend.video_processing.ffmpeg_service import _NO_WINDOW, _exe

WORDS = [{"start": 0.0, "end": 0.4, "word": "Hello"}, {"start": 0.4, "end": 0.8, "word": "big"},
         {"start": 0.8, "end": 1.2, "word": "world"}, {"start": 1.2, "end": 1.6, "word": "today"}]
LINE = {"start": 0.0, "end": 1.6, "text": "Hello big world today", "words": WORDS}


def _dialogues(ass):
    return [l for l in ass.splitlines() if l.startswith("Dialogue:")]


def test_eight_presets():
    assert set(PRESETS) == {"gaming", "viral_reels", "cinematic", "bold_highlight", "minimal", "word_by_word", "karaoke", "custom"}
    assert len(list_presets()) == 8


def test_resolve_sanitizes():
    c = resolve("gaming", {"font": "Ar,ial\n", "outline": 999, "primary": "red", "position": "nowhere", "words_per_line": "x"})
    assert "," not in c["font"] and "\n" not in c["font"]
    assert c["outline"] <= 12
    assert HEX.match(c["primary"])
    assert c["position"] in ("bottom", "center", "top")


def test_karaoke_uses_kf():
    ass = to_ass_studio([LINE], 720, 1280, {"preset": "karaoke"})
    assert "\\kf" in ass


def test_word_mode_one_event_per_word():
    ass = to_ass_studio([LINE], 720, 1280, {"preset": "word_by_word"})
    assert len(_dialogues(ass)) == 4


def test_overlay_and_empty_lines():
    ass = to_ass_studio([], 720, 1280, {"preset": "minimal", "overlays": [{"text": "BOSS FIGHT", "start": 1, "end": 3, "position": "top"}]})
    d = _dialogues(ass)
    assert len(d) == 1 and d[0].startswith("Dialogue: 1,") and "BOSS FIGHT" in d[0] and "\\an8" in d[0]


def test_offset_shifts_time():
    ass = to_ass_studio([LINE], 720, 1280, {"preset": "minimal", "config": {"offset": 1}})
    assert re.search(r"Dialogue: 0,0:00:01\.00,", ass)


def test_style_uses_preset_font_and_colour():
    ass = to_ass_studio([LINE], 720, 1280, {"preset": "gaming"})
    style = [l for l in ass.splitlines() if l.startswith("Style:")][0]
    assert "Impact" in style and "&H0066FF00" in style  # #00FF66 -> BGR


def test_regroup_splits_words():
    assert len(regroup([LINE], 2)) == 2


def test_vtt():
    v = to_vtt([LINE])
    assert v.startswith("WEBVTT") and "00:00:00.000 --> 00:00:01.600" in v


def test_api_routes_and_handler_patch():
    from backend.api import captions as capapi
    paths = {r.path for r in capapi.router.routes}
    assert any(p.endswith("/captions/studio-burn") for p in paths)
    assert any(p.endswith("/captions/studio-preview") for p in paths)
    assert any(p.endswith("/captions.vtt") for p in paths)
    import backend.workers.caption_handlers as ch
    import inspect
    assert 'ctx.payload.get("studio")' in inspect.getsource(ch)


@pytest.mark.skipif(not has_subtitles_filter(), reason="FFmpeg has no libass")
def test_preview_frame_is_real_jpeg(tmp_path):
    from backend.captions.preview import render_preview
    src = tmp_path / "v.mp4"
    subprocess.run([_exe(), "-hide_banner", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=2:r=10",
                    "-pix_fmt", "yuv420p", str(src)], check=True, capture_output=True, creationflags=_NO_WINDOW)
    ass = to_ass_studio([LINE], 320, 240, {"preset": "gaming"})
    jpg = render_preview(src, ass, 0.5, 320)
    assert jpg[:2] == b"\xff\xd8" and len(jpg) > 500