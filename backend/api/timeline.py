import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.clips import clip_dict
from backend.api.editor import _ready
from backend.database.db import get_db
from backend.database.models import Clip, Job

router = APIRouter(prefix="/api/editor", tags=["editor-timeline"])
Transition = Literal["none", "fade", "fadeblack", "dissolve", "wipeleft", "slideleft", "circleopen"]


class Seg(BaseModel):
    clip_id: int
    start: float = Field(0.0, ge=0)
    end: Optional[float] = Field(None, gt=0)


class TimelineBody(BaseModel):
    segments: list[Seg] = Field(min_length=1, max_length=20)
    ratio: Literal["first", "9:16", "1:1", "16:9"] = "first"
    transition: Transition = "none"
    transition_sec: float = Field(0.5, ge=0.2, le=2.0)
    title: str = Field("", max_length=200)


class SplitBody(BaseModel):
    clip_id: int
    at: float = Field(gt=0)
    title: str = Field("", max_length=150)


def _new_clip(db, src, title, start, end):
    c = Clip(video_id=src.video_id, title=title[:200], start_sec=float(src.start_sec or 0) + start,
             end_sec=float(src.start_sec or 0) + end, duration_sec=round(end - start, 3), status="pending")
    db.add(c)
    db.flush()
    return c


@router.post("/timeline")
def timeline(body: TimelineBody, db: Session = Depends(get_db)):
    items, durs = [], []
    for s in body.segments:
        c = _ready(db, s.clip_id)
        total = float(c.duration_sec or 0.0)
        end = s.end if s.end is not None else total
        if not end:
            raise HTTPException(400, f"Clip {c.id} has no known length")
        if total and end > total + 0.05:
            raise HTTPException(400, f"Segment end {end:g}s is beyond clip {c.id} ({total:g}s)")
        if end - s.start < 0.3:
            raise HTTPException(400, "Each segment must be at least 0.3 seconds long")
        items.append({"clip_id": c.id, "start": s.start, "end": end})
        durs.append(end - s.start)
    n = len(items)
    t = body.transition_sec if (body.transition != "none" and n > 1) else 0.0
    if t and any(d < 2 * t - 1e-6 for d in durs):
        raise HTTPException(400, f"Every segment must be at least {2 * t:g}s for a {t:g}s transition")
    total_out = round(sum(durs) - (n - 1) * t, 3)
    first = _ready(db, items[0]["clip_id"])
    title = body.title.strip() or f"Timeline ({n} segments)"
    new = _new_clip(db, first, title, items[0]["start"], items[0]["start"] + total_out)
    job = Job(type="timeline_clips", video_id=first.video_id, status="queued", payload=json.dumps({
        "segments": items, "new_clip_id": new.id, "ratio": body.ratio,
        "transition": body.transition, "transition_sec": body.transition_sec}))
    db.add(job)
    db.commit()
    db.refresh(new)
    db.refresh(job)
    return {"clip": clip_dict(new), "clip_id": new.id, "job_id": job.id, "duration_sec": total_out}


@router.post("/split")
def split(body: SplitBody, db: Session = Depends(get_db)):
    c = _ready(db, body.clip_id)
    total = float(c.duration_sec or 0.0)
    if not total:
        raise HTTPException(400, "This clip has no known length")
    if body.at < 0.3 or body.at > total - 0.3:
        raise HTTPException(400, f"Split point must be between 0.3s and {total - 0.3:.1f}s")
    base = body.title.strip() or c.title
    out = []
    for label, a, b in (("part 1", 0.0, body.at), ("part 2", body.at, total)):
        new = _new_clip(db, c, f"{base} ({label})", a, b)
        job = Job(type="timeline_clips", video_id=c.video_id, status="queued", payload=json.dumps({
            "segments": [{"clip_id": c.id, "start": a, "end": b}], "new_clip_id": new.id,
            "ratio": "first", "transition": "none", "transition_sec": 0.5}))
        db.add(job)
        db.flush()
        out.append((new, job))
    db.commit()
    for new, job in out:
        db.refresh(new)
        db.refresh(job)
    return {"clips": [clip_dict(n) for n, _ in out], "clip_ids": [n.id for n, _ in out],
            "job_ids": [j.id for _, j in out]}
