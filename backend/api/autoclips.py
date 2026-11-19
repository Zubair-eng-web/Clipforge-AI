"""Auto clips API: turn the best analyzed highlights into exported clips."""
import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.clip_generation.selector import select_clips
from backend.database.db import get_db
from backend.database.models import Clip, Job, Video, VideoAnalysis

router = APIRouter(prefix="/api/videos", tags=["auto-clips"])


class AutoClipsBody(BaseModel):
    count: int = Field(5, ge=1, le=20)
    min_score: float = Field(0.0, ge=0, le=100)
    mode: Literal["accurate", "fast"] = "accurate"
    pad_before: float = Field(0.0, ge=0, le=5)
    pad_after: float = Field(0.0, ge=0, le=5)


@router.post("/{video_id}/auto-clips")
def auto_clips(video_id: int, body: Optional[AutoClipsBody] = None, db: Session = Depends(get_db)):
    body = body or AutoClipsBody()
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(404, "Video not found")
    analysis = db.scalar(select(VideoAnalysis).where(VideoAnalysis.video_id == video_id))
    if analysis is None or analysis.status != "ready":
        raise HTTPException(409, "Run AI analysis on this video first")
    try:
        highlights = json.loads(analysis.highlights_json or "[]")
    except ValueError:
        highlights = []
    if not highlights:
        raise HTTPException(422, "No highlights found (video may have no speech)")

    existing = db.scalars(
        select(Clip).where(Clip.video_id == video_id, Clip.status.in_(["pending", "processing", "ready"]))
    ).all()
    chosen = select_clips(
        highlights,
        count=body.count,
        min_score=body.min_score,
        duration=video.duration_sec,
        pad_before=body.pad_before,
        pad_after=body.pad_after,
        blocked=[(c.start_sec, c.end_sec) for c in existing],
    )
    if not chosen:
        raise HTTPException(422, "No new clips available (all good highlights already used or score too low)")

    created = []
    for c in chosen:
        clip = Clip(
            video_id=video_id,
            title=c["title"],
            start_sec=c["start"],
            end_sec=c["end"],
            duration_sec=c["duration"],
            status="pending",
            ai_score=c["score"],
        )
        db.add(clip)
        db.flush()
        job = Job(
            type="clip_export",
            video_id=video_id,
            status="queued",
            payload=json.dumps({"clip_id": clip.id, "mode": body.mode}),
        )
        db.add(job)
        db.flush()
        created.append({"clip_id": clip.id, "job_id": job.id, "title": clip.title,
                        "start": c["start"], "end": c["end"], "score": c["score"]})
    db.commit()
    return {"video_id": video_id, "created": len(created), "clips": created}
