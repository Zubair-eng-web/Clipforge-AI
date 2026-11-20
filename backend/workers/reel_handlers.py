"""Job handler: reel_create (clip -> platform reel as a NEW clip in storage/edited_clips)."""
import json
import logging
import uuid

from backend import config
from backend.database.db import SessionLocal
from backend.database.models import Clip, MusicTrack
from backend.reels.engine import build_reel
from backend.services.paths import resolve_storage
from backend.video_processing.ffmpeg_service import FfmpegError, grab_frame
from backend.video_processing.ffprobe import probe
from backend.workers.caption_handlers import _aspect, _set_clip
from backend.workers.runner import JobCancelled, JobContext, register

log = logging.getLogger("clipforge.reels")


def _save_reel_row(values: dict):
    """Best effort: fills only the columns that exist in models_phase12.Reel. Never breaks the job."""
    try:
        from backend.database import models_phase12 as m12
        Reel = getattr(m12, "Reel", None)
        if Reel is None:
            return None
        cols = set(Reel.__table__.columns.keys())
        data = {k: v for k, v in values.items() if k in cols}
        with SessionLocal() as db:
            r = Reel(**data)
            db.add(r)
            db.commit()
            return r.id
    except Exception:
        log.exception("could not save reel row (the reel clip itself is fine)")
        return None


def _num(v, d):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


@register("reel_create")
def reel_create(ctx: JobContext) -> None:
    p = ctx.payload
    src_id = int(p["clip_id"])
    new_id = int(p["new_clip_id"])
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
        video_id = src_clip.video_id
        title = new_clip.title
        music_rows = []
        for m in p.get("music") or []:
            t = db.get(MusicTrack, int(m["track_id"]))
            if t is None:
                new_clip.status = "failed"
                db.commit()
                raise RuntimeError(f"Music track {m['track_id']} not found")
            music_rows.append((m, t.file_path, t.duration_sec))
        new_clip.status = "processing"
        db.commit()

    src = resolve_storage(rel)
    if not src.is_file():
        _set_clip(new_id, status="failed")
        raise RuntimeError("Clip file is missing on disk")

    name = uuid.uuid4().hex
    (config.STORAGE_DIR / "edited_clips").mkdir(parents=True, exist_ok=True)
    (config.STORAGE_DIR / "thumbnails").mkdir(parents=True, exist_ok=True)
    dst = config.STORAGE_DIR / "edited_clips" / f"{name}.mp4"
    thumb = config.STORAGE_DIR / "thumbnails" / f"{name}.jpg"
    try:
        if not w or not h or not duration:
            info0 = probe(src)
            w = w or info0["width"]
            h = h or info0["height"]
            duration = duration or float(info0["duration_sec"] or 0.0)
        tracks = []
        for m, trel, tdur in music_rows:
            tp = resolve_storage(trel)
            if not tp.is_file():
                raise RuntimeError("A music file is missing on disk")
            if not tdur:
                tdur = float(probe(tp)["duration_sec"] or 0.0)
            tracks.append({
                "path": str(tp), "tdur": float(tdur), "volume": _num(m.get("volume"), 0.6),
                "start": _num(m.get("start"), 0.0), "trim_in": _num(m.get("trim_in"), 0.0),
                "trim_out": _num(m.get("trim_out"), 0.0), "fade_in": _num(m.get("fade_in"), 1.0),
                "fade_out": _num(m.get("fade_out"), 1.5), "loop": bool(m.get("loop", True)),
            })
        res = build_reel(
            src, dst, src_duration=duration, w=int(w), h=int(h),
            ratio=p.get("ratio", "9:16"), size=p.get("size", "1080"), mode=p.get("mode", "face"),
            cx=p.get("cx"), cy=p.get("cy"), target_sec=p.get("target_sec"),
            trim_dead=bool(p.get("trim_dead_time", True)), start=p.get("start_sec"), end=p.get("end_sec"),
            brightness=_num(p.get("brightness"), 0.0), contrast=_num(p.get("contrast"), 1.0),
            saturation=_num(p.get("saturation"), 1.0), music=tracks or None,
            orig_on=bool(p.get("original_audio_on", True)), orig_volume=_num(p.get("original_volume"), 1.0),
            on_progress=ctx.progress,
        )
        info = probe(dst)
        thumb_ok = True
        try:
            grab_frame(dst, thumb, min(1.0, res["duration"] / 2))
        except FfmpegError:
            thumb_ok = False
        ok = _set_clip(
            new_id, status="ready", file_path=f"edited_clips/{name}.mp4",
            thumbnail_path=f"thumbnails/{name}.jpg" if thumb_ok else None,
            width=info["width"], height=info["height"], aspect_ratio=_aspect(info["width"], info["height"]),
            duration_sec=info["duration_sec"] or res["duration"],
        )
        if not ok:
            raise RuntimeError("Clip was deleted while exporting")
        _save_reel_row({
            "title": title, "clip_id": new_id, "source_clip_id": src_id, "video_id": video_id,
            "platform": p.get("platform"), "ratio": p.get("ratio"), "status": "ready",
            "duration_sec": info["duration_sec"] or res["duration"], "width": info["width"],
            "height": info["height"], "file_path": f"edited_clips/{name}.mp4",
            "thumbnail_path": f"thumbnails/{name}.jpg" if thumb_ok else None,
            "settings_json": json.dumps({"request": p, "result": res}),
        })
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