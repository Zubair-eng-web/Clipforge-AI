import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.config import STORAGE_DIR
from backend.database.db import DB_PATH, get_db
from backend.database.models import Clip, Thumbnail, Video

router = APIRouter(prefix="/api/storage-manager", tags=["storage"])
ORPHAN_DIRS = ["generated_clips", "edited_clips", "thumbnails"]
CACHE_DIRS = {"previews": "previews", "temporary": "temporary"}


def _dir_size(path: Path) -> int:
    total = 0
    for dp, _d, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dp, f))
            except OSError:
                pass
    return total


def _inside_storage(p: Path) -> bool:
    try:
        p.resolve().relative_to(STORAGE_DIR.resolve())
        return True
    except ValueError:
        return False


def _safe_unlink(p: Path) -> int:
    """Deletes one file inside storage only. Returns freed bytes."""
    try:
        if p.is_file() and _inside_storage(p):
            size = p.stat().st_size
            p.unlink()
            return size
    except OSError:
        pass
    return 0


def _known_names(db: Session) -> set:
    names = set()
    for col in (Clip.file_path, Clip.thumbnail_path, Thumbnail.file_path, Video.stored_path, Video.proxy_path):
        for v in db.scalars(select(col)).all():
            if v:
                names.add(Path(v).name)
    return names


def _orphans(db: Session):
    known = _known_names(db)
    out = []
    for d in ORPHAN_DIRS:
        base = STORAGE_DIR / d
        if not base.is_dir():
            continue
        for f in base.iterdir():
            if f.is_file() and f.name not in known:
                out.append(f)
    return out


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    folders = []
    if STORAGE_DIR.is_dir():
        for d in sorted(STORAGE_DIR.iterdir()):
            if d.is_dir():
                folders.append({"name": d.name, "bytes": _dir_size(d)})
    orphans = _orphans(db)
    usage = shutil.disk_usage(STORAGE_DIR)
    return {
        "folders": folders,
        "total_bytes": sum(f["bytes"] for f in folders),
        "db_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "disk": {"total": usage.total, "used": usage.used, "free": usage.free},
        "orphan_files": len(orphans),
        "orphan_bytes": sum(f.stat().st_size for f in orphans if f.exists()),
        "previews_bytes": _dir_size(STORAGE_DIR / "previews") if (STORAGE_DIR / "previews").is_dir() else 0,
        "temporary_bytes": _dir_size(STORAGE_DIR / "temporary") if (STORAGE_DIR / "temporary").is_dir() else 0,
        "failed_clips": len(db.scalars(select(Clip.id).where(Clip.status.in_(["failed", "cancelled"]))).all()),
    }


class CleanupIn(BaseModel):
    target: str  # previews | temporary | orphans | failed_clips


@router.post("/cleanup")
def cleanup(body: CleanupIn, db: Session = Depends(get_db)):
    freed = 0
    count = 0
    t = body.target
    if t in CACHE_DIRS:
        base = STORAGE_DIR / CACHE_DIRS[t]
        if base.is_dir():
            for f in list(base.rglob("*")):
                n = _safe_unlink(f)
                if n or f.is_file():
                    freed += n
                    count += 1
        if t == "previews":
            db.execute(update(Video).values(proxy_path=None))
            db.commit()
    elif t == "orphans":
        for f in _orphans(db):
            freed += _safe_unlink(f)
            count += 1
    elif t == "failed_clips":
        for c in db.scalars(select(Clip).where(Clip.status.in_(["failed", "cancelled"]))).all():
            for p in (c.file_path, c.thumbnail_path):
                if p:
                    freed += _safe_unlink(Path(p) if Path(p).is_absolute() else STORAGE_DIR.parent / p)
            db.delete(c)
            count += 1
        db.commit()
    else:
        raise HTTPException(400, "Unknown cleanup target")
    return {"target": t, "files_or_items": count, "freed_bytes": freed}