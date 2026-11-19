import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.db import get_db
from backend.database.models import Job, Video
from backend.services.paths import resolve_storage

router = APIRouter(prefix="/api/videos", tags=["previews"])


def _proxy_file(v: Video):
    if not v.proxy_path:
        return None
    try:
        p = resolve_storage(v.proxy_path)
    except ValueError:
        return None
    return p if p.is_file() else None


@router.post("/{video_id}/proxy")
def request_proxy(video_id: int, db: Session = Depends(get_db)):
    """Make a browser-friendly preview copy (used when the original cannot play in the browser)."""
    v = db.get(Video, video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    if v.width is None:
        raise HTTPException(400, "Audio files do not need a video preview")
    if _proxy_file(v):
        return {"ready": True, "job_id": None}
    active = db.scalars(
        select(Job).where(Job.type == "proxy", Job.video_id == video_id, Job.status.in_(["queued", "processing"]))
    ).first()
    if active:
        return {"ready": False, "job_id": active.id}
    job = Job(type="proxy", video_id=video_id, status="queued", payload=json.dumps({"video_id": video_id}))
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"ready": False, "job_id": job.id}


@router.get("/{video_id}/proxy")
def get_proxy(video_id: int, db: Session = Depends(get_db)):
    v = db.get(Video, video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    p = _proxy_file(v)
    if not p:
        raise HTTPException(404, "Preview is not ready")
    return FileResponse(p, media_type="video/mp4")
