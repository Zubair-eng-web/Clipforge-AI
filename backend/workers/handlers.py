"""Job handlers: clip_export and proxy (browser preview)."""
import re
import uuid

from backend import config
from backend.database.db import SessionLocal
from backend.database.models import Clip, Video
from backend.services.paths import resolve_storage
from backend.video_processing.ffmpeg_service import FfmpegError, cut_clip, grab_frame, make_proxy
from backend.video_processing.ffprobe import probe
from backend.workers.runner import JobCancelled, JobContext, register


def _aspect(w, h):
    if not w or not h:
        return None
    r = w / h
    for name, val in (("16:9", 16 / 9), ("9:16", 9 / 16), ("1:1", 1.0), ("4:3", 4 / 3), ("3:4", 3 / 4), ("21:9", 21 / 9)):
        if abs(r - val) < 0.03:
            return name
    return "custom"


def _set_clip(clip_id: int, **values) -> bool:
    with SessionLocal() as db:
        clip = db.get(Clip, clip_id)
        if clip is None:
            return False
        for k, v in values.items():
            setattr(clip, k, v)
        db.commit()
        return True


def _unlink(*paths) -> None:
    for p in paths:
        if p is not None:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


@register("clip_export")
def clip_export(ctx: JobContext) -> None:
    clip_id = int(ctx.payload["clip_id"])
    mode = ctx.payload.get("mode", "accurate")
    with SessionLocal() as db:
        clip = db.get(Clip, clip_id)
        if clip is None:
            raise RuntimeError("Clip record not found")
        video = db.get(Video, clip.video_id)
        if video is None:
            raise RuntimeError("Source video not found")
        stored = video.stored_path
        start, end = clip.start_sec, clip.end_sec
        clip.status = "processing"
        db.commit()

    src = resolve_storage(stored)
    if not src.is_file():
        _set_clip(clip_id, status="failed")
        raise RuntimeError("Source video file is missing on disk")

    name = uuid.uuid4().hex
    _cat = re.sub(r"[^a-z0-9_]", "", str(ctx.payload.get("category") or "").lower())
    _fn = re.sub(r"[^A-Za-z0-9_\-]", "", str(ctx.payload.get("filename") or ""))
    _rel = f"generated_clips/{_cat}/{_fn}.mp4" if _cat and _fn else f"generated_clips/{name}.mp4"
    dst = config.STORAGE_DIR / _rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    thumb = config.STORAGE_DIR / "thumbnails" / f"{name}.jpg"
    try:
        if mode == "fast":
            try:
                cut_clip(src, dst, start, end, "fast", ctx.progress)
            except FfmpegError:  # codec not allowed in MP4 container: fall back to re-encode
                _unlink(dst)
                cut_clip(src, dst, start, end, "accurate", ctx.progress)
        else:
            cut_clip(src, dst, start, end, "accurate", ctx.progress)

        info = probe(dst)
        thumb_ok = True
        try:
            grab_frame(dst, thumb, min(1.0, (end - start) / 2))
        except FfmpegError:
            thumb_ok = False

        ok = _set_clip(
            clip_id,
            status="ready",
            file_path=_rel,
            thumbnail_path=f"thumbnails/{name}.jpg" if thumb_ok else None,
            width=info["width"],
            height=info["height"],
            aspect_ratio=_aspect(info["width"], info["height"]),
            duration_sec=info["duration_sec"] or (end - start),
        )
        if not ok:
            raise RuntimeError("Clip was deleted while exporting")
    except JobCancelled:
        _unlink(dst, thumb)
        _set_clip(clip_id, status="cancelled")
        raise
    except Exception:
        _unlink(dst, thumb)
        _set_clip(clip_id, status="failed")
        raise


@register("proxy")
def build_proxy(ctx: JobContext) -> None:
    video_id = int(ctx.payload["video_id"])
    with SessionLocal() as db:
        v = db.get(Video, video_id)
        if v is None:
            raise RuntimeError("Video not found")
        stored, duration = v.stored_path, (v.duration_sec or 0.0)
    src = resolve_storage(stored)
    if not src.is_file():
        raise RuntimeError("Source video file is missing on disk")

    (config.STORAGE_DIR / "previews").mkdir(parents=True, exist_ok=True)
    rel = f"previews/{uuid.uuid4().hex}.mp4"
    dst = config.STORAGE_DIR / rel
    try:
        make_proxy(src, dst, duration, ctx.progress)
    except BaseException:
        _unlink(dst)
        raise

    old = None
    with SessionLocal() as db:
        v = db.get(Video, video_id)
        if v is None:
            _unlink(dst)
            raise RuntimeError("Video was deleted while building preview")
        old, v.proxy_path = v.proxy_path, rel
        db.commit()
    if old:
        try:
            _unlink(resolve_storage(old))
        except ValueError:
            pass


from backend.workers import analysis_handlers  # noqa: F401,E402  (registers the 'analyze' job)
from backend.workers import caption_handlers  # noqa: F401,E402  (registers caption jobs)
