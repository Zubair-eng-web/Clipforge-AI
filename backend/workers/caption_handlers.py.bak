"""Job handlers: caption_generate (word-level captions for a clip) and caption_burn (captions burned into video)."""
import json
import shutil
import uuid

from sqlalchemy import select

from backend import config
from backend.audio_processing.word_transcribe import transcribe_words
from backend.captions.builder import build_lines, to_ass
from backend.captions.burn import burn_captions
from backend.database.db import SessionLocal
from backend.database.models import Clip, ClipCaption
from backend.services.paths import resolve_storage
from backend.video_processing.ffmpeg_service import FfmpegError, grab_frame
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


@register("caption_generate")
def caption_generate(ctx: JobContext) -> None:
    clip_id = int(ctx.payload["clip_id"])
    language = ctx.payload.get("language") or None
    if language == "auto":
        language = None
    with SessionLocal() as db:
        clip = db.get(Clip, clip_id)
        if clip is None or not clip.file_path:
            raise RuntimeError("Clip not found or not ready")
        rel, duration = clip.file_path, float(clip.duration_sec or 0.0)
    src = resolve_storage(rel)
    if not src.is_file():
        raise RuntimeError("Clip file is missing on disk")

    result = transcribe_words(src, duration, ctx.progress, language)
    lines = build_lines(result["words"])
    payload = json.dumps(lines, ensure_ascii=False)
    with SessionLocal() as db:
        row = db.scalar(select(ClipCaption).where(ClipCaption.clip_id == clip_id))
        if row is None:
            db.add(ClipCaption(clip_id=clip_id, language=result.get("language"), lines_json=payload))
        else:
            row.language = result.get("language")
            row.lines_json = payload
        db.commit()


@register("caption_burn")
def caption_burn(ctx: JobContext) -> None:
    src_id = int(ctx.payload["clip_id"])
    new_id = int(ctx.payload["new_clip_id"])
    style = ctx.payload.get("style", "classic")
    position = ctx.payload.get("position", "bottom")
    font_size = ctx.payload.get("font_size")

    with SessionLocal() as db:
        src_clip = db.get(Clip, src_id)
        new_clip = db.get(Clip, new_id)
        if src_clip is None or new_clip is None:
            raise RuntimeError("Clip record not found")
        cap = db.scalar(select(ClipCaption).where(ClipCaption.clip_id == src_id))
        if cap is None or not src_clip.file_path:
            new_clip.status = "failed"
            db.commit()
            raise RuntimeError("This clip has no captions yet")
        rel, duration = src_clip.file_path, float(src_clip.duration_sec or 0.0)
        w, h = src_clip.width, src_clip.height
        lines = json.loads(cap.lines_json or "[]")
        new_clip.status = "processing"
        db.commit()

    src = resolve_storage(rel)
    if not src.is_file():
        _set_clip(new_id, status="failed")
        raise RuntimeError("Clip file is missing on disk")
    if not w or not h:
        info0 = probe(src)
        w, h = info0["width"], info0["height"]

    name = uuid.uuid4().hex
    (config.STORAGE_DIR / "edited_clips").mkdir(parents=True, exist_ok=True)
    dst = config.STORAGE_DIR / "edited_clips" / f"{name}.mp4"
    thumb = config.STORAGE_DIR / "thumbnails" / f"{name}.jpg"
    work = config.STORAGE_DIR / "temporary" / name
    try:
        work.mkdir(parents=True, exist_ok=True)
        ass = work / "captions.ass"
        ass.write_text(to_ass(lines, int(w), int(h), style, position, font_size=font_size), encoding="utf-8")
        burn_captions(src, ass, dst, duration, ctx.progress)
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
    finally:
        shutil.rmtree(work, ignore_errors=True)