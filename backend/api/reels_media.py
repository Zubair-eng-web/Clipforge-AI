"""Reel media helpers: play a reel's video/thumbnail and find the clip behind a reel (for Publish)."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.database.db import get_db
from backend.database.models import Clip
from backend.services.paths import resolve_storage

router = APIRouter(prefix="/api/reels", tags=["reels-media"])


def _row(db: Session, rid: int):
    r = db.execute(text("SELECT file_path, thumbnail_path FROM reels WHERE id = :i"), {"i": rid}).first()
    if r is None:
        raise HTTPException(404, "Reel not found")
    return r


def _file(rel) -> Path:
    if not rel:
        raise HTTPException(404, "No file for this reel")
    try:
        p = resolve_storage(rel)
    except ValueError:
        raise HTTPException(400, "Invalid stored path")
    if not p.is_file():
        raise HTTPException(404, "File is missing on disk")
    return p


@router.get("/{rid}/stream")
def reel_stream(rid: int, db: Session = Depends(get_db)):
    return FileResponse(_file(_row(db, rid)[0]), media_type="video/mp4")


@router.get("/{rid}/thumbnail")
def reel_thumbnail(rid: int, db: Session = Depends(get_db)):
    return FileResponse(_file(_row(db, rid)[1]), media_type="image/jpeg")


@router.get("/{rid}/clip")
def reel_clip(rid: int, db: Session = Depends(get_db)):
    rel = _row(db, rid)[0]
    if not rel:
        raise HTTPException(404, "No file for this reel")
    c = db.scalars(select(Clip).where(Clip.file_path == rel)).first()
    if c is None:
        name = Path(rel).name
        c = db.scalars(select(Clip).where(Clip.file_path.like("%" + name))).first()
    if c is None:
        raise HTTPException(404, "No clip found for this reel")
    return {"clip_id": c.id, "status": c.status}