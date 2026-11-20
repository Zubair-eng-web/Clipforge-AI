"""Job handler 'audio_mix': mix music into a clip. Result = NEW clip in storage/edited_clips (or a short preview file).
Light job: it can run while a heavy analysis is running."""
from backend import config
from backend.audio_studio.mix import mix_audio
from backend.database.db import SessionLocal
from backend.database.models import Clip, MusicTrack
from backend.editor.ops import has_audio
from backend.services.paths import resolve_storage
from backend.video_processing.ffprobe import probe
from backend.workers.caption_handlers import _set_clip
from backend.workers.editor_handlers import _finish_clip, _targets
from backend.workers.runner import JobCancelled, JobContext, register


@register("audio_mix")
def audio_mix(ctx: JobContext) -> None:
    p = ctx.payload
    src_id = int(p["clip_id"])
    new_id = int(p["new_clip_id"]) if p.get("new_clip_id") else None
    preview = bool(p.get("preview"))
    s = p["settings"]

    dst = thumb = None
    try:
        with SessionLocal() as db:
            clip = db.get(Clip, src_id)
            if clip is None or not clip.file_path:
                raise RuntimeError("Clip not found or not ready")
            rel, dur = clip.file_path, float(clip.duration_sec or 0.0)
            tracks = []
            for t in s["tracks"]:
                m = db.get(MusicTrack, int(t["track_id"]))
                if m is None:
                    raise RuntimeError(f"Music track {t['track_id']} was deleted")
                tracks.append({**t, "rel": m.file_path, "tdur": float(m.duration_sec or 0.0)})
            if new_id:
                nc = db.get(Clip, new_id)
                if nc is None:
                    raise RuntimeError("Clip record not found")
                nc.status = "processing"
                db.commit()

        src = resolve_storage(rel)
        if not src.is_file():
            raise RuntimeError("Clip file is missing on disk")
        if not dur:
            dur = float(probe(src)["duration_sec"] or 0.0)
        resolved = []
        for t in tracks:
            path = resolve_storage(t["rel"])
            if not path.is_file():
                raise RuntimeError("A music file is missing on disk")
            resolved.append({
                "path": path, "tdur": t["tdur"] or float(probe(path)["duration_sec"] or 0.0),
                "volume": float(t["volume"]) / 100.0, "start": float(t["start_sec"]), "trim_in": float(t["trim_in"]),
                "trim_out": t.get("trim_out"), "fade_in": float(t["fade_in"]), "fade_out": float(t["fade_out"]),
                "loop": bool(t["loop"]),
            })
        has_orig = has_audio(src)
        orig_on = bool(s["original_enabled"])
        orig_vol = float(s["original_volume"]) / 100.0
        if preview:
            (config.STORAGE_DIR / "previews").mkdir(parents=True, exist_ok=True)
            dst = config.STORAGE_DIR / "previews" / f"audiomix_{ctx.job_id}.mp4"
            mix_audio(src, dst, dur, has_orig, orig_on, orig_vol, resolved, "aac", 128,
                      limit=float(p.get("preview_seconds", 20)), on_progress=ctx.progress)
        else:
            name, dst, thumb = _targets()
            mix_audio(src, dst, dur, has_orig, orig_on, orig_vol, resolved, s.get("codec", "aac"),
                      int(s.get("bitrate_kbps", 192)), on_progress=ctx.progress)
            _finish_clip(new_id, name, dst, thumb, dur)
    except JobCancelled:
        for f in (dst, thumb):
            if f is not None:
                f.unlink(missing_ok=True)
        if new_id:
            _set_clip(new_id, status="cancelled")
        raise
    except Exception:
        for f in (dst, thumb):
            if f is not None:
                f.unlink(missing_ok=True)
        if new_id:
            _set_clip(new_id, status="failed")
        raise