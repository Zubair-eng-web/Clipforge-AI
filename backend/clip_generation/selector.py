"""Auto clip selection: best highlights first, never overlapping."""
from __future__ import annotations


def _overlaps(a0, a1, b0, b1, gap):
    return a0 < b1 + gap and a1 > b0 - gap


def select_clips(
    highlights,
    count=5,
    min_score=0.0,
    min_len=5.0,
    max_len=90.0,
    duration=None,
    pad_before=0.0,
    pad_after=0.0,
    min_gap=0.0,
    blocked=(),
):
    """Pick up to `count` clips by score. `blocked` = (start, end) ranges already used."""
    taken = [(float(a), float(b)) for a, b in blocked]
    out = []
    for h in sorted(highlights, key=lambda x: x.get("score", 0), reverse=True):
        if len(out) >= count:
            break
        if h.get("score", 0) < min_score:
            continue
        start = max(0.0, float(h["start"]) - pad_before)
        end = float(h["end"]) + pad_after
        if duration:
            end = min(end, float(duration))
        if end - start > max_len:
            end = start + max_len
        if end - start < min_len:
            continue
        if any(_overlaps(start, end, a, b, min_gap) for a, b in taken):
            continue
        taken.append((start, end))
        out.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "duration": round(end - start, 2),
            "score": float(h.get("score", 0)),
            "title": (h.get("title") or "Clip")[:200],
            "reason": h.get("reason", ""),
        })
    return out
