"""Job handler 'youtube_import': download a link into storage/original_videos and create a Video row."""
import shutil
import uuid

from sqlalchemy import update

from backend import config
from backend.database.db import SessionLocal
from backend.database.models import Job, Video
from backend.importers.youtube import YoutubeError, check_limits, download_video, fetch_info
from backend.video_processing.ffprobe import probe
from backend.workers.runner import JobCancelled, JobContext, register


@register("youtube_import")
def youtube_import(ctx: JobContext) -> None:
    url = str(ctx.payload["url"])
    check_limits(fetch_info(url))

    name = uuid.uuid4().hex
    tmp_dir = config.STORAGE_DIR / "temporary" / name
    tmp_dir.mkdir(parents=True, exist_ok=True)
    cancelled = {"v": False}

    def cb(p: float) -> None:
        try:
            ctx.progress(min(p, 1.0) * 0.95)
        except JobCancelled:
            cancelled["v"] = True
            raise

    final = None
    try:
        path, title = download_video(url, tmp_dir, name, cb)
        ext = path.suffix.lower()
        if ext not in config.ALLOWED_EXTENSIONS:
            raise YoutubeError(f"Downloaded file type '{ext}' is not supported")
        info = probe(path)
        size = path.stat().st_size
        final_name = f"{uuid.uuid4().hex}{ext}"
        final = config.STORAGE_DIR / "original_videos" / final_name
        shutil.move(str(path), str(final))
        with SessionLocal() as db:
            v = Video(
                original_name=config.safe_display_name(f"{title}{ext}"),
                stored_path=f"original_videos/{final_name}",
                size_bytes=size, duration_sec=info["duration_sec"], width=info["width"], height=info["height"],
                format=ext.lstrip("."), status="uploaded",
            )
            db.add(v)
            db.commit()
            db.refresh(v)
            db.execute(update(Job).where(Job.id == ctx.job_id).values(video_id=v.id))
            db.commit()
    except JobCancelled:
        if final is not None:
            final.unlink(missing_ok=True)
        raise
    except Exception:
        if final is not None:
            final.unlink(missing_ok=True)
        if cancelled["v"]:
            raise JobCancelled()
        raise
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)