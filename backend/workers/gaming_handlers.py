"""Job handler 'gaming_classify': find gaming highlights (frames + audio energy + speech) in one video.
Scenes are stored in category_scenes with category = 'gta_<id>'."""
import json
import logging

from sqlalchemy import delete, select

from backend import config
from backend.database.db import SessionLocal
from backend.database.models import CategoryScene, Setting, Video
from backend.gaming import pipeline
from backend.gaming.categories import category_ids
from backend.scene_ai import engine
from backend.scene_ai.extract import create_clips
from backend.services.paths import resolve_storage
from backend.video_processing.ffmpeg_service import FfmpegError, grab_frame
from backend.workers.analysis_handlers import _run_steps
from backend.workers.runner import JobContext, register
from backend.workers.scene_handlers import _Sub, _load

log = logging.getLogger("clipforge.gaming_handler")


@register("gaming_classify")
def gaming_classify(ctx: JobContext) -> None:
    p = ctx.payload
    video_id = int(p["video_id"])
    o = p.get("options", {})
    valid = set(category_ids()) | {"custom"}
    cat_req = [c for c in p["categories"] if c["key"] in valid]
    if not cat_req:
        raise RuntimeError("No valid gaming category selected")
    custom_label = next((c.get("custom_text", "") for c in cat_req if c["key"] == "custom"), None)
    sel = [c["key"] for c in cat_req]

    with SessionLocal() as db:
        v = db.get(Video, video_id)
        if v is None:
            raise RuntimeError("Video not found")
        stored, duration, has_video = v.stored_path, float(v.duration_sec or 0.0), v.width is not None
    if not has_video:
        raise RuntimeError("Gaming highlights need a video file")
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
        _run_steps(_Sub(ctx, 0.0, 0.3), video_id, src, duration, True, False, steps, False, False, None)
        shots, segments, have_tr = _load(video_id)
    if not shots:
        raise RuntimeError("No scenes found in this video")
    if not o.get("use_speech", True):
        segments = []

    units = engine.build_units(shots, duration or shots[-1]["end"])
    results, info = pipeline.score_units(units, segments, src, selected=sel, custom_label=custom_label,
                                         use_vision=bool(o.get("use_vision", True)),
                                         progress=_Sub(ctx, 0.3, 0.9).progress)
    cuts = sorted({round(s["start"], 2) for s in shots} | {round(s["end"], 2) for s in shots})
    new = pipeline.build_scenes(units, results, cat_req, cuts, o)
    ctx.progress(0.92)

    dbkeys = ["gta_" + k for k in sel]
    with SessionLocal() as db:
        db.execute(delete(CategoryScene).where(CategoryScene.video_id == video_id,
                                               CategoryScene.category.in_(dbkeys), CategoryScene.clip_id.is_(None)))
        kept = db.scalars(select(CategoryScene).where(CategoryScene.video_id == video_id,
                                                      CategoryScene.category.in_(dbkeys))).all()
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
        c = counts.setdefault(s["category"][4:], {"detected": 0, "uncertain": 0})
        c[s["status"]] += 1
    info["counts"] = counts
    with SessionLocal() as db:
        key = f"gaming_info:{video_id}"
        row = db.get(Setting, key)
        payload = json.dumps(info, ensure_ascii=False)
        if row:
            row.value = payload
        else:
            db.add(Setting(key=key, value=payload))
        db.commit()

    if o.get("auto_extract", False) and ids:
        with SessionLocal() as db:
            rows = db.scalars(select(CategoryScene).where(CategoryScene.id.in_(ids),
                                                          CategoryScene.status == "detected")).all()
            video = db.get(Video, video_id)
            create_clips(db, video, rows, o.get("mode", "accurate"), bool(o.get("subtitles")),
                         segments if o.get("subtitles") else None)