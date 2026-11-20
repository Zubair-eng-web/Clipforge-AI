"""Gaming pipeline (pure, no DB): units -> Gemini vision (engine.classify) + audio energy + transcript
-> multi-signal scores per unit. Output has the same shape as engine.classify, so
engine.find_segments / fit_window / snap_range can be reused unchanged."""
import math

from backend.scene_ai import engine
from .categories import get_categories
from .signals import audio_energy_profile, summarize_audio
from .scoring import classify_unit


def _cats_for_ai(selected, custom_label):
    out = []
    for c in get_categories(custom_label):
        if selected and c["id"] not in selected:
            continue
        out.append({"key": c["id"], "rule": c["hint"] or c["label"], "label": c["label"],
                    "custom_text": custom_label or ""})
    return out


def score_units(units, segments, src, selected=None, custom_label=None, use_vision=True,
                progress=None, profile=None):
    """Returns (results, info). results[i] = {scores: {category_id: 0-100}, desc, source, signals}.
    source = 'gemini' only when real vision scores exist for that unit, otherwise 'local'
    (then the scene can only be 'uncertain')."""
    cats = _cats_for_ai(selected, custom_label)
    keys = [c["key"] for c in cats]
    vis, info = engine.classify(units, segments, cats, src, use_vision=use_vision, progress=progress)
    if profile is None:
        profile = audio_energy_profile(src)
    info["audio_available"] = bool(profile)
    if not profile:
        info.setdefault("warnings", []).append("No audio signal found: scoring uses frames and speech only")
    results = []
    for u, v in zip(units, vis):
        a, b = int(u["start"]), max(int(math.ceil(u["end"])), int(u["start"]) + 1)
        stats = summarize_audio(profile[a:b])
        has_vision = v.get("source") == "gemini"
        res = classify_unit(engine.unit_text(segments, u, limit=500),
                            [v.get("desc", "")] if v.get("desc") else [],
                            stats, v["scores"] if has_vision else None, custom_label)
        results.append({"scores": {k: res[k]["score"] if k in res else 0.0 for k in keys},
                        "desc": v.get("desc", ""),
                        "source": "gemini" if has_vision else "local",
                        "signals": {k: res[k]["signals"] for k in keys if k in res}})
    return results, info
def build_scenes(units, results, cat_req, cuts, o):
    """Pure: turn per-unit scores into scenes. DB category = 'gta_' + gaming id (no clash with scene_ai)."""
    thr = float(o.get("confidence", 55))
    min_sec = float(o.get("min_scene_sec", 8))
    max_sec = float(o.get("max_scene_sec", 0) or 0)
    out = []
    for c in cat_req:
        key = c["key"]
        fixed = None if c.get("duration") in (None, "auto") else float(c["duration"])
        sc_list = [r["scores"].get(key, 0.0) for r in results]
        for seg in engine.find_segments(units, results, key, thr, bool(o.get("merge", True))):
            full0, full1 = seg["start"], seg["end"]
            st, en = full0, full1
            limits = [x for x in (fixed, max_sec) if x and x > 0]
            limit = min(limits) if limits else None
            if limit and en - st > limit + 0.01:
                st, en = engine.fit_window(units, sc_list, seg["unit_idx"], limit)
                if o.get("complete_boundaries", True):
                    st, en = engine.snap_range(st, en, cuts, full0, full1)
            if en - st < min_sec:
                continue
            out.append({**seg, "category": "gta_" + key, "start": st, "end": en, "full0": full0, "full1": full1})
    return out