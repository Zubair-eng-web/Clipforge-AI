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

from backend.api.analysis import compat_router as analysis_compat_router
from backend.api.analysis import router as analysis_router
from backend.api.autoclips import router as autoclips_router
from backend.api.captions import router as captions_router
from backend.api.clips import router as clips_router
from backend.api.jobs import router as jobs_router
from backend.api.previews import router as previews_router
from backend.api.reframe import router as reframe_router
from backend.api.settings import router as settings_router
from backend.api.thumbnails import frame_router as thumb_frame_router
from backend.api.thumbnails import router as thumbnails_router
from backend.api.youtube import router as youtube_router
from backend.api.batch import router as batch_router
from backend.api.editor import clip_router as editor_clip_router
from backend.api.editor import router as editor_router
from backend.api.videos import router as videos_router
from backend.api.queue import router as queue_router
from backend.api.library import collections_router, history_router, projects_router
from backend.api.storage_manager import router as storage_router
from backend.api.analytics import router as analytics_router
from backend.api.diagnostics import router as diagnostics_router
from backend.api.scene_ai import router as scene_ai_router
from backend.api.gaming import router as gaming_router
import backend.workers.gaming_handlers  # noqa: F401
import backend.workers.reel_handlers  # noqa: F401
import backend.workers.batch_pipeline_handlers  # noqa: F401
import backend.workers.timeline_handlers  # noqa: F401
import backend.workers.compose_handlers  # noqa: F401
from backend.api.reels_studio import router as reels_studio_router
from backend.api.social import router as social_router
from backend.api.timeline import router as timeline_router
from backend.api.compose import router as compose_router
from backend.api.gemini_key import router as gemini_key_router
from backend.api.audio_studio import mcol_router, music_router, studio_router
from backend.api.studio_stats import router as phase12_router
from backend.config import STORAGE_DIR, ensure_storage_dirs
from backend.database.db import get_db, init_db
from backend.database.models import Clip, Job, Video
from backend.services.performance import startup_housekeeping
from backend.api.performance import router as performance_router
from backend.workers import runner


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_storage_dirs()
    init_db()
    startup_housekeeping()
    runner.start()
    yield
    runner.stop()


app = FastAPI(title="CLIPFORGE AI", version="0.4.0", lifespan=lifespan)

origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin, "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(videos_router)
app.include_router(gaming_router)
app.include_router(reels_studio_router)
app.include_router(social_router)
app.include_router(timeline_router)
app.include_router(compose_router)
app.include_router(gemini_key_router)
app.include_router(previews_router)
app.include_router(clips_router)
app.include_router(jobs_router)
app.include_router(analysis_router)
app.include_router(analysis_compat_router)
app.include_router(captions_router)
app.include_router(autoclips_router)
app.include_router(reframe_router)
app.include_router(settings_router)
app.include_router(thumb_frame_router)
app.include_router(thumbnails_router)
app.include_router(youtube_router)
app.include_router(batch_router)
app.include_router(editor_clip_router)
app.include_router(editor_router)
app.include_router(queue_router)
app.include_router(projects_router)
app.include_router(collections_router)
app.include_router(history_router)
app.include_router(storage_router)
app.include_router(analytics_router)
app.include_router(diagnostics_router)
app.include_router(scene_ai_router)
app.include_router(music_router)
app.include_router(mcol_router)
app.include_router(studio_router)
app.include_router(phase12_router)
app.include_router(performance_router)


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


from backend.api.reels_media import router as reels_media_router  # noqa: E402
app.include_router(reels_media_router)
