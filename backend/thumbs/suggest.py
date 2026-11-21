"""Thumbnail Studio (Phase 12.9): platform sizes, AI frame suggestions (OpenCV scoring), text ideas.
Text ideas come only from the clip title / scene description. Without Gemini a local template is used."""
import json
import shutil
import tempfile
from pathlib import Path

import cv2
import numpy as np

from backend.ai.gemini_client import ask, is_configured
from backend.video_processing.ffmpeg_service import FfmpegError, grab_frame

PLATFORMS = {
    "youtube": {"label": "YouTube (1280x720)", "w": 1280, "h": 720},
    "shorts": {"label": "Shorts / Reels / TikTok cover (1080x1920)", "w": 1080, "h": 1920},
    "instagram_post": {"label": "Instagram post (1080x1080)", "w": 1080, "h": 1080},
    "instagram_portrait": {"label": "Instagram portrait (1080x1350)", "w": 1080, "h": 1350},
    "facebook": {"label": "Facebook link (1200x630)", "w": 1200, "h": 630},
    "x": {"label": "X / Twitter (1600x900)", "w": 1600, "h": 900},
}


def score_image(img) -> float:
    """0..100: sharp, well lit, contrasty, colourful frames score higher."""
    h, w = img.shape[:2]
    if w > 320:
        img = cv2.resize(img, (320, max(1, int(h * 320 / w))))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    sharp = min(float(cv2.Laplacian(gray, cv2.CV_64F).var()) / 300.0, 1.0)
    mean = float(gray.mean()) / 255.0
    bright = max(0.0, 1.0 - abs(mean - 0.5) * 2.0)
    contrast = min(float(gray.std()) / 64.0, 1.0)
    f = img.astype(np.float32)
    b, g, r = f[:, :, 0], f[:, :, 1], f[:, :, 2]
    rg, yb = np.abs(r - g), np.abs(0.5 * (r + g) - b)
    col = float(np.sqrt(rg.std() ** 2 + yb.std() ** 2) + 0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2))
    colour = min(col / 80.0, 1.0)
    return round(100.0 * (0.35 * sharp + 0.2 * bright + 0.2 * contrast + 0.25 * colour), 1)


def suggest_frames(src, duration, count=6, samples=14):
    """Samples frames across the clip (small, one at a time: low RAM) and returns the best, spread apart."""
    duration = float(duration)
    if duration <= 0:
        return []
    n = max(samples, count * 2)
    times = [round(duration * (0.04 + 0.92 * i / (n - 1)), 2) for i in range(n)]
    tmp = Path(tempfile.mkdtemp(prefix="thumbs_"))
    scored = []
    try:
        for i, t in enumerate(times):
            p = tmp / f"{i}.jpg"
            try:
                grab_frame(src, p, t)
            except FfmpegError:
                continue
            img = cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue
            scored.append((score_image(img), t))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    scored.sort(reverse=True)
    gap = max(0.5, duration / (count * 2.5))
    picked = []
    for s, t in scored:
        if all(abs(t - q["t"]) >= gap for q in picked):
            picked.append({"t": t, "score": s})
        if len(picked) >= count:
            break
    return picked


def _local_texts(title):
    words = (title or "").split()
    out = []
    if words:
        out.append(" ".join(words[:5]).upper())
        if len(words) > 3:
            out.append(" ".join(words[:3]).upper())
    out += ["MUST WATCH", "WATCH THIS"]
    seen, res = set(), []
    for t in out:
        if t and t not in seen:
            seen.add(t)
            res.append(t[:40])
    return res


def _parse_list(raw):
    s = (raw or "").strip()
    a, b = s.find("["), s.rfind("]")
    if a == -1 or b <= a:
        return None
    try:
        data = json.loads(s[a:b + 1])
    except ValueError:
        return None
    out = [" ".join(str(x).split()).upper()[:40] for x in data if isinstance(x, str) and str(x).strip()]
    return out[:6] or None


def suggest_texts(title, description="", use_gemini=True):
    """Returns (texts, source, warning). Only the given title / description are used."""
    local = _local_texts(title)
    if not use_gemini:
        return local, "local", None
    if not is_configured():
        return local, "local", "No Gemini key: simple text ideas from the title."
    prompt = (
        "You write short thumbnail texts for a video clip. Use ONLY the facts below. Do not invent events.\n"
        f"Clip title: {title}\nScene description: {description or '(none)'}\n"
        'Return ONLY a JSON array of 5 texts, each at most 5 words, like ["TEXT ONE", "TEXT TWO"].')
    try:
        texts = _parse_list(ask(prompt))
    except Exception as e:
        return local, "local", f"Gemini failed, local ideas used: {str(e)[:120]}"
    if not texts:
        return local, "local", "Gemini reply could not be read, local ideas used."
    return texts, "gemini", None
