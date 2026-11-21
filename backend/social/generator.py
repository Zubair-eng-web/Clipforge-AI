"""Social text (title, description, caption, hashtags, ...) from REAL clip data only."""
import json
import re

from backend.ai.gemini_client import ask, is_configured

TONES = {
    "viral": "energetic, hooky, curiosity-driven, made to stop the scroll",
    "funny": "playful and humorous, light jokes, no insults",
    "cinematic": "dramatic and atmospheric, like a movie trailer line",
    "professional": "clean, clear and informative, no slang",
    "suspenseful": "tense, mysterious, leaves the viewer wanting more",
    "minimal": "very short, simple, no hype",
}
PLATFORMS = {
    "general": "General", "youtube_shorts": "YouTube Shorts", "instagram_reels": "Instagram Reels",
    "facebook_reels": "Facebook Reels", "tiktok": "TikTok",
}
FIELDS = ["title", "description", "caption", "hashtags", "keywords", "cta", "pinned_comment"]
_CTA = {
    "viral": "Follow for more!", "funny": "Tag a friend who needs to see this!",
    "cinematic": "Watch till the end.", "professional": "Subscribe for more videos.",
    "suspenseful": "Part 2 soon. Follow so you do not miss it.", "minimal": "Follow.",
}


def _clip(s, n: int) -> str:
    return str(s or "").strip()[:n]


def clean_hashtags(v) -> str:
    items = v if isinstance(v, list) else re.split(r"[\s,]+", str(v or ""))
    out, seen = [], set()
    for t in items:
        t = re.sub(r"[^\w]", "", str(t).lstrip("#"))
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append("#" + t)
    return " ".join(out[:15])


def normalize(d: dict) -> dict:
    kw = d.get("keywords", "")
    if isinstance(kw, list):
        kw = ", ".join(str(x).strip() for x in kw if str(x).strip())
    return {
        "title": _clip(d.get("title"), 100), "description": _clip(d.get("description"), 1000),
        "caption": _clip(d.get("caption"), 500), "hashtags": clean_hashtags(d.get("hashtags")),
        "keywords": _clip(kw, 400), "cta": _clip(d.get("cta"), 200),
        "pinned_comment": _clip(d.get("pinned_comment"), 300),
    }


def parse_json(text: str):
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        d = json.loads(t[a:b + 1])
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


def build_context(title: str, label: str, description: str, speech: str, notes: str) -> str:
    parts = []
    if title:
        parts.append(f"Clip title: {title}")
    if label:
        parts.append(f"Scene type: {label}")
    if description:
        parts.append(f"AI scene description: {description}")
    if speech:
        parts.append(f"Speech in the clip: {speech}")
    if notes:
        parts.append(f"Creator notes: {notes}")
    return "\n".join(parts)


def build_prompt(context: str, tone: str, platform: str) -> str:
    return (
        "You write social media text for a short video clip.\n"
        f"Platform: {PLATFORMS.get(platform, 'General')}. Tone: {tone} ({TONES.get(tone, '')}).\n"
        "Use ONLY the facts below. Do not invent dialogue, names, scores or events. "
        "If the information is thin, stay generic.\n\n"
        f"{context or '(no details available)'}\n\n"
        "Return ONLY JSON with these keys: title (max 80 chars), description (2-3 sentences), "
        "caption (1-2 short lines), hashtags (list of 8-12 words, no spaces), keywords (list of 6-10), "
        "cta (one short line), pinned_comment (one short line to start discussion). No markdown."
    )


def local_fallback(title: str, label: str, tone: str) -> dict:
    base = title or label or "Gameplay moment"
    words = [w for w in re.findall(r"[A-Za-z0-9]+", f"{label} {title}") if len(w) > 3][:4]
    tags = words + ["shorts", "gaming"]
    return normalize({
        "title": base,
        "description": f"{base}." + (f" Scene type: {label}." if label and label.lower() not in base.lower() else ""),
        "caption": base, "hashtags": tags, "keywords": words + ["gameplay"],
        "cta": _CTA.get(tone, "Follow for more!"), "pinned_comment": "What do you think? Tell me below.",
    })


def generate(title: str, label: str, description: str, speech: str, notes: str, tone: str, platform: str):
    """Returns (fields, source, warning). source is 'gemini' or 'local'."""
    if not is_configured():
        return local_fallback(title, label, tone), "local", "No Gemini key: simple local text was made."
    try:
        raw = ask(build_prompt(build_context(title, label, description, speech, notes), tone, platform))
    except Exception as e:  # network, quota, 403 ...
        return local_fallback(title, label, tone), "local", f"Gemini failed ({str(e)[:120]}). Local text used."
    d = parse_json(raw)
    f = normalize(d) if d else None
    if not f or not f["title"]:
        return local_fallback(title, label, tone), "local", "Gemini reply could not be read. Local text used."
    return f, "gemini", None