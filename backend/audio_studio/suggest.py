"""Music suggestions from the LOCAL library only. Gemini gets track names/tags as text (it cannot hear audio).
Nothing is downloaded and nothing is applied: the user approves every track."""
import json
import re

from backend.ai import gemini_client

MOODS = {
    "fighting": ["fight", "battle", "epic", "intense", "action", "cinematic", "drum", "war", "power", "combat", "boss", "trailer"],
    "action": ["action", "epic", "intense", "cinematic", "drum", "chase", "power", "trailer", "energy", "rock"],
    "romantic": ["love", "romantic", "soft", "piano", "heart", "ballad", "slow", "tender", "wedding", "pyar", "mohabbat"],
    "comedy": ["fun", "funny", "playful", "happy", "upbeat", "quirky", "comic", "cheerful", "ukulele", "bouncy"],
    "horror": ["horror", "scary", "dark", "suspense", "eerie", "ambient", "creepy", "tension", "haunt", "drone"],
    "suspense": ["suspense", "tension", "thriller", "dark", "ambient", "mystery", "drone", "eerie"],
    "emotional": ["sad", "emotional", "piano", "violin", "sorrow", "cry", "melancholy", "strings", "tears", "slow"],
    "crying": ["sad", "emotional", "piano", "violin", "sorrow", "melancholy", "strings", "tears"],
    "dramatic": ["dramatic", "orchestral", "cinematic", "epic", "strings", "tension"],
    "adventure": ["adventure", "epic", "journey", "orchestral", "cinematic", "uplifting"],
    "motivational": ["motivational", "inspiring", "uplifting", "epic", "success", "power", "energetic"],
    "dancing": ["dance", "beat", "party", "upbeat", "club", "groove", "edm"],
    "singing": ["song", "melody", "vocal", "acoustic", "pop"],
    "friendship": ["friend", "happy", "warm", "acoustic", "upbeat", "fun"],
    "family": ["family", "warm", "soft", "piano", "acoustic", "tender"],
    "angry": ["angry", "intense", "rock", "metal", "dark", "drum"],
    "surprise": ["surprise", "sting", "hit", "tension", "dramatic"],
    "educational": ["calm", "ambient", "soft", "light", "background", "lofi"],
    "dialogue": ["calm", "ambient", "soft", "light", "background", "lofi"],
}


def _text(t):
    return f"{t['name']} {t.get('folder', '')} {t.get('tags', '')}".lower()


def local_score(cat, t):
    words = MOODS.get(cat, [])
    txt = _text(t)
    hits = [w for w in words if w in txt]
    return min(100.0, 35.0 * len(hits)), hits


def _ask_gemini(cat, tracks):
    lines = [
        f'You help choose background music for a video scene of category "{cat}".',
        "Below are tracks from the user's OWN music library. You only know the name, folder and tags (you cannot hear them).",
        "Rate 0-100 how likely each track suits this scene. If the text gives no clue, score under 30. Be conservative.",
        'Return ONLY a JSON array, no markdown: [{"id": 1, "score": 80, "reason": "short reason"}]',
        "",
    ]
    for t in tracks[:80]:
        lines.append(f"[{t['id']}] name: {t['name']} | folder: {t.get('folder', '')} | tags: {t.get('tags', '')}")
    raw = gemini_client.ask("\n".join(lines))
    s = (raw or "").strip()
    a, b = s.find("["), s.rfind("]")
    if a == -1 or b <= a:
        raise ValueError("no JSON")
    out = {}
    for it in json.loads(s[a:b + 1]):
        try:
            out[int(it["id"])] = {"score": max(0.0, min(100.0, float(it["score"]))), "reason": str(it.get("reason", ""))[:160]}
        except (KeyError, TypeError, ValueError):
            continue
    return out


def suggest_tracks(cat, tracks, limit=5):
    gem, source = {}, "local"
    if gemini_client.is_configured():
        try:
            gem = _ask_gemini(cat, tracks)
            source = "gemini"
        except Exception:
            gem, source = {}, "local"
    rows = []
    for t in tracks:
        sc, hits = local_score(cat, t)
        g = gem.get(t["id"])
        score = g["score"] if g else sc
        reason = g["reason"] if g and g["reason"] else (("Name/tags match: " + ", ".join(hits)) if hits else "")
        if score >= 30:
            rows.append({"track_id": t["id"], "name": t["name"], "score": round(score), "reason": reason})
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows[:limit], source