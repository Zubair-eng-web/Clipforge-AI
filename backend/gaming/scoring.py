"""Multi-signal scoring: vision (Gemini frames) + audio energy + transcript. Never one signal alone.
Rules: police chase vs car chase, fight vs gunfight."""
from .categories import get_categories

WEIGHTS = {"vision": 0.5, "audio": 0.25, "text": 0.25}
DETECTED_MIN = 55
POLICE_CUES = ("police", "cop", "siren", "wanted", "officer", "patrol", "swat")
GUN_CUES = ("gun", "shoot", "pistol", "rifle", "shotgun", "firing", "bullet", "ammo", "muzzle", "weapon", "sniper")

def text_score(text, keywords):
    if not text or not text.strip():
        return None  # no speech = no text signal (never fake)
    t = text.lower()
    hits = sum(1 for k in keywords if k in t)
    return float(min(100, hits * 35))

def audio_score(stats, mode):
    if not stats or not stats.get("available") or mode == "any":
        return None
    mean, peak = stats["mean"], stats["peak"]
    if mode == "high":
        return 100.0 * (0.6 * mean + 0.4 * peak)
    return max(0.0, 100.0 * (1.0 - abs(mean - 0.4) * 1.5))  # mid

def combine(vision, audio, text):
    parts = {k: v for k, v in (("vision", vision), ("audio", audio), ("text", text)) if v is not None}
    if not parts:
        return 0.0, []
    tw = sum(WEIGHTS[k] for k in parts)
    score = sum(WEIGHTS[k] * v for k, v in parts.items()) / tw
    positive = [k for k, v in parts.items() if v >= 40]
    return score, positive

def _has(blob, cues):
    return any(c in blob for c in cues)

def apply_rules(res, blob):
    police = _has(blob, POLICE_CUES)
    gun = _has(blob, GUN_CUES)
    if "police_chase" in res and "car_chase" in res:
        if police:
            res["police_chase"]["score"] = min(100.0, res["police_chase"]["score"] + 15)
            res["car_chase"]["score"] *= 0.6
        else:
            res["police_chase"]["score"] = min(res["police_chase"]["score"], 40.0)
    if "fighting" in res and "shooting" in res:
        if gun:
            res["shooting"]["score"] = min(100.0, res["shooting"]["score"] + 10)
            res["fighting"]["score"] *= 0.5
        else:
            res["shooting"]["score"] = min(res["shooting"]["score"], 45.0)

def classify_unit(text="", tags=None, audio_stats=None, vision_scores=None, custom_label=None):
    """text: transcript of the unit. tags: cue words from vision (e.g. ['police car','gun']).
    audio_stats: summarize_audio() result. vision_scores: {category_id: 0-100} from Gemini (optional).
    Returns {category_id: {category, score, confidence, signals, status}}."""
    tags = tags or []
    vision_scores = vision_scores or {}
    blob = (text or "").lower() + " " + " ".join(str(t).lower() for t in tags)
    res = {}
    for c in get_categories(custom_label):
        v = vision_scores.get(c["id"])
        a = audio_score(audio_stats, c["audio"])
        t = text_score(text, c["keywords"])
        score, positive = combine(v, a, t)
        res[c["id"]] = {"category": c["id"], "score": score, "signals": positive}
    apply_rules(res, blob)
    for r in res.values():
        if len(r["signals"]) < 2:
            r["score"] = min(r["score"], 49.0)  # one signal alone is never enough
        r["score"] = round(r["score"], 1)
        r["confidence"] = r["score"]
        if r["score"] >= DETECTED_MIN and len(r["signals"]) >= 2:
            r["status"] = "detected"
        elif r["score"] >= 25:
            r["status"] = "uncertain"
        else:
            r["status"] = "none"
    return res

def best_categories(results, top=3):
    items = [r for r in results.values() if r["status"] != "none"]
    return sorted(items, key=lambda r: r["score"], reverse=True)[:top]