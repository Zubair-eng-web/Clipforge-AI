"""Job handler: timeline_clips (segments of ready clips -> ONE new clip in storage/edited_clips)."""
from backend.database.db import SessionLocal
from backend.database.models import Clip
from backend.editor.timeline import build_timeline
from backend.reframing.reframe import RATIOS
from backend.services.paths import resolve_storage
from backend.video_processing.ffprobe import probe
from backend.workers.caption_handlers import _set_clip
from backend.workers.editor_handlers import _finish_clip, _targets
from backend.workers.runner import JobCancelled, JobContext, register


@register("timeline_clips")
def timeline_clips(ctx: JobContext) -> None:
    p = ctx.payload
    new_id = int(p["new_clip_id"])
    ratio = p.get("ratio", "first")
    transition = p.get("transition", "none")
    tsec = float(p.get("transition_sec", 0.5))
    rows = []
    with SessionLocal() as db:
        new_clip = db.get(Clip, new_id)
        if new_clip is None:
            raise RuntimeError("Clip record not found")
        for s in p["segments"]:
            c = db.get(Clip, int(s["clip_id"]))
            if c is None or not c.file_path:
                new_clip.status = "failed"
                db.commit()
                raise RuntimeError("One of the clips is missing or not ready")
            rows.append((c.file_path, float(s.get("start", 0.0)), s.get("end"),
                         float(c.duration_sec or 0.0), c.width, c.height))
        new_clip.status = "processing"
        db.commit()
    paths = [resolve_storage(r[0]) for r in rows]
    if any(not x.is_file() for x in paths):
        _set_clip(new_id, status="failed")
        raise RuntimeError("A clip file is missing on disk")
    name, dst, thumb = _targets()
    try:
        segs = []
        for path, (_rel, st, en, dur, _w, _h) in zip(paths, rows):
            if not dur:
                dur = float(probe(path)["duration_sec"] or 0.0)
            en = min(float(en), dur) if en is not None else dur
            segs.append({"path": path, "start": st, "end": en})
        if ratio == "first":
            fw, fh = rows[0][4], rows[0][5]
            if not fw or not fh:
                i0 = probe(paths[0])
                fw, fh = i0["width"], i0["height"]
        else:
            fw, fh = RATIOS[ratio]
        total = build_timeline(segs, dst, fw, fh, transition, tsec, ctx.progress)
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
