import json
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database.db import get_db
from backend.database.models import Clip, Job, Video
from backend.services.cleanup import delete_clip_files
from backend.services.paths import resolve_storage

router = APIRouter(prefix="/api/clips", tags=["clips"])
MIN_CLIP_SEC = 0.5


class ClipCreate(BaseModel):
    video_id: int
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    title: str = Field(default="", max_length=200)
    mode: Literal["accurate", "fast"] = "accurate"


def clip_dict(c: Clip) -> dict:
    return {
        "id": c.id,
        "video_id": c.video_id,
        "title": c.title,
        "start_sec": c.start_sec,
        "end_sec": c.end_sec,
        "duration_sec": c.duration_sec,
        "width": c.width,
        "height": c.height,
        "aspect_ratio": c.aspect_ratio,
        "status": c.status,
        "ai_score": c.ai_score,
        "has_file": bool(c.file_path),
        "has_thumbnail": bool(c.thumbnail_path),
        "created_at": c.created_at.isoformat(),
    }


def _mmss(sec: float) -> str:
    s = int(sec)
    return f"{s // 60}:{s % 60:02d}"


def _get_or_404(db: Session, clip_id: int) -> Clip:
    c = db.get(Clip, clip_id)
    if not c:
        raise HTTPException(404, "Clip not found")
    return c


def _file_or_404(rel, what: str) -> Path:
    if not rel:
        raise HTTPException(404, f"{what} is not ready")
    try:
        p = resolve_storage(rel)
    except ValueError:
        raise HTTPException(400, "Invalid stored path")
    if not p.is_file():
        raise HTTPException(404, f"{what} is missing on disk")
    return p


@router.post("")
def create_clip(body: ClipCreate, db: Session = Depends(get_db)):
    v = db.get(Video, body.video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    if v.width is None:
        raise HTTPException(400, "Clips can only be cut from video files (this file is audio only)")
    start, end = body.start_sec, body.end_sec
    if v.duration_sec is not None:
        if start >= v.duration_sec:
            raise HTTPException(400, "Start is beyond the end of the video")
        end = min(end, v.duration_sec)
    if end - start < MIN_CLIP_SEC:
        raise HTTPException(400, f"Clip must be at least {MIN_CLIP_SEC} seconds long")

    title = body.title.strip() or f"{Path(v.original_name).stem} ({_mmss(start)}-{_mmss(end)})"
    clip = Clip(video_id=v.id, title=title[:200], start_sec=round(start, 3), end_sec=round(end, 3),
                duration_sec=round(end - start, 3), status="pending")
    db.add(clip)
    db.flush()
    job = Job(type="clip_export", video_id=v.id, status="queued",
              payload=json.dumps({"clip_id": clip.id, "mode": body.mode}))
    db.add(job)
    db.commit()
    db.refresh(clip)
    db.refresh(job)
    return {"clip": clip_dict(clip), "job_id": job.id}


@router.get("")
def list_clips(video_id: int = 0, limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    stmt = select(Clip)
    if video_id:
        stmt = stmt.where(Clip.video_id == video_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Clip.id.desc()).limit(min(max(limit, 1), 500)).offset(max(offset, 0))
    ).all()
    return {"total": total, "items": [clip_dict(c) for c in rows]}


@router.get("/{clip_id}")
def get_clip(clip_id: int, db: Session = Depends(get_db)):
    return clip_dict(_get_or_404(db, clip_id))


@router.get("/{clip_id}/stream")
def stream_clip(clip_id: int, db: Session = Depends(get_db)):
    c = _get_or_404(db, clip_id)
    return FileResponse(_file_or_404(c.file_path, "Clip file"), media_type="video/mp4")


@router.get("/{clip_id}/download")
def download_clip(clip_id: int, db: Session = Depends(get_db)):
    c = _get_or_404(db, clip_id)
    p = _file_or_404(c.file_path, "Clip file")
    safe = re.sub(r"[^\w\-. ()]+", "_", c.title).strip(" .") or "clip"
    return FileResponse(p, media_type="video/mp4", filename=f"{safe}.mp4")


@router.get("/{clip_id}/thumbnail")
def clip_thumbnail(clip_id: int, db: Session = Depends(get_db)):
    c = _get_or_404(db, clip_id)
    return FileResponse(_file_or_404(c.thumbnail_path, "Thumbnail"), media_type="image/jpeg")


@router.delete("/{clip_id}")
def delete_clip(clip_id: int, db: Session = Depends(get_db)):
    c = _get_or_404(db, clip_id)
    if c.status in ("pending", "processing"):
        raise HTTPException(409, "Clip is still exporting. Cancel the job first.")
    delete_clip_files(c)
    db.delete(c)
    db.commit()
    return {"deleted": True, "id": clip_id}
