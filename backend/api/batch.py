import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database.db import get_db
from backend.database.models import Clip, Job, Video

router = APIRouter(prefix="/api/batch", tags=["batch"])


class StartBody(BaseModel):
    video_ids: list[int] = Field(min_length=1, max_length=50)
    count: int = Field(5, ge=1, le=20)
    mode: Literal["accurate", "fast"] = "accurate"
    min_score: float = Field(0.0, ge=0, le=100)
    use_gemini: bool = True


@router.post("/start")
def start_batch(body: StartBody, db: Session = Depends(get_db)):
    ids = list(dict.fromkeys(body.video_ids))
    videos = {v.id: v for v in db.scalars(select(Video).where(Video.id.in_(ids))).all()}
    missing = [i for i in ids if i not in videos]
    if missing:
        raise HTTPException(404, f"Video not found: {missing}")
    audio_only = [i for i in ids if videos[i].width is None]
    if audio_only:
        raise HTTPException(400, f"Audio-only files cannot be clipped: {audio_only}")
    active = {
        j.video_id for j in db.scalars(
            select(Job).where(Job.type == "batch_video", Job.status.in_(["queued", "processing"]))
        ).all()
    }
    created, skipped = [], []
    for vid in ids:
        if vid in active:
            skipped.append(vid)
            continue
        job = Job(type="batch_video", video_id=vid, status="queued",
                  payload=json.dumps({"video_id": vid, "count": body.count, "mode": body.mode,
                                      "min_score": body.min_score, "use_gemini": body.use_gemini}))
        db.add(job)
        db.flush()
        created.append(job.id)
    db.commit()
    return {"created": len(created), "job_ids": created, "skipped_video_ids": skipped}


@router.get("/jobs")
def batch_jobs(limit: int = 50, db: Session = Depends(get_db)):
    jobs = db.scalars(
        select(Job).where(Job.type == "batch_video").order_by(Job.id.desc()).limit(min(max(limit, 1), 200))
    ).all()
    vids = {j.video_id for j in jobs if j.video_id}
    names = {v.id: v.original_name for v in db.scalars(select(Video).where(Video.id.in_(vids))).all()} if vids else {}
    counts: dict = {}
    if vids:
        for vid, status, n in db.execute(
            select(Clip.video_id, Clip.status, func.count()).where(Clip.video_id.in_(vids)).group_by(Clip.video_id, Clip.status)
        ).all():
            counts.setdefault(vid, {})[status] = n
    items = []
    for j in jobs:
        c = counts.get(j.video_id, {})
        items.append({
            "job_id": j.id, "video_id": j.video_id, "video_name": names.get(j.video_id, f"Video {j.video_id}"),
            "status": j.status, "progress": j.progress, "error": j.error,
            "clips_total": sum(c.values()), "clips_ready": c.get("ready", 0),
            "clips_active": c.get("pending", 0) + c.get("processing", 0),
            "created_at": j.created_at.isoformat(),
        })
    return {"items": items}