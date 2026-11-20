import re

PATTERN = r"(?m)^\s*[A-Z.]+\s+subtitles\s"


def test_filter_regex_matches_old_and_new_ffmpeg_format():
    old_fmt = " T.C subtitles         V->V       Render text subtitles."
    new_fmt = " .. subtitles         V->V       Render text subtitles."
    other = " .. ass               V->V       Render ASS subtitles."
    assert re.search(PATTERN, old_fmt)
    assert re.search(PATTERN, new_fmt)
    assert not re.search(PATTERN, other)


def test_burn_module_uses_flexible_pattern():
    from pathlib import Path
    src = Path("backend/captions/burn.py").read_text(encoding="utf-8")
    assert "[A-Z.]+" in src and "[A-Z.]{3}" not in src


def test_real_ffmpeg_detected():
    import shutil
    import pytest
    if not shutil.which("ffmpeg"):
        pytest.skip("no ffmpeg")
    from backend.captions.burn import has_subtitles_filter
    assert has_subtitles_filter() is True