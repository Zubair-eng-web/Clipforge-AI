"""Job handler: reframe (convert a clip to 9:16, 1:1 or 16:9 as a NEW clip in storage/edited_clips)."""
import uuid

from backend import config
from backend.database.db import SessionLocal
from backend.database.models import Clip
from backend.reframing.reframe import reframe_video
from backend.services.paths import resolve_storage
from backend.video_processing.ffmpeg_service import FfmpegError, grab_frame
from backend.video_processing.ffprobe import probe
from backend.workers.caption_handlers import _aspect, _set_clip
from backend.workers.runner import JobCancelled, JobContext, register


@register("reframe")
def reframe(ctx: JobContext) -> None:
    src_id = int(ctx.payload["clip_id"])
    new_id = int(ctx.payload["new_clip_id"])
    ratio = ctx.payload.get("ratio", "9:16")
    mode = ctx.payload.get("mode", "face")

    with SessionLocal() as db:
        src_clip = db.get(Clip, src_id)
        new_clip = db.get(Clip, new_id)
        if src_clip is None or new_clip is None:
            raise RuntimeError("Clip record not found")
        if not src_clip.file_path:
            new_clip.status = "failed"
            db.commit()
            raise RuntimeError("The source clip has no file")
        rel = src_clip.file_path
        duration = float(src_clip.duration_sec or 0.0)
        w, h = src_clip.width, src_clip.height
        new_clip.status = "processing"
        db.commit()

    src = resolve_storage(rel)
    if not src.is_file():
        _set_clip(new_id, status="failed")
        raise RuntimeError("Clip file is missing on disk")

    name = uuid.uuid4().hex
    (config.STORAGE_DIR / "edited_clips").mkdir(parents=True, exist_ok=True)
    dst = config.STORAGE_DIR / "edited_clips" / f"{name}.mp4"
    thumb = config.STORAGE_DIR / "thumbnails" / f"{name}.jpg"
    try:
        if not w or not h or not duration:
            info0 = probe(src)
            w = w or info0["width"]
            h = h or info0["height"]
            duration = duration or float(info0["duration_sec"] or 0.0)
        reframe_video(src, dst, ratio, mode, duration, int(w), int(h), ctx.progress)
        info = probe(dst)
        thumb_ok = True
        try:
            grab_frame(dst, thumb, min(1.0, duration / 2))
        except FfmpegError:
            thumb_ok = False
        ok = _set_clip(
            new_id, status="ready", file_path=f"edited_clips/{name}.mp4",
            thumbnail_path=f"thumbnails/{name}.jpg" if thumb_ok else None,
            width=info["width"], height=info["height"], aspect_ratio=_aspect(info["width"], info["height"]),
            duration_sec=info["duration_sec"] or duration,
        )
        if not ok:
            raise RuntimeError("Clip was deleted while exporting")
    except JobCancelled:
        dst.unlink(missing_ok=True)
        thumb.unlink(missing_ok=True)
        _set_clip(new_id, status="cancelled")
        raise
    except Exception:
        dst.unlink(missing_ok=True)
        thumb.unlink(missing_ok=True)
        _set_clip(new_id, status="failed")
        raise