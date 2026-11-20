import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import config
from backend.database import models
from backend.database.db import get_db
from backend.database.models_phase12 import Reel
from backend.services.paths import resolve_storage

router = APIRouter(tags=["phase12"])


def _count(db: Session, model, *conds) -> int:
    stmt = select(func.count()).select_from(model)
    if conds:
        stmt = stmt.where(*conds)
    return db.scalar(stmt) or 0


def _folder_size(path: Path) -> int:
    total = 0
    for dirpath, _d, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else None


def _recent_files(folders, limit=5):
    items = []
    for folder in folders:
        base = config.STORAGE_DIR / folder
        if not base.exists():
            continue
        for dirpath, _d, files in os.walk(base):
            for name in files:
                fp = Path(dirpath) / name
                try:
                    st = fp.stat()
                except OSError:
                    continue
                items.append((st.st_mtime, folder, name, st.st_size))
    items.sort(reverse=True)
    return [
        {"name": n, "folder": f, "size_bytes": s,
         "modified": datetime.fromtimestamp(m, timezone.utc).isoformat()}
        for m, f, n, s in items[:limit]
    ]


@router.get("/api/studio/stats")
def studio_stats(db: Session = Depends(get_db)):
    storage = config.STORAGE_DIR
    by_folder = {d: (_folder_size(storage / d) if (storage / d).exists() else 0) for d in config.SUBDIRS}
    projects = db.scalars(select(models.Project).order_by(models.Project.id.desc()).limit(5)).all()
    return {
        "videos": _count(db, models.Video),
        "clips": _count(db, models.Clip),
        "reels": _count(db, Reel),
        "captions": _count(db, models.ClipCaption),
        "music_tracks": _count(db, models.MusicTrack),
        "highlights": _count(db, models.Highlight),
        "processing_jobs": _count(db, models.Job, models.Job.status == "processing"),
        "queued_jobs": _count(db, models.Job, models.Job.status.in_(["queued", "pending"])),
        "storage_bytes": _folder_size(storage),
        "storage_by_folder": by_folder,
        "recent_projects": [
            {"id": p.id,
             "name": getattr(p, "name", None) or getattr(p, "title", None) or f"Project {p.id}",
             "created_at": _iso(getattr(p, "created_at", None))}
            for p in projects
        ],
        "recent_exports": _recent_files(["reels", "exports", "edited_clips"]),
    }


@router.get("/api/about")
def about():
    return {
        "name": "CLIPFORGE AI",
        "tagline": "Turn Long Videos Into Powerful Clips.",
        "version": "0.12.0-dev",
        "mode": "Local-first: Windows PC, CPU only, no cloud deployment",
        "python": sys.version.split()[0],
        "features": [
            "Upload and YouTube import (authorized sources only)",
            "AI analysis, highlights, auto clipper, scene detection",
            "Smart captions, reframing, video editor, thumbnails, batch",
            "Custom music library and audio studio",
            "Reels and Shorts studio (Phase 12, in progress)",
        ],
        "rules": [
            "Original videos are never modified.",
            "Captions come only from real speech or user-written text.",
            "Music comes only from your own library; nothing is downloaded or applied without approval.",
            "No fake analytics: only real measured data.",
        ],
        "notice": "Only process videos and music you own or are allowed to use. Game footage (for example GTA 6) is copyrighted: follow the publisher and platform content policies.",
    }


def _reel_dict(r: Reel) -> dict:
    return {
        "id": r.id, "video_id": r.video_id, "source_clip_id": r.source_clip_id,
        "title": r.title, "platform": r.platform, "aspect": r.aspect,
        "width": r.width, "height": r.height,
        "start_sec": r.start_sec, "end_sec": r.end_sec, "duration_sec": r.duration_sec,
        "file_path": r.file_path, "thumbnail_path": r.thumbnail_path,
        "status": r.status, "created_at": _iso(r.created_at),
    }


def _safe_unlink(rel):
    if not rel:
        return
    try:
        p = resolve_storage(rel)
    except ValueError:
        return
    allowed = [(config.STORAGE_DIR / "reels").resolve(), (config.STORAGE_DIR / "thumbnails").resolve()]
    if any(a in p.parents for a in allowed) and p.is_file():
        try:
            p.unlink()
        except OSError:
            pass


@router.get("/api/reels")
def list_reels(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.scalars(select(Reel).order_by(Reel.id.desc()).limit(max(1, min(limit, 500)))).all()
    return [_reel_dict(r) for r in rows]


@router.get("/api/reels/{reel_id}")
def get_reel(reel_id: int, db: Session = Depends(get_db)):
    r = db.get(Reel, reel_id)
    if not r:
        raise HTTPException(404, "Reel not found")
    return _reel_dict(r)


@router.delete("/api/reels/{reel_id}")
def delete_reel(reel_id: int, db: Session = Depends(get_db)):
    r = db.get(Reel, reel_id)
    if not r:
        raise HTTPException(404, "Reel not found")
    _safe_unlink(r.file_path)
    _safe_unlink(r.thumbnail_path)
    db.delete(r)
    db.commit()
    return {"deleted": reel_id}