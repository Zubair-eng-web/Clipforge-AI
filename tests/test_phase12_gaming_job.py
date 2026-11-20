from backend.gaming import pipeline

UNITS = [{"start": 0, "end": 10}, {"start": 10, "end": 20}, {"start": 20, "end": 30}]
CUTS = [0, 10, 20, 30]

def _res(scores, source="gemini"):
    return [{"scores": {"explosions": s}, "desc": "boom", "source": source} for s in scores]

def test_build_scenes_prefix_and_status():
    out = pipeline.build_scenes(UNITS, _res([0, 90, 0]), [{"key": "explosions", "duration": "auto"}], CUTS, {})
    assert len(out) == 1
    s = out[0]
    assert s["category"] == "gta_explosions" and (s["start"], s["end"]) == (10, 20) and s["status"] == "detected"

def test_fixed_duration_window():
    out = pipeline.build_scenes(UNITS, _res([0, 90, 0]), [{"key": "explosions", "duration": 5}], CUTS, {"min_scene_sec": 3})
    assert len(out) == 1 and round(out[0]["end"] - out[0]["start"], 2) == 5.0

def test_local_source_is_uncertain():
    out = pipeline.build_scenes(UNITS, _res([0, 90, 0], "local"), [{"key": "explosions", "duration": "auto"}], CUTS, {})
    assert out and all(s["status"] == "uncertain" for s in out)

def test_too_short_scene_dropped():
    out = pipeline.build_scenes(UNITS, _res([0, 90, 0]), [{"key": "explosions", "duration": "auto"}], CUTS, {"min_scene_sec": 15})
    assert out == []

def test_short_label_gta_and_old():
    from backend.scene_ai.categories import short_label
    assert short_label("gta_explosions") == "Explosions"
    assert short_label("gta_fighting") == "Fist Fight"
    assert short_label("fighting") == "Fighting"

def test_gaming_api_module():
    from backend.api import gaming
    paths = {r.path for r in gaming.router.routes}
    assert "/api/gaming/videos/{video_id}/run" in paths and "/api/gaming/videos/{video_id}/highlights" in paths
    items = gaming.categories()["items"]
    assert len(items) == 26 and items[-1]["key"] == "custom"

def test_handler_registered_and_main_imports():
    import backend.workers.gaming_handlers as h
    assert callable(h.gaming_classify)
    import backend.main  # noqa: F401