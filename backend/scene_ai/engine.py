"""Scene AI engine: analysis units, frame sampling, batched Gemini vision classification,
category segments and duration fitting. Mostly pure functions (unit tested)."""
import json
import logging
import os
import subprocess
import time

from backend.ai import gemini_client
from backend.scene_ai.categories import CATEGORIES
from backend.video_processing.ffmpeg_service import _NO_WINDOW, _exe

log = logging.getLogger("clipforge.scene_ai")
TRANSIENT = ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED", "timed out", "Timeout", "getaddrinfo",
             "ConnectError", "INTERNAL")
PERMANENT = ("403", "PERMISSION_DENIED", "API_KEY_INVALID", "API key", "401", "UNAUTHENTICATED", "NOT_FOUND")
FRAME_POINTS = (0.15, 0.5, 0.85)


def fmt(t: float) -> str:
    t = int(max(t, 0))
    return f"{t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}"


# ---------- analysis units ----------
def build_units(shots, duration=0.0, target=None):
    """Merge PySceneDetect shots into analysis units (about 12-90 s each, at most ~SCENE_AI_MAX_UNITS)."""
    shots = sorted((s for s in shots if s["end"] > s["start"]), key=lambda s: s["start"])
    if not shots:
        return []
    total = duration or shots[-1]["end"]
    if target is None:
        max_units = max(int(os.getenv("SCENE_AI_MAX_UNITS", "150") or 150), 10)
        target = min(max(total / max_units, 12.0), 90.0)
    pieces = []
    for s in shots:
        length = s["end"] - s["start"]
        if length > 1.5 * target:  # a very long shot is split so it can be judged in parts
            n = max(int(round(length / target)), 2)
            step = length / n
            pieces += [(s["start"] + i * step, s["start"] + (i + 1) * step) for i in range(n)]
        else:
            pieces.append((s["start"], s["end"]))
    units, cur = [], None
    for a, b in pieces:
        cur = [a, b] if cur is None else [cur[0], b]
        if cur[1] - cur[0] >= target:
            units.append({"start": round(cur[0], 2), "end": round(cur[1], 2)})
            cur = None
    if cur is not None:
        if units and cur[1] - cur[0] < target / 2:
            units[-1]["end"] = round(cur[1], 2)
        else:
            units.append({"start": round(cur[0], 2), "end": round(cur[1], 2)})
    return units


def grab_jpeg(src, t: float, width: int = 384):
    """One small JPEG frame as bytes (no temp files, tiny RAM)."""
    cmd = [_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{max(t, 0.0):.2f}", "-i", str(src),
           "-frames:v", "1", "-vf", f"scale={width}:-2", "-q:v", "6", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=60, creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return None
    return r.stdout if r.returncode == 0 and r.stdout else None


def unit_text(segments, u, limit=350) -> str:
    txt = " ".join(s.get("text", "").strip() for s in segments if s["start"] < u["end"] and s["end"] > u["start"])
    return txt[:limit]


# ---------- classification ----------
def local_scores(text, keys):
    """Offline fallback from speech keywords only. Capped at 60, so results are always 'uncertain'."""
    t = (text or "").lower()
    out = {}
    for k in keys:
        hits = sum(1 for w in CATEGORIES.get(k, {}).get("kw", []) if w in t)
        out[k] = float(min(60, 30 * hits)) if hits else 0.0
    return out


def build_header(cats):
    lines = [
        "You are a precise film scene analyst. You get consecutive units of ONE video. Each unit has a time range, its dialogue and 3 still frames (early, middle, late).",
        "For EACH unit rate from 0 to 100 how strongly it shows EACH category below. 0 = not present. Judge from the frames AND the dialogue together.",
        "Be strict: a category scores above 60 only when the evidence is clear. Categories are independent, a unit can score high on several.",
        "Categories:",
    ]
    for c in cats:
        rule = c["rule"]
        if c["key"] == "custom":
            rule = "Only units matching this user description: " + str(c.get("custom_text", ""))[:300]
        lines.append(f'- "{c["key"]}": {rule}')
    keys = ", ".join(f'"{c["key"]}": 0' for c in cats)
    lines += [
        "Also give a short English description (max 15 words) of what happens in the unit.",
        'Return ONLY a JSON array with one object per unit, no markdown: [{"id": 1, "scores": {' + keys + '}, "description": "..."}]',
        "",
    ]
    return "\n".join(lines)


def parse_response(raw, keys):
    s = (raw or "").strip()
    a, b = s.find("["), s.rfind("]")
    if a == -1 or b <= a:
        raise ValueError("No JSON array in the Gemini response")
    out = {}
    for item in json.loads(s[a:b + 1]):
        try:
            i = int(item["id"])
        except (KeyError, TypeError, ValueError):
            continue
        raw_scores = item.get("scores") or {}
        sc = {}
        for k in keys:
            try:
                sc[k] = max(0.0, min(100.0, float(raw_scores.get(k, 0))))
            except (TypeError, ValueError):
                sc[k] = 0.0
        out[i] = {"scores": sc, "desc": str(item.get("description", "")).strip()[:200]}
    return out


def _call(parts, tries=3):
    delay = 3.0
    for attempt in range(tries):
        try:
            return gemini_client.ask_parts(parts)
        except Exception as e:
            transient = any(t in str(e) or t in type(e).__name__ for t in TRANSIENT)
            if not transient or attempt == tries - 1:
                raise
            log.warning("Gemini busy (%s), retrying in %.0fs", str(e)[:80], delay)
            time.sleep(delay)
            delay *= 2


def classify(units, segments, cats, src, use_vision=True, progress=None, sleep_between=1.0):
    """Returns (results, info). results[i] = {scores: {key: 0..100}, desc, source: gemini|local}.
    Units are sent in batches (SCENE_AI_BATCH, default 8 units = 24 small frames per call)."""
    keys = [c["key"] for c in cats]
    batch_n = max(int(os.getenv("SCENE_AI_BATCH", "8") or 8), 1)
    info = {"units": len(units), "gemini_batches": 0, "gemini_failed_batches": 0, "local_units": 0,
            "vision": bool(use_vision), "warnings": []}
    gem_ok = gemini_client.is_configured()
    if not gem_ok:
        info["warnings"].append("GEMINI_API_KEY is not set: speech keywords only (low accuracy, results are marked uncertain)")
    header = build_header(cats)
    results = [None] * len(units)
    batches = [list(range(i, min(i + batch_n, len(units)))) for i in range(0, len(units), batch_n)]
    fails = 0
    for bi, idxs in enumerate(batches):
        if gem_ok:
            try:
                parts = [header]
                for i in idxs:
                    u = units[i]
                    parts.append(f"Unit {i + 1} [{fmt(u['start'])} - {fmt(u['end'])}] dialogue: "
                                 + (unit_text(segments, u) or "(no speech)"))
                    if use_vision:
                        for f in FRAME_POINTS:
                            img = grab_jpeg(src, u["start"] + (u["end"] - u["start"]) * f)
                            if img:
                                parts.append(img)
                parsed = parse_response(_call(parts), keys)
                got = 0
                for i in idxs:
                    g = parsed.get(i + 1)
                    if g:
                        results[i] = {"scores": g["scores"], "desc": g["desc"], "source": "gemini"}
                        got += 1
                if got == 0:
                    raise ValueError("Gemini returned no usable unit")
                info["gemini_batches"] += 1
                fails = 0
            except Exception as e:
                msg = str(e)
                if (type(e).__name__ == "JobCancelled"):
                    raise
                info["gemini_failed_batches"] += 1
                fails += 1
                if len(info["warnings"]) < 5:
                    info["warnings"].append(f"Gemini batch {bi + 1} failed: {msg[:160]}")
                if any(t in msg for t in PERMANENT):
                    gem_ok = False
                    info["warnings"].append("Gemini key/model problem, using speech keywords for the rest (results uncertain)")
                elif fails >= 2:
                    gem_ok = False
                    info["warnings"].append("Gemini failed twice in a row (quota or busy), using speech keywords for the rest")
        for i in idxs:
            if results[i] is None:
                results[i] = {"scores": local_scores(unit_text(segments, units[i]), keys), "desc": "", "source": "local"}
                info["local_units"] += 1
        if progress:
            progress((bi + 1) / len(batches))
        if gem_ok and sleep_between and bi < len(batches) - 1:
            time.sleep(sleep_between)
    return results, info


# ---------- segments and durations ----------
def find_segments(units, results, key, threshold, merge=True):
    """Consecutive positive units become one scene. merge=True also bridges a single weak unit between two strong ones."""
    low = max(threshold - 20, 25)
    sc = [r["scores"].get(key, 0.0) for r in results]
    pos = [s >= low for s in sc]
    active = list(pos)
    if merge:
        for i in range(1, len(sc) - 1):
            if not pos[i] and pos[i - 1] and pos[i + 1]:
                active[i] = True
    segs, i, n = [], 0, len(units)
    while i < n:
        if not active[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and active[j + 1]:
            j += 1
        idx = list(range(i, j + 1))
        pos_idx = [k for k in idx if pos[k]]
        w = sum(units[k]["end"] - units[k]["start"] for k in pos_idx) or 1.0
        conf = sum(sc[k] * (units[k]["end"] - units[k]["start"]) for k in pos_idx) / w
        gem = sum(1 for k in pos_idx if results[k]["source"] == "gemini")
        source = "gemini" if gem * 2 >= len(pos_idx) else "local"
        best = max(pos_idx, key=lambda k: sc[k])
        status = "detected" if (conf >= threshold and source == "gemini") else "uncertain"
        segs.append({"category": key, "start": units[i]["start"], "end": units[j]["end"], "conf": round(conf, 1),
                     "source": source, "status": status, "description": results[best].get("desc") or "",
                     "unit_idx": idx})
        i = j + 1
    return segs


def fit_window(units, sc, idx, length):
    """Most relevant continuous window of `length` seconds inside the scene made of units idx."""
    g0, g1 = units[idx[0]]["start"], units[idx[-1]]["end"]
    if g1 - g0 <= length:
        return g0, g1
    cands = {units[k]["start"] for k in idx} | {max(g0, units[k]["end"] - length) for k in idx}
    best = None
    for st in sorted(cands):
        st = max(g0, min(st, g1 - length))
        en = st + length
        val = 0.0
        for k in idx:
            ov = min(units[k]["end"], en) - max(units[k]["start"], st)
            if ov > 0:
                val += sc[k] * ov
        if best is None or val > best[0] + 1e-9:
            best = (val, st, en)
    return round(best[1], 2), round(best[2], 2)


def snap_range(st, en, cuts, lo, hi, tol=3.0):
    """Move start/end to the nearest shot cut (within tol seconds) so the clip does not begin or end mid-shot."""
    def snap(t):
        near = [c for c in cuts if abs(c - t) <= tol and lo - 1e-6 <= c <= hi + 1e-6]
        return min(near, key=lambda c: abs(c - t)) if near else t
    a, b = snap(st), snap(en)
    return (round(a, 2), round(b, 2)) if b - a >= 1.0 else (st, en)


def overlap_ratio(a0, a1, b0, b1) -> float:
    inter = min(a1, b1) - max(a0, b0)
    if inter <= 0:
        return 0.0
    return inter / max(min(a1 - a0, b1 - b0), 0.001)