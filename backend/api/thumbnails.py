import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from backend import config
from backend.database.db import get_db
from backend.database.models import Clip, Thumbnail
from backend.services.paths import resolve_storage
from backend.video_processing.ffmpeg_service import FfmpegError
from backend.video_processing.frames import grab_frame_hd

router = APIRouter(prefix="/api/thumbnails", tags=["thumbnails"])
frame_router = APIRouter(prefix="/api/clips", tags=["thumbnails"])
MAX_BYTES = 15 * 1024 * 1024


def _dict(t: Thumbnail) -> dict:
    return {"id": t.id, "clip_id": t.clip_id, "title": t.title, "created_at": t.created_at.isoformat()}


def _get(db: Session, thumb_id: int) -> Thumbnail:
    t = db.get(Thumbnail, thumb_id)
    if not t:
        raise HTTPException(404, "Thumbnail not found")
    return t


def _file(t: Thumbnail):
    try:
        p = resolve_storage(t.file_path)
    except ValueError:
        raise HTTPException(400, "Invalid stored path")
    if not p.is_file():
        raise HTTPException(404, "Thumbnail file is missing on disk")
    return p


@frame_router.get("/{clip_id}/frame")
def clip_frame(clip_id: int, t: float = 0.0, db: Session = Depends(get_db)):
    """One full-size frame of a ready clip at time t (seconds). Temporary file is removed after sending."""
    clip = db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(404, "Clip not found")
    if clip.status != "ready" or not clip.file_path:
        raise HTTPException(409, "The clip is not ready yet")
    try:
        src = resolve_storage(clip.file_path)
    except ValueError:
        raise HTTPException(400, "Invalid stored path")
    if not src.is_file():
        raise HTTPException(404, "Clip file is missing on disk")
    at = min(max(t, 0.0), max((clip.duration_sec or 0.0) - 0.05, 0.0))
    tmp = config.STORAGE_DIR / "temporary" / f"{uuid.uuid4().hex}.jpg"
    try:
        grab_frame_hd(src, tmp, at)
    except FfmpegError as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(500, f"Could not read a frame: {e}")
    return FileResponse(tmp, media_type="image/jpeg", background=BackgroundTask(lambda: tmp.unlink(missing_ok=True)))


@router.get("")
def list_thumbnails(limit: int = 200, db: Session = Depends(get_db)):
    rows = db.scalars(select(Thumbnail).order_by(Thumbnail.id.desc()).limit(min(max(limit, 1), 500))).all()
    return {"items": [_dict(t) for t in rows]}


@router.post("")
def save_thumbnail(
    file: UploadFile = File(...),
    title: str = Form(""),
    clip_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image is larger than 15 MB")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        ext = ".png"
    elif data.startswith(b"\xff\xd8\xff"):
        ext = ".jpg"
    else:
        raise HTTPException(400, "Only PNG or JPEG images are accepted")
    if clip_id is not None and db.get(Clip, clip_id) is None:
        clip_id = None
    (config.STORAGE_DIR / "thumbnails").mkdir(parents=True, exist_ok=True)
    rel = f"thumbnails/studio_{uuid.uuid4().hex}{ext}"
    path = config.STORAGE_DIR / rel
    path.write_bytes(data)
    try:
        t = Thumbnail(clip_id=clip_id, title=title.strip()[:300], file_path=rel)
        db.add(t)
        db.commit()
        db.refresh(t)
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return _dict(t)


@router.get("/{thumb_id}/file")
def thumbnail_file(thumb_id: int, db: Session = Depends(get_db)):
    t = _get(db, thumb_id)
    p = _file(t)
    return FileResponse(p, media_type="image/png" if p.suffix == ".png" else "image/jpeg")


@router.get("/{thumb_id}/download")
def thumbnail_download(thumb_id: int, db: Session = Depends(get_db)):
    t = _get(db, thumb_id)
    p = _file(t)
    safe = re.sub(r"[^\w\-. ()]+", "_", t.title).strip(" .") or "thumbnail"
    return FileResponse(p, media_type="image/png" if p.suffix == ".png" else "image/jpeg",
                        filename=f"{safe[:80]}{p.suffix}")


@router.delete("/{thumb_id}")
def delete_thumbnail(thumb_id: int, db: Session = Depends(get_db)):
    t = _get(db, thumb_id)
    try:
        resolve_storage(t.file_path).unlink(missing_ok=True)
    except (ValueError, OSError):
        pass
    db.delete(t)
    db.commit()
    return {"deleted": True, "id": thumb_id}