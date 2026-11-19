"""Job handlers: edit_clip (trim/speed/volume/fades/color) and merge_clips. Results are NEW clips in storage/edited_clips."""
import uuid

from backend import config
from backend.database.db import SessionLocal
from backend.database.models import Clip
from backend.editor.ops import edit_clip_file, merge_clips_files
from backend.services.paths import resolve_storage
from backend.video_processing.ffmpeg_service import FfmpegError, grab_frame
from backend.video_processing.ffprobe import probe
from backend.workers.caption_handlers import _aspect, _set_clip
from backend.workers.runner import JobCancelled, JobContext, register


def _targets():
    name = uuid.uuid4().hex
    (config.STORAGE_DIR / "edited_clips").mkdir(parents=True, exist_ok=True)
    return name, config.STORAGE_DIR / "edited_clips" / f"{name}.mp4", config.STORAGE_DIR / "thumbnails" / f"{name}.jpg"


def _finish_clip(new_id, name, dst, thumb, fallback_duration):
    info = probe(dst)
    thumb_ok = True
    try:
        grab_frame(dst, thumb, min(1.0, fallback_duration / 2))
    except FfmpegError:
        thumb_ok = False
    ok = _set_clip(
        new_id, status="ready", file_path=f"edited_clips/{name}.mp4",
        thumbnail_path=f"thumbnails/{name}.jpg" if thumb_ok else None,
        width=info["width"], height=info["height"], aspect_ratio=_aspect(info["width"], info["height"]),
        duration_sec=info["duration_sec"] or fallback_duration,
    )
    if not ok:
        raise RuntimeError("Clip was deleted while exporting")


@register("edit_clip")
def edit_clip(ctx: JobContext) -> None:
    src_id = int(ctx.payload["clip_id"])
    new_id = int(ctx.payload["new_clip_id"])
    ops = ctx.payload.get("ops") or {}

    with SessionLocal() as db:
        src_clip = db.get(Clip, src_id)
        new_clip = db.get(Clip, new_id)
        if src_clip is None or new_clip is None:
            raise RuntimeError("Clip record not found")
        if not src_clip.file_path:
            new_clip.status = "failed"
            db.commit()
            raise RuntimeError("The source clip has no file")
        rel, clip_dur = src_clip.file_path, float(src_clip.duration_sec or 0.0)
        new_clip.status = "processing"
        db.commit()

    src = resolve_storage(rel)
    if not src.is_file():
        _set_clip(new_id, status="failed")
        raise RuntimeError("Clip file is missing on disk")

    name, dst, thumb = _targets()
    try:
        if not clip_dur:
            clip_dur = float(probe(src)["duration_sec"] or 0.0)
        start = float(ops.get("trim_start", 0.0))
        end = ops.get("trim_end")
        end = min(float(end), clip_dur) if end is not None else clip_dur
        if end - start < 0.5:
            raise RuntimeError("Trimmed clip must be at least 0.5 seconds long")
        out_dur = edit_clip_file(src, dst, start, end, ops, ctx.progress)
        _finish_clip(new_id, name, dst, thumb, out_dur)
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


@register("merge_clips")
def merge_clips(ctx: JobContext) -> None:
    ids = [int(i) for i in ctx.payload["clip_ids"]]
    new_id = int(ctx.payload["new_clip_id"])
    ratio = ctx.payload.get("ratio", "first")

    with SessionLocal() as db:
        new_clip = db.get(Clip, new_id)
        clips = [db.get(Clip, i) for i in ids]
        if new_clip is None:
            raise RuntimeError("Clip record not found")
        if any(c is None or not c.file_path for c in clips):
            new_clip.status = "failed"
            db.commit()
            raise RuntimeError("One of the clips is missing or not ready")
        rels = [c.file_path for c in clips]
        durs = [float(c.duration_sec or 0.0) for c in clips]
        first_size = (clips[0].width, clips[0].height)
        new_clip.status = "processing"
        db.commit()

    srcs = [resolve_storage(r) for r in rels]
    if any(not s.is_file() for s in srcs):
        _set_clip(new_id, status="failed")
        raise RuntimeError("A clip file is missing on disk")

    name, dst, thumb = _targets()
    try:
        for i, s in enumerate(srcs):
            if not durs[i]:
                durs[i] = float(probe(s)["duration_sec"] or 0.0)
        if not first_size[0] or not first_size[1]:
            info0 = probe(srcs[0])
            first_size = (info0["width"], info0["height"])
        total = merge_clips_files(srcs, durs, dst, ratio, first_size, ctx.progress)
        _finish_clip(new_id, name, dst, thumb, total)
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