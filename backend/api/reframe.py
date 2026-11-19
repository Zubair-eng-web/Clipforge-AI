import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.clips import clip_dict
from backend.database.db import get_db
from backend.database.models import Clip, Job

router = APIRouter(prefix="/api/clips", tags=["reframing"])


class ReframeBody(BaseModel):
    ratio: Literal["9:16", "1:1", "16:9"] = "9:16"
    mode: Literal["face", "center", "blur"] = "face"


@router.post("/{clip_id}/reframe")
def reframe_clip(clip_id: int, body: Optional[ReframeBody] = None, db: Session = Depends(get_db)):
    body = body or ReframeBody()
    clip = db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(404, "Clip not found")
    if clip.status != "ready" or not clip.file_path:
        raise HTTPException(409, "The clip is not ready yet")
    new = Clip(video_id=clip.video_id, title=f"{clip.title} ({body.ratio})"[:200], start_sec=clip.start_sec,
               end_sec=clip.end_sec, duration_sec=clip.duration_sec, ai_score=clip.ai_score, status="pending")
    db.add(new)
    db.flush()
    job = Job(type="reframe", video_id=clip.video_id, status="queued",
              payload=json.dumps({"clip_id": clip.id, "new_clip_id": new.id, "ratio": body.ratio, "mode": body.mode}))
    db.add(job)
    db.commit()
    db.refresh(new)
    db.refresh(job)
    return {"clip": clip_dict(new), "clip_id": new.id, "job_id": job.id}