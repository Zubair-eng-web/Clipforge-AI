"""Create category clips (clip_export jobs) from detected scenes. Files go to storage/generated_clips/<category>/."""
import json
import re
from pathlib import Path

from sqlalchemy import select

from backend import config
from backend.database.models import CategoryScene, Clip, Job
from backend.scene_ai.categories import short_label


def _next_number(db, category: str) -> int:
    mx = 0
    folder = config.STORAGE_DIR / "generated_clips" / category
    if folder.is_dir():
        for f in folder.iterdir():
            m = re.match(rf"{re.escape(category)}_scene_(\d+)", f.name)
            if m:
                mx = max(mx, int(m.group(1)))
    for fn in db.scalars(select(CategoryScene.filename).where(CategoryScene.category == category,
                                                              CategoryScene.filename.is_not(None))).all():
        m = re.match(rf"{re.escape(category)}_scene_(\d+)", fn or "")
        if m:
            mx = max(mx, int(m.group(1)))
    return mx + 1


def _ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(path: Path, segments, start: float, end: float) -> int:
    lines, n = [], 0
    for s in segments:
        a, b = max(s["start"], start), min(s["end"], end)
        if b <= a or not str(s.get("text", "")).strip():
            continue
        n += 1
        lines.append(f"{n}\n{_ts(a - start)} --> {_ts(b - start)}\n{str(s['text']).strip()}\n")
    if lines:
        path.write_text("\n".join(lines), encoding="utf-8")
    return n


def create_clips(db, video, scenes, mode="accurate", subtitles=False, segments=None):
    """For each scene without a live clip: create a Clip + clip_export job. Commits. Returns a list of dicts."""
    created, counters = [], {}
    for sc in scenes:
        if sc.clip_id:
            old = db.get(Clip, sc.clip_id)
            if old is not None and old.status in ("pending", "processing", "ready"):
                continue
        dur = sc.end_sec - sc.start_sec
        if dur < 0.5:
            continue
        cat = sc.category
        if cat not in counters:
            counters[cat] = _next_number(db, cat)
        n = counters[cat]
        counters[cat] += 1
        fname = f"{cat}_scene_{n:03d}"
        clip = Clip(video_id=video.id, title=f"{short_label(cat)} scene {n:03d}"[:200], start_sec=round(sc.start_sec, 3),
                    end_sec=round(sc.end_sec, 3), duration_sec=round(dur, 3), status="pending", ai_score=sc.confidence)
        db.add(clip)
        db.flush()
        job = Job(type="clip_export", video_id=video.id, status="queued",
                  payload=json.dumps({"clip_id": clip.id, "mode": mode, "category": cat, "filename": fname}))
        db.add(job)
        db.flush()
        sc.clip_id, sc.filename = clip.id, fname
        if subtitles and segments:
            folder = config.STORAGE_DIR / "generated_clips" / cat
            folder.mkdir(parents=True, exist_ok=True)
            write_srt(folder / f"{fname}.srt", segments, sc.start_sec, sc.end_sec)
        created.append({"scene_id": sc.id, "clip_id": clip.id, "job_id": job.id, "filename": fname})
    db.commit()
    return created