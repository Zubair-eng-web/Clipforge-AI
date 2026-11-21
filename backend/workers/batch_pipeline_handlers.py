"""Job handler 'batch_pipeline': one video -> analyze (if needed) -> export best clips -> optional reel per clip
-> optional captions (Whisper words + Captions Studio preset burned in) per final clip.

Every step runs inside this one job (no waiting on the queue), so videos are processed one after another
and RAM stays low. Cancelling the job stops it after the current step.
Captions never make the job fail: a clip without speech just stays without captions (a note is saved)."""
import json
import logging

from sqlalchemy import select, update

from backend.captions.burn import has_subtitles_filter
from backend.clip_generation.selector import select_clips
from backend.database.db import SessionLocal
from backend.database.models import Clip, ClipCaption, Job, Setting, Video, VideoAnalysis
from backend.reels.presets import PLATFORMS
from backend.workers import runner
from backend.workers.analysis_handlers import analyze
from backend.workers.runner import JobCancelled, JobContext, register

log = logging.getLogger("clipforge.batch_pipeline")


class _Sub:
    """Looks like a JobContext to another handler, but reports into a slice (lo..hi) of this job."""

    def __init__(self, parent: JobContext, payload: dict, lo: float, hi: float):
        self.job_id = parent.job_id
        self.payload = payload
        self._parent = parent
        self._lo = lo
        self._hi = hi

    def progress(self, p: float) -> None:
        p = min(max(float(p), 0.0), 1.0)
        self._parent.progress(self._lo + (self._hi - self._lo) * p)


def _check_cancel(job_id: int) -> None:
    with SessionLocal() as db:
        if db.scalar(select(Job.status).where(Job.id == job_id)) == "cancelled":
            raise JobCancelled()


def _analysis_ready(video_id: int) -> bool:
    with SessionLocal() as db:
        va = db.scalar(select(VideoAnalysis).where(VideoAnalysis.video_id == video_id))
        return va is not None and va.status == "ready"


def _save_result(job_id: int, data: dict) -> None:
    key = f"batch_result:{job_id}"
    value = json.dumps(data, ensure_ascii=False)
    try:
        with SessionLocal() as db:
            row = db.get(Setting, key)
            if row:
                row.value = value
            else:
                db.add(Setting(key=key, value=value))
            db.commit()
    except Exception:
        log.exception("could not save batch result")


def _note(res: dict, text: str) -> None:
    if len(res["notes"]) < 5:
        res["notes"].append(str(text)[:200])


def _set_status_if_open(clip_ids: list, status: str) -> None:
    if not clip_ids:
        return
    with SessionLocal() as db:
        db.execute(update(Clip).where(Clip.id.in_(clip_ids), Clip.status.in_(["pending", "processing"]))
                   .values(status=status))
        db.commit()


def _clip_status(clip_id: int):
    with SessionLocal() as db:
        return db.scalar(select(Clip.status).where(Clip.id == clip_id))


def _handler(name: str):
    fn = runner.HANDLERS.get(name)
    if fn is None:
        raise RuntimeError(f"Job handler '{name}' is not registered")
    return fn


def _new_derived_clip(src_id: int, suffix: str):
    with SessionLocal() as db:
        src = db.get(Clip, src_id)
        if src is None:
            raise RuntimeError("Source clip not found")
        new = Clip(video_id=src.video_id, title=f"{src.title} - {suffix}"[:200] if suffix != "(captions)"
                   else f"{src.title} (captions)"[:200],
                   start_sec=src.start_sec, end_sec=src.end_sec, duration_sec=src.duration_sec,
                   ai_score=src.ai_score, status="pending")
        db.add(new)
        db.commit()
        db.refresh(new)
        return new.id, float(src.duration_sec or 0.0)


def _caption_one(ctx: JobContext, clip_id: int, preset: str, language, lo: float, hi: float,
                 res: dict, cap_new: list) -> None:
    """Whisper captions for one clip, then burn the preset into a NEW clip. Never raises (except cancel)."""
    gen = _handler("caption_generate")
    burn = _handler("caption_burn")
    mid = lo + (hi - lo) * 0.7
    try:
        gen(_Sub(ctx, {"clip_id": clip_id, "language": language}, lo, mid))
    except JobCancelled:
        raise
    except Exception as e:
        res["captions_skipped"] += 1
        _note(res, f"Captions for clip {clip_id}: {e or e.__class__.__name__}")
        return
    with SessionLocal() as db:
        row = db.scalar(select(ClipCaption).where(ClipCaption.clip_id == clip_id))
        lines = json.loads(row.lines_json or "[]") if row is not None else []
    if not lines:
        res["captions_skipped"] += 1
        _note(res, f"Clip {clip_id}: no speech found, so no captions were added")
        return
    _check_cancel(ctx.job_id)
    new_id, _dur = _new_derived_clip(clip_id, "(captions)")
    cap_new.append(new_id)
    payload = {"clip_id": clip_id, "new_clip_id": new_id,
               "studio": {"preset": preset, "config": {}, "overlays": []}}
    try:
        burn(_Sub(ctx, payload, mid, hi))
    except JobCancelled:
        raise
    except Exception as e:
        _note(res, f"Caption burn for clip {clip_id}: {e or e.__class__.__name__}")
        _set_status_if_open([new_id], "failed")
    if _clip_status(new_id) == "ready":
        res["captions_ready"] += 1
    else:
        res["captions_skipped"] += 1


@register("batch_pipeline")
def batch_pipeline(ctx: JobContext) -> None:
    p = ctx.payload
    video_id = int(p["video_id"])
    count = int(p.get("count", 5))
    mode = p.get("mode", "accurate")
    min_score = float(p.get("min_score", 0.0))
    use_gemini = bool(p.get("use_gemini", True))
    make_reels = bool(p.get("make_reels", False))
    want_caps = bool(p.get("captions", False))
    cap_preset = p.get("caption_preset") or "gaming"
    cap_lang = p.get("caption_language") or None
    if cap_lang == "auto":
        cap_lang = None

    res = {"clips_total": 0, "clips_ready": 0, "clips_failed": 0,
           "reels_ready": 0, "reels_failed": 0, "captions_ready": 0, "captions_skipped": 0, "notes": []}
    created: list = []
    reel_new: list = []
    cap_new: list = []

    # progress plan: analysis 0..0.30, then export / reels / captions share 0.30..0.98
    w_exp, w_reel, w_cap = 1.0, (1.5 if make_reels else 0.0), (2.0 if want_caps else 0.0)
    tot = w_exp + w_reel + w_cap
    a0 = 0.30
    e_hi = a0 + 0.68 * w_exp / tot
    r_hi = e_hi + 0.68 * w_reel / tot
    c_hi = r_hi + 0.68 * w_cap / tot

    try:
        with SessionLocal() as db:
            video = db.get(Video, video_id)
            if video is None:
                raise RuntimeError("Video not found")
            duration = video.duration_sec

        # 1) analysis (skipped when already done)
        if _analysis_ready(video_id):
            ctx.progress(0.05)
        else:
            analyze(_Sub(ctx, {"video_id": video_id, "use_gemini": use_gemini}, 0.0, a0))
        _check_cancel(ctx.job_id)

        # 2) choose clips
        with SessionLocal() as db:
            va = db.scalar(select(VideoAnalysis).where(VideoAnalysis.video_id == video_id))
            if va is None or va.status != "ready":
                raise RuntimeError("Analysis did not finish")
            try:
                highlights = json.loads(va.highlights_json or "[]")
            except ValueError:
                highlights = []
            if not highlights:
                raise RuntimeError("No highlights found (video may have no speech)")
            existing = db.scalars(
                select(Clip).where(Clip.video_id == video_id, Clip.status.in_(["pending", "processing", "ready"]))
            ).all()
            chosen = select_clips(
                highlights, count=count, min_score=min_score, duration=duration,
                pad_before=0.0, pad_after=0.0, blocked=[(c.start_sec, c.end_sec) for c in existing],
            )
            if not chosen:
                raise RuntimeError("No new clips available (all good highlights already used or score too low)")
            for c in chosen:
                clip = Clip(video_id=video_id, title=c["title"], start_sec=c["start"], end_sec=c["end"],
                            duration_sec=c["duration"], status="pending", ai_score=c["score"])
                db.add(clip)
                db.flush()
                created.append(clip.id)
            db.commit()
        res["clips_total"] = len(created)

        # 3) export clips (runs the normal clip_export handler directly)
        export = _handler("clip_export")
        span = (e_hi - a0) / len(created)
        ready: list = []
        for i, cid in enumerate(created):
            _check_cancel(ctx.job_id)
            sub = _Sub(ctx, {"clip_id": cid, "mode": mode}, a0 + span * i, a0 + span * (i + 1))
            try:
                export(sub)
            except JobCancelled:
                raise
            except Exception as e:
                _note(res, f"Clip {cid}: {e or e.__class__.__name__}")
                _set_status_if_open([cid], "failed")
            if _clip_status(cid) == "ready":
                ready.append(cid)
                res["clips_ready"] += 1
            else:
                res["clips_failed"] += 1

        # 4) reels (optional)
        finals = list(ready)
        if make_reels and ready:
            finals = []
            reel_fn = _handler("reel_create")
            plat_key = p.get("platform") or "youtube_shorts"
            if plat_key not in PLATFORMS:
                plat_key = "youtube_shorts"
            plat = PLATFORMS[plat_key]
            ratio = p.get("ratio") or plat["ratio"]
            rspan = (r_hi - e_hi) / len(ready)
            for i, cid in enumerate(ready):
                _check_cancel(ctx.job_id)
                new_id, dur = _new_derived_clip(cid, plat["label"])
                reel_new.append(new_id)
                target = p.get("target_sec")
                if target is None and dur > plat["max_sec"]:
                    target = float(plat["max_sec"])
                if target is not None:
                    target = min(float(target), float(plat["max_sec"]))
                payload = {
                    "clip_id": cid, "new_clip_id": new_id, "platform": plat_key, "ratio": ratio,
                    "size": p.get("size", "720"), "mode": p.get("reel_mode", "center"),
                    "cx": None, "cy": None, "target_sec": target, "start_sec": None, "end_sec": None,
                    "trim_dead_time": True, "brightness": 0.0, "contrast": 1.0, "saturation": 1.0,
                    "music": p.get("music") or [],
                    "original_audio_on": bool(p.get("original_audio_on", True)),
                    "original_volume": float(p.get("original_volume", 1.0)),
                    "title": "", "intro": None, "outro": None,
                }
                try:
                    reel_fn(_Sub(ctx, payload, e_hi + rspan * i, e_hi + rspan * (i + 1)))
                except JobCancelled:
                    raise
                except Exception as e:
                    _note(res, f"Reel for clip {cid}: {e or e.__class__.__name__}")
                    _set_status_if_open([new_id], "failed")
                if _clip_status(new_id) == "ready":
                    res["reels_ready"] += 1
                    finals.append(new_id)
                else:
                    res["reels_failed"] += 1

        # 5) captions (optional): on the reels if made, otherwise on the plain clips
        if want_caps and finals:
            if not has_subtitles_filter():
                _note(res, "Captions skipped: this FFmpeg build has no subtitles (libass) support")
                res["captions_skipped"] = len(finals)
            else:
                cspan = (c_hi - r_hi) / len(finals)
                for i, fid in enumerate(finals):
                    _check_cancel(ctx.job_id)
                    _caption_one(ctx, fid, cap_preset, cap_lang, r_hi + cspan * i, r_hi + cspan * (i + 1),
                                 res, cap_new)

        # 6) verdict (captions never fail the job)
        if res["clips_ready"] == 0:
            raise RuntimeError("No clip could be exported. " + (res["notes"][0] if res["notes"] else ""))
        if make_reels and res["reels_ready"] == 0:
            raise RuntimeError("Clips were exported, but no reel could be made (try Reels Studio on them). "
                               + (res["notes"][0] if res["notes"] else ""))
    except JobCancelled:
        _set_status_if_open(created + reel_new + cap_new, "cancelled")
        _note(res, "Cancelled by user")
        _save_result(ctx.job_id, res)
        raise
    except Exception as e:
        _note(res, str(e) or e.__class__.__name__)
        _save_result(ctx.job_id, res)
        raise
    _save_result(ctx.job_id, res)
    ctx.progress(1.0)