import importlib.util
from pathlib import Path


def _load():
    p = Path(__file__).resolve().parents[1] / "scripts" / "benchmark.py"
    spec = importlib.util.spec_from_file_location("benchmark_script", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_realtime_factor():
    m = _load()
    assert m.realtime_factor(120, 60) == 2.0
    assert m.realtime_factor(120, 0) is None
    assert m.realtime_factor(0, 10) is None


def test_rss_of_nothing_is_zero():
    assert _load().rss_mb({}) == 0.0


def test_report_text():
    m = _load()
    res = {"when": "2026-11-21 10:00", "video": {"id": 1, "name": "demo.mp4", "duration": 120.0},
           "ram_total_gb": 8.0, "min_avail_gb": 1.2, "whisper": "base", "low_memory": True, "frame_width": 256,
           "gemini": False, "peak_mb": 1500.0, "found": True,
           "steps": [{"name": "1 Whisper transcript", "status": "completed", "seconds": 60.0, "peak_mb": 1400.0, "error": None},
                     {"name": "2 Scene detection", "status": "failed", "seconds": 5.0, "peak_mb": 900.0, "error": "boom"}]}
    t = m.fmt_report(res)
    assert "demo.mp4" in t and "low-memory mode: ON" in t and "| 1 Whisper transcript | completed | 60.0 | 2.0 | 1400 |" in t
    assert "Errors:" in t and "boom" in t