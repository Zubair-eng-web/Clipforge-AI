import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import config
from backend.database.db import get_db
from backend.database.models import Video
from backend.video_processing.ffprobe import ProbeError, probe

router = APIRouter(prefix="/api/videos", tags=["videos"])
CHUNK = 1024 * 1024


class UploadRejected(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message


def video_dict(v: Video) -> dict:
    return {
        "id": v.id,
        "name": v.original_name,
        "size_bytes": v.size_bytes,
        "duration_sec": v.duration_sec,
        "width": v.width,
        "height": v.height,
        "format": v.format,
        "status": v.status,
        "has_video": v.width is not None,
        "created_at": v.created_at.isoformat(),
    }


def _save_one(upload: UploadFile, db: Session) -> dict:
    display = config.safe_display_name(upload.filename or "")
    ext = Path(display).suffix.lower()
    if ext not in config.ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(config.ALLOWED_EXTENSIONS))
        raise UploadRejected("bad_type", f"Unsupported file type '{ext or 'none'}'. Allowed: {allowed}")

    tmp = config.STORAGE_DIR / "temporary" / f"{uuid.uuid4().hex}.part"
    limit = config.max_upload_bytes()
    size = 0
    try:
        with open(tmp, "wb") as out:
            while True:
                chunk = upload.file.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise UploadRejected("too_large", "File is larger than the allowed upload limit (MAX_UPLOAD_GB in .env)")
                out.write(chunk)
        if size == 0:
            raise UploadRejected("empty", "File is empty")
        try:
            info = probe(tmp)
        except ProbeError as e:
            raise UploadRejected("invalid_media", str(e))

        final_name = f"{uuid.uuid4().hex}{ext}"
        final = config.STORAGE_DIR / "original_videos" / final_name
        shutil.move(str(tmp), str(final))
    finally:
        tmp.unlink(missing_ok=True)

    try:
        v = Video(
            original_name=display,
            stored_path=f"original_videos/{final_name}",
            size_bytes=size,
            duration_sec=info["duration_sec"],
            width=info["width"],
            height=info["height"],
            format=ext.lstrip("."),
            status="uploaded",
        )
        db.add(v)
        db.commit()
        db.refresh(v)
    except Exception:
        db.rollback()
        final.unlink(missing_ok=True)
        raise
    return video_dict(v)


@router.post("/upload")
def upload_videos(files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    uploaded, errors = [], []
    for f in files:
        try:
            uploaded.append(_save_one(f, db))
        except UploadRejected as e:
            errors.append({"filename": f.filename, "code": e.code, "error": e.message})
    if uploaded or not errors:
        status = 200
    elif any(e["code"] == "too_large" for e in errors):
        status = 413
    else:
        status = 400
    return JSONResponse({"uploaded": uploaded, "errors": errors}, status_code=status)


@router.get("")
def list_videos(q: str = "", format: str = "", limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    stmt = select(Video)
    if q.strip():
        stmt = stmt.where(Video.original_name.contains(q.strip(), autoescape=True))
    if format:
        stmt = stmt.where(Video.format == format.lower().lstrip("."))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Video.created_at.desc(), Video.id.desc())
        .limit(min(max(limit, 1), 500))
        .offset(max(offset, 0))
    ).all()
    return {"total": total, "items": [video_dict(v) for v in rows]}


def _get_or_404(db: Session, video_id: int) -> Video:
    v = db.get(Video, video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    return v


def _resolve(v: Video) -> Path:
    base = config.STORAGE_DIR.resolve()
    p = (base / v.stored_path).resolve()
    if base not in p.parents:
        raise HTTPException(400, "Invalid stored path")
    return p


@router.get("/{video_id}")
def get_video(video_id: int, db: Session = Depends(get_db)):
    return video_dict(_get_or_404(db, video_id))


@router.get("/{video_id}/stream")
def stream_video(video_id: int, db: Session = Depends(get_db)):
    v = _get_or_404(db, video_id)
    p = _resolve(v)
    if not p.is_file():
        raise HTTPException(404, "File is missing on disk")
    return FileResponse(p, media_type=config.MEDIA_TYPES.get(p.suffix.lower(), "application/octet-stream"))


@router.delete("/{video_id}")
def delete_video(video_id: int, db: Session = Depends(get_db)):
    v = _get_or_404(db, video_id)
    _resolve(v).unlink(missing_ok=True)
    db.delete(v)
    db.commit()
    return {"deleted": True, "id": video_id}