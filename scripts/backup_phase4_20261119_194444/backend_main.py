import os
from contextlib import asynccontextmanager
from pathlib import Path

import psutil
from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.clips import router as clips_router
from backend.api.jobs import router as jobs_router
from backend.api.previews import router as previews_router
from backend.api.videos import router as videos_router
from backend.config import STORAGE_DIR, ensure_storage_dirs
from backend.database.db import get_db, init_db
from backend.database.models import Clip, Job, Video
from backend.workers import runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_storage_dirs()
    init_db()
    runner.start()
    yield
    runner.stop()


app = FastAPI(title="CLIPFORGE AI", version="0.3.0", lifespan=lifespan)

origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin, "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(videos_router)
app.include_router(previews_router)
app.include_router(clips_router)
app.include_router(jobs_router)


def folder_size(path: Path) -> int:
    total = 0
    for dirpath, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total


@app.get("/api/health")
def health():
    mem = psutil.virtual_memory()
    return {"status": "ok", "app": "CLIPFORGE AI", "ram_used_percent": mem.percent}


@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db)):
    def count(model, *conds):
        stmt = select(func.count()).select_from(model)
        if conds:
            stmt = stmt.where(*conds)
        return db.scalar(stmt) or 0

    recent_videos = db.scalars(select(Video).order_by(Video.created_at.desc()).limit(5)).all()
    recent_clips = db.scalars(select(Clip).order_by(Clip.created_at.desc()).limit(5)).all()
    return {
        "total_videos": count(Video),
        "total_clips": count(Clip),
        "completed_jobs": count(Job, Job.status == "completed"),
        "processing_jobs": count(Job, Job.status == "processing"),
        "failed_jobs": count(Job, Job.status == "failed"),
        "storage_bytes": folder_size(STORAGE_DIR),
        "recent_videos": [
            {"id": v.id, "name": v.original_name, "created_at": v.created_at.isoformat()}
            for v in recent_videos
        ],
        "recent_clips": [
            {"id": c.id, "title": c.title, "created_at": c.created_at.isoformat()}
            for c in recent_clips
        ],
    }
