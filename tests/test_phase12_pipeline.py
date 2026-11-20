from backend.gaming import pipeline
from backend.scene_ai import engine

UNITS = [{"start": 0, "end": 10}, {"start": 10, "end": 20}, {"start": 20, "end": 30}]
SEGS = [{"start": 11, "end": 15, "text": "explosion boom"}]
PROFILE = [0.05] * 10 + [1.0] * 10 + [0.05] * 10

def fake_classify(units, segments, cats, src, use_vision=True, progress=None):
    out = []
    for i, _ in enumerate(units):
        sc = {c["key"]: 0.0 for c in cats}
        if i == 1 and "explosions" in sc:
            sc["explosions"] = 90.0
        out.append({"scores": sc, "desc": "big explosion" if i == 1 else "", "source": "gemini"})
    return out, {"warnings": []}

def test_two_signals_make_detected_scene(monkeypatch):
    monkeypatch.setattr(engine, "classify", fake_classify)
    res, info = pipeline.score_units(UNITS, SEGS, "x.mp4", selected=["explosions", "scenery"], profile=PROFILE)
    assert res[1]["scores"]["explosions"] >= 55
    assert res[0]["scores"]["explosions"] < 30 and res[2]["scores"]["explosions"] < 30
    segs = engine.find_segments(UNITS, res, "explosions", 55)
    assert len(segs) == 1 and (segs[0]["start"], segs[0]["end"]) == (10, 20)
    assert segs[0]["status"] == "detected"

def test_vision_only_stays_uncertain(monkeypatch):
    monkeypatch.setattr(engine, "classify", fake_classify)
    res, _ = pipeline.score_units(UNITS, [], "x.mp4", selected=["explosions"], profile=[])
    assert res[1]["scores"]["explosions"] <= 49
    segs = engine.find_segments(UNITS, res, "explosions", 55)
    assert all(s["status"] == "uncertain" for s in segs)

def test_without_gemini_source_is_local(monkeypatch):
    def local(units, segments, cats, src, use_vision=True, progress=None):
        return [{"scores": {c["key"]: 0.0 for c in cats}, "desc": "", "source": "local"} for _ in units], {"warnings": []}
    monkeypatch.setattr(engine, "classify", local)
    res, _ = pipeline.score_units(UNITS, SEGS, "x.mp4", selected=["explosions"], profile=PROFILE)
    assert all(r["source"] == "local" for r in res)
    segs = engine.find_segments(UNITS, res, "explosions", 55)
    assert all(s["status"] == "uncertain" for s in segs)