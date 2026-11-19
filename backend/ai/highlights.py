"""Highlight candidates: windows built from the transcript, scored locally,
optionally re-scored by Gemini (TEXT ONLY, never video). Falls back to local scores."""
import json
import logging
import os
import re
import time
from typing import Callable, Optional

from backend.ai import gemini_client

log = logging.getLogger("clipforge.highlights")

MIN_LEN, TARGET_LEN, MAX_LEN, STEP = 15.0, 30.0, 60.0, 10.0
BATCH = 8

_HOOKS = [
    "secret", "never", "always", "mistake", "mistakes", "truth", "stop", "why", "how", "best", "worst",
    "biggest", "amazing", "incredible", "important", "remember", "free", "imagine", "crazy", "shocking",
    "nobody", "everyone", "learn", "tip", "tips", "trick", "easy", "fast", "money", "win", "lose",
    "problem", "solution", "reason", "you need", "you should",
    "کبھی", "راز", "غلطی", "اہم", "پیسہ", "سچ", "سیکھ", "آسان",
]
_HOOK_RE = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in _HOOKS) + r")\b", re.IGNORECASE)
_TRANSIENT = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "timed out", "Timeout", "getaddrinfo", "ConnectError")


def build_candidates(segments, min_len=MIN_LEN, target_len=TARGET_LEN, max_len=MAX_LEN, step=STEP):
    """Sliding windows over transcript segments, starting at segment boundaries."""
    segs = [s for s in segments if s.get("text") and s["end"] > s["start"]]
    out, last_start = [], -1e9
    for i, first in enumerate(segs):
        start = first["start"]
        if start - last_start < step:
            continue
        j = i
        while j + 1 < len(segs) and segs[j]["end"] - start < target_len and segs[j + 1]["end"] - start <= max_len:
            j += 1
        end = segs[j]["end"]
        if end - start < min_len:
            continue
        out.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "text": " ".join(s["text"] for s in segs[i:j + 1]),
        })
        last_start = start
    return out


def local_score(text: str, duration: float) -> float:
    """0..100 heuristic: speech pace, questions, exclamations, hook words, numbers, clean ending, length."""
    words = re.findall(r"\w+", text, flags=re.UNICODE)
    if duration <= 0 or not words:
        return 0.0
    wps = len(words) / duration
    s = 25 * max(0.0, 1 - abs(wps - 2.75) / 2.75)
    q = text.count("?") + text.count("؟")
    ex = text.count("!")
    s += min(q, 3) * 5 + min(ex, 3) * 4
    hooks = {m.lower() for m in _HOOK_RE.findall(text)}
    s += min(len(hooks), 4) * 6
    if re.search(r"\d", text):
        s += 5
    first = text[:120]
    if "?" in first or "؟" in first or _HOOK_RE.search(first):
        s += 8
    if text.rstrip()[-1:] in (".", "!", "?", "؟", "۔"):
        s += 5
    if 20 <= duration <= 45:
        s += 10
    elif 12 <= duration < 20 or 45 < duration <= 60:
        s += 5
    return round(min(s, 100.0), 1)


def _overlap_ratio(a, b) -> float:
    inter = min(a["end"], b["end"]) - max(a["start"], b["start"])
    if inter <= 0:
        return 0.0
    return inter / max(min(a["end"] - a["start"], b["end"] - b["start"]), 0.001)


def select_top(cands, limit):
    """Best local scores first, skipping windows that overlap an already kept one by 50% or more."""
    kept = []
    for c in sorted(cands, key=lambda c: c["local_score"], reverse=True):
        if all(_overlap_ratio(c, k) < 0.5 for k in kept):
            kept.append(c)
        if len(kept) >= limit:
            break
    return kept


def _local_title(text: str) -> str:
    w = text.split()
    return " ".join(w[:8]) + ("..." if len(w) > 8 else "")


def _build_prompt(chunk) -> str:
    lines = [
        "You are an expert short-form video editor.",
        "Below are candidate clips taken from ONE video transcript.",
        "Score each from 0 to 100 for how well it works as a standalone short clip: strong hook, one complete idea, useful or emotional payoff, clear ending.",
        "Also write a catchy title (max 8 words) in the SAME language as the clip text, and a one-sentence reason in English.",
        'Return ONLY a JSON array, no markdown, like: [{"id": 1, "score": 85, "title": "...", "reason": "..."}]',
        "",
    ]
    for idx, c in chunk:
        lines.append(f"[{idx}] ({int(c['end'] - c['start'])}s) {c['text'][:500]}")
    return "\n".join(lines)


def parse_gemini_json(raw: str) -> dict:
    s = (raw or "").strip()
    a, b = s.find("["), s.rfind("]")
    if a == -1 or b <= a:
        raise ValueError("No JSON array in the Gemini response")
    data = json.loads(s[a:b + 1])
    out = {}
    for item in data:
        try:
            i = int(item["id"])
            sc = float(item["score"])
        except (KeyError, TypeError, ValueError):
            continue
        out[i] = {
            "score": max(0.0, min(100.0, sc)),
            "title": str(item.get("title", "")).strip()[:120],
            "reason": str(item.get("reason", "")).strip()[:300],
        }
    return out


def _ask_with_retry(prompt: str, tries: int = 3) -> str:
    delay = 2.0
    for attempt in range(tries):
        try:
            return gemini_client.ask(prompt)
        except Exception as e:
            transient = any(t in str(e) or t in type(e).__name__ for t in _TRANSIENT)
            if not transient or attempt == tries - 1:
                raise
            log.warning("Gemini busy (%s), retrying in %.0fs", str(e)[:80], delay)
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def analyze_highlights(segments, use_gemini: bool = True, on_progress: Optional[Callable[[float], None]] = None,
                       sleep_between: float = 1.0):
    """Returns (items sorted by score desc, info). Never raises because of Gemini problems."""
    cands = build_candidates(segments)
    for c in cands:
        c["local_score"] = local_score(c["text"], c["end"] - c["start"])
    kept = select_top(cands, int(os.getenv("HIGHLIGHT_MAX_CANDIDATES", "60") or 60))
    for c in kept:
        c["score"] = c["local_score"]
        c["source"] = "local"
        c["title"] = _local_title(c["text"])
        c["reason"] = "Local score: speech pace, hooks, questions and clip length"

    info = {"candidates": len(cands), "kept": len(kept), "gemini_used": False, "gemini_scored": 0, "warnings": []}
    if use_gemini and kept:
        if not gemini_client.is_configured():
            info["warnings"].append("GEMINI_API_KEY is not set, using local scores only")
        else:
            targets = kept[:int(os.getenv("HIGHLIGHT_GEMINI_MAX", "24") or 24)]
            indexed = list(enumerate(targets))
            batches = [indexed[i:i + BATCH] for i in range(0, len(indexed), BATCH)]
            for bi, chunk in enumerate(batches):
                try:
                    scored = parse_gemini_json(_ask_with_retry(_build_prompt(chunk)))
                except Exception as e:
                    info["warnings"].append(f"Gemini failed, local scores used for the rest: {str(e)[:160]}")
                    break
                for idx, c in chunk:
                    g = scored.get(idx)
                    if g is None:
                        continue
                    c["score"] = round(0.7 * g["score"] + 0.3 * c["local_score"], 1)
                    c["source"] = "gemini"
                    if g["title"]:
                        c["title"] = g["title"]
                    if g["reason"]:
                        c["reason"] = g["reason"]
                    info["gemini_scored"] += 1
                if on_progress:
                    on_progress((bi + 1) / len(batches))
                if sleep_between and bi < len(batches) - 1:
                    time.sleep(sleep_between)
            info["gemini_used"] = info["gemini_scored"] > 0
    if on_progress:
        on_progress(1.0)
    kept.sort(key=lambda c: c["score"], reverse=True)
    return kept, info