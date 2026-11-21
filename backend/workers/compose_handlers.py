"""Job handler: editor_compose (text overlays + extra music tracks -> ONE new clip). Source is never modified."""
import shutil

from backend import config
from backend.audio_studio.mix import mix_audio
from backend.captions.burn import burn_captions
from backend.captions.presets import to_ass_studio
from backend.database.db import SessionLocal
from backend.database.models import Clip, MusicTrack
from backend.editor.ops import has_audio
from backend.services.paths import resolve_storage
from backend.video_processing.ffprobe import probe
from backend.workers.caption_handlers import _set_clip
from backend.workers.editor_handlers import _finish_clip, _targets
from backend.workers.runner import JobCancelled, JobContext, register


@register("editor_compose")
def editor_compose(ctx: JobContext) -> None:
    p = ctx.payload
    src_id, new_id = int(p["clip_id"]), int(p["new_clip_id"])
    overlays = p.get("overlays") or []
    music = p.get("music") or []
    rows = []
    with SessionLocal() as db:
        clip, nc = db.get(Clip, src_id), db.get(Clip, new_id)
        if clip is None or nc is None:
            raise RuntimeError("Clip record not found")
        if not clip.file_path:
            nc.status = "failed"
            db.commit()
            raise RuntimeError("The source clip has no file")
        rel, dur, w, h = clip.file_path, float(clip.duration_sec or 0.0), clip.width, clip.height
        for m in music:
            t = db.get(MusicTrack, int(m["track_id"]))
            if t is None:
                nc.status = "failed"
                db.commit()
                raise RuntimeError(f"Music track {m['track_id']} was deleted")
            rows.append((m, t.file_path, float(t.duration_sec or 0.0)))
        nc.status = "processing"
        db.commit()

    src = resolve_storage(rel)
    if not src.is_file():
        _set_clip(new_id, status="failed")
        raise RuntimeError("Clip file is missing on disk")
    name, dst, thumb = _targets()
    work = config.STORAGE_DIR / "temporary" / name
    try:
        if not dur or not w or not h:
            i0 = probe(src)
            dur = dur or float(i0["duration_sec"] or 0.0)
            w, h = w or i0["width"], h or i0["height"]
        tracks = []
        for m, trel, tdur in rows:
            path = resolve_storage(trel)
            if not path.is_file():
                raise RuntimeError("A music file is missing on disk")
            tracks.append({
                "path": path, "tdur": tdur or float(probe(path)["duration_sec"] or 0.0),
                "volume": float(m.get("volume", 50)) / 100.0, "start": float(m.get("start_sec", 0)),
                "trim_in": float(m.get("trim_in", 0)), "trim_out": m.get("trim_out"),
                "fade_in": float(m.get("fade_in", 0)), "fade_out": float(m.get("fade_out", 0)),
                "loop": bool(m.get("loop", False)),
            })
        cur = src
        if overlays:
            work.mkdir(parents=True, exist_ok=True)
            ass = work / "overlays.ass"
            ass.write_text(to_ass_studio([], int(w), int(h), {
                "preset": "custom", "config": p.get("style") or {}, "overlays": overlays}), encoding="utf-8")
            target = (work / "overlay.mp4") if tracks else dst
            cb = (lambda x: ctx.progress(x * 0.6)) if tracks else ctx.progress
            burn_captions(src, ass, target, dur, cb)
            cur = target
        if tracks:
            cb = (lambda x: ctx.progress(0.6 + x * 0.4)) if overlays else ctx.progress
            mix_audio(cur, dst, dur, has_audio(cur), bool(p.get("original_on", True)),
                      float(p.get("original_volume", 100)) / 100.0, tracks, on_progress=cb)
        _finish_clip(new_id, name, dst, thumb, dur)
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
