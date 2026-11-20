"""Job handler 'scene_classify': find category scenes (fighting, romantic, comedy, ...) in one video."""
import json
import logging

from sqlalchemy import delete, select

from backend import config
from backend.database.db import SessionLocal
from backend.database.models import CategoryScene, Scene, Setting, Transcript, Video
from backend.scene_ai import engine
from backend.scene_ai.categories import CATEGORIES
from backend.scene_ai.extract import create_clips
from backend.services.paths import resolve_storage
from backend.video_processing.ffmpeg_service import FfmpegError, grab_frame
from backend.workers.analysis_handlers import _run_steps
from backend.workers.runner import JobContext, register

log = logging.getLogger("clipforge.scene_handler")


class _Sub:
    def __init__(self, ctx, lo, hi):
        self.ctx, self.lo, self.hi = ctx, lo, hi

    def progress(self, p: float) -> None:
        self.ctx.progress(self.lo + (self.hi - self.lo) * min(max(p, 0.0), 1.0))


def _load(video_id: int):
    with SessionLocal() as db:
        shots = [{"start": s.start_sec, "end": s.end_sec}
                 for s in db.scalars(select(Scene).where(Scene.video_id == video_id).order_by(Scene.idx)).all()]
        tr = db.scalars(select(Transcript).where(Transcript.video_id == video_id)
                        .order_by(Transcript.id.desc())).first()
        segs = json.loads(tr.segments or "[]") if tr else []
        return shots, segs, tr is not None


@register("scene_classify")
def scene_classify(ctx: JobContext) -> None:
    p = ctx.payload
    video_id = int(p["video_id"])
    cat_req = p["categories"]
    o = p.get("options", {})
    with SessionLocal() as db:
        v = db.get(Video, video_id)
        if v is None:
            raise RuntimeError("Video not found")
        stored, duration, has_video = v.stored_path, float(v.duration_sec or 0.0), v.width is not None
    if not has_video:
        raise RuntimeError("Scene classification needs a video file")
    src = resolve_storage(stored)
    if not src.is_file():
        raise RuntimeError("Source video file is missing on disk")

    shots, segments, have_tr = _load(video_id)
    steps = []
    if o.get("use_speech", True) and not have_tr:
        steps.append("transcribe")
    if not shots:
        steps.append("scenes")
    if steps:
        _run_steps(_Sub(ctx, 0.0, 0.35), video_id, src, duration, True, False, steps, False, False, None)
        shots, segments, have_tr = _load(video_id)
    if not shots:
        raise RuntimeError("No scenes found in this video")
    if not o.get("use_speech", True):
        segments = []

    units = engine.build_units(shots, duration or shots[-1]["end"])
    cats = [{"key": c["key"], "rule": CATEGORIES[c["key"]]["rule"], "label": CATEGORIES[c["key"]]["label"],
             "custom_text": c.get("custom_text", "")} for c in cat_req]
    results, info = engine.classify(units, segments, cats, src, use_vision=bool(o.get("use_vision", True)),
                                    progress=_Sub(ctx, 0.35, 0.9).progress)

    cuts = sorted({round(s["start"], 2) for s in shots} | {round(s["end"], 2) for s in shots})
    thr = float(o.get("confidence", 60))
    min_sec = float(o.get("min_scene_sec", 10))
    max_sec = float(o.get("max_scene_sec", 0) or 0)
    new = []
    for c in cat_req:
        key = c["key"]
        fixed = None if c.get("duration") in (None, "auto") else float(c["duration"])
        sc_list = [r["scores"].get(key, 0.0) for r in results]
        for seg in engine.find_segments(units, results, key, thr, bool(o.get("merge", True))):
            full0, full1 = seg["start"], seg["end"]
            st, en = full0, full1
            limits = [x for x in (fixed, max_sec) if x and x > 0]
            limit = min(limits) if limits else None
            if limit and en - st > limit + 0.01:
                st, en = engine.fit_window(units, sc_list, seg["unit_idx"], limit)
                if o.get("complete_boundaries", True):
                    st, en = engine.snap_range(st, en, cuts, full0, full1)
            if en - st < min_sec:
                continue
            new.append({**seg, "start": st, "end": en, "full0": full0, "full1": full1})
    ctx.progress(0.92)

    keys = [c["key"] for c in cat_req]
    with SessionLocal() as db:
        db.execute(delete(CategoryScene).where(CategoryScene.video_id == video_id,
                                               CategoryScene.category.in_(keys), CategoryScene.clip_id.is_(None)))
        kept = db.scalars(select(CategoryScene).where(CategoryScene.video_id == video_id,
                                                      CategoryScene.category.in_(keys))).all()
        rows = []
        for s in new:
            if o.get("avoid_duplicates", True) and any(
                    k.category == s["category"] and engine.overlap_ratio(s["start"], s["end"], k.start_sec, k.end_sec) >= 0.5
                    for k in kept):
                continue
            row = CategoryScene(video_id=video_id, category=s["category"], start_sec=s["start"], end_sec=s["end"],
                                full_start_sec=s["full0"], full_end_sec=s["full1"], confidence=s["conf"],
                                status=s["status"], source=s["source"], description=s["description"])
            db.add(row)
            rows.append(row)
        db.flush()
        ids = [r.id for r in rows]
        db.commit()

    for n, sid in enumerate(ids):
        with SessionLocal() as db:
            r = db.get(CategoryScene, sid)
            if r is None:
                continue
            rel = f"thumbnails/scene_{sid}.jpg"
            try:
                grab_frame(src, config.STORAGE_DIR / rel, (r.start_sec + r.end_sec) / 2)
                r.thumbnail_path = rel
                db.commit()
            except FfmpegError:
                pass
        ctx.progress(0.92 + 0.06 * (n + 1) / max(len(ids), 1))

    counts = {}
    for s in new:
        c = counts.setdefault(s["category"], {"detected": 0, "uncertain": 0})
        c[s["status"]] += 1
    info["counts"] = counts
    with SessionLocal() as db:
        key = f"scene_ai_info:{video_id}"
        row = db.get(Setting, key)
        payload = json.dumps(info, ensure_ascii=False)
        if row:
            row.value = payload
        else:
            db.add(Setting(key=key, value=payload))
        db.commit()

    if o.get("auto_extract", True) and ids:
        with SessionLocal() as db:
            rows = db.scalars(select(CategoryScene).where(CategoryScene.id.in_(ids),
                                                          CategoryScene.status == "detected")).all()
            video = db.get(Video, video_id)
            create_clips(db, video, rows, o.get("mode", "accurate"), bool(o.get("subtitles")),
                         segments if o.get("subtitles") else None)