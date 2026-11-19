import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.clips import clip_dict
from backend.database.db import get_db
from backend.database.models import Clip, Job

clip_router = APIRouter(prefix="/api/clips", tags=["editor"])
router = APIRouter(prefix="/api/editor", tags=["editor"])


class EditBody(BaseModel):
    trim_start: float = Field(0.0, ge=0)
    trim_end: Optional[float] = Field(None, gt=0)
    speed: float = Field(1.0, ge=0.5, le=2.0)
    volume: float = Field(1.0, ge=0.0, le=2.0)
    mute: bool = False
    fade_seconds: float = Field(0.0, ge=0.0, le=3.0)
    brightness: float = Field(0.0, ge=-0.5, le=0.5)
    contrast: float = Field(1.0, ge=0.5, le=1.5)
    saturation: float = Field(1.0, ge=0.0, le=2.0)
    flip_h: bool = False


class MergeBody(BaseModel):
    clip_ids: list[int] = Field(min_length=2, max_length=10)
    ratio: Literal["first", "9:16", "1:1", "16:9"] = "first"
    title: str = Field("", max_length=200)


def _ready(db: Session, clip_id: int) -> Clip:
    c = db.get(Clip, clip_id)
    if not c:
        raise HTTPException(404, f"Clip {clip_id} not found")
    if c.status != "ready" or not c.file_path:
        raise HTTPException(409, f"Clip {clip_id} is not ready yet")
    return c


@clip_router.post("/{clip_id}/edit")
def edit_clip(clip_id: int, body: EditBody, db: Session = Depends(get_db)):
    clip = _ready(db, clip_id)
    total = float(clip.duration_sec or 0.0)
    start = body.trim_start
    end = min(body.trim_end, total) if (body.trim_end is not None and total) else (body.trim_end or total)
    if total and start >= total:
        raise HTTPException(400, "Trim start is beyond the end of the clip")
    if end and end - start < 0.5:
        raise HTTPException(400, "The trimmed clip must be at least 0.5 seconds long")
    trimmed = start > 0 or (total and end and end < total - 0.05)
    changed = (trimmed or body.speed != 1.0 or body.volume != 1.0 or body.mute or body.fade_seconds > 0
               or body.brightness != 0.0 or body.contrast != 1.0 or body.saturation != 1.0 or body.flip_h)
    if not changed:
        raise HTTPException(400, "Nothing to change. Adjust at least one setting.")

    ops = {"trim_start": start, "trim_end": end or None, "speed": body.speed, "volume": body.volume,
           "mute": body.mute, "fade": body.fade_seconds, "brightness": body.brightness,
           "contrast": body.contrast, "saturation": body.saturation, "flip_h": body.flip_h}
    out_dur = round(((end or total) - start) / body.speed, 3)
    new = Clip(video_id=clip.video_id, title=f"{clip.title} (edited)"[:200], start_sec=clip.start_sec + start,
               end_sec=clip.start_sec + (end or total), duration_sec=out_dur, ai_score=clip.ai_score, status="pending")
    db.add(new)
    db.flush()
    job = Job(type="edit_clip", video_id=clip.video_id, status="queued",
              payload=json.dumps({"clip_id": clip.id, "new_clip_id": new.id, "ops": ops}))
    db.add(job)
    db.commit()
    db.refresh(new)
    db.refresh(job)
    return {"clip": clip_dict(new), "clip_id": new.id, "job_id": job.id}


@router.post("/merge")
def merge(body: MergeBody, db: Session = Depends(get_db)):
    clips = [_ready(db, i) for i in body.clip_ids]
    total = round(sum(float(c.duration_sec or 0.0) for c in clips), 3)
    first = clips[0]
    title = body.title.strip() or f"Merged clip ({len(clips)} clips)"
    new = Clip(video_id=first.video_id, title=title[:200], start_sec=first.start_sec,
               end_sec=first.start_sec + total, duration_sec=total, status="pending")
    db.add(new)
    db.flush()
    job = Job(type="merge_clips", video_id=first.video_id, status="queued",
              payload=json.dumps({"clip_ids": body.clip_ids, "new_clip_id": new.id, "ratio": body.ratio}))
    db.add(job)
    db.commit()
    db.refresh(new)
    db.refresh(job)
    return {"clip": clip_dict(new), "clip_id": new.id, "job_id": job.id}