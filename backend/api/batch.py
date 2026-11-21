import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database.db import get_db
from backend.database.models import Clip, Job, MusicTrack, Setting, Video
from backend.reels.presets import PLATFORMS, check_target
from backend.captions.presets import PRESETS as CAPTION_PRESETS

router = APIRouter(prefix="/api/batch", tags=["batch"])
BATCH_TYPES = ["batch_video", "batch_pipeline"]


class StartBody(BaseModel):
    video_ids: list[int] = Field(min_length=1, max_length=50)
    count: int = Field(5, ge=1, le=20)
    mode: Literal["accurate", "fast"] = "accurate"
    min_score: float = Field(0.0, ge=0, le=100)
    use_gemini: bool = True


class MusicItem(BaseModel):
    track_id: int
    volume: float = Field(default=0.6, ge=0, le=1)
    start: float = Field(default=0.0, ge=0)
    trim_in: float = Field(default=0.0, ge=0)
    trim_out: float = Field(default=0.0, ge=0)
    fade_in: float = Field(default=1.0, ge=0, le=30)
    fade_out: float = Field(default=1.5, ge=0, le=30)
    loop: bool = True


class PipelineBody(BaseModel):
    video_ids: list[int] = Field(min_length=1, max_length=50)
    count: int = Field(5, ge=1, le=20)
    mode: Literal["accurate", "fast"] = "accurate"
    min_score: float = Field(0.0, ge=0, le=100)
    use_gemini: bool = True
    make_reels: bool = False
    platform: str = "youtube_shorts"
    ratio: Optional[Literal["9:16", "1:1", "16:9"]] = None
    size: Literal["1080", "720"] = "720"
    reel_mode: Literal["face", "center", "blur"] = "center"
    target_sec: Optional[float] = Field(default=None, gt=0)
    music: list[MusicItem] = Field(default_factory=list, max_length=5)
    original_audio_on: bool = True
    original_volume: float = Field(default=1.0, ge=0, le=1)
    captions: bool = False
    caption_preset: str = "gaming"
    caption_language: Optional[str] = Field(default=None, max_length=10)


def _prepare(db: Session, video_ids: list[int]):
    ids = list(dict.fromkeys(video_ids))
    videos = {v.id: v for v in db.scalars(select(Video).where(Video.id.in_(ids))).all()}
    missing = [i for i in ids if i not in videos]
    if missing:
        raise HTTPException(404, f"Video not found: {missing}")
    audio_only = [i for i in ids if videos[i].width is None]
    if audio_only:
        raise HTTPException(400, f"Audio-only files cannot be clipped: {audio_only}")
    active = {
        j.video_id for j in db.scalars(
            select(Job).where(Job.type.in_(BATCH_TYPES), Job.status.in_(["queued", "processing"]))
        ).all()
    }
    return ids, active


@router.post("/start")
def start_batch(body: StartBody, db: Session = Depends(get_db)):
    ids, active = _prepare(db, body.video_ids)
    created, skipped = [], []
    for vid in ids:
        if vid in active:
            skipped.append(vid)
            continue
        job = Job(type="batch_video", video_id=vid, status="queued",
                  payload=json.dumps({"video_id": vid, "count": body.count, "mode": body.mode,
                                      "min_score": body.min_score, "use_gemini": body.use_gemini}))
        db.add(job)
        db.flush()
        created.append(job.id)
    db.commit()
    return {"created": len(created), "job_ids": created, "skipped_video_ids": skipped}


@router.post("/pipeline")
def start_pipeline(body: PipelineBody, db: Session = Depends(get_db)):
    if body.platform not in PLATFORMS:
        raise HTTPException(400, f"Unknown platform: {body.platform}")
    if body.target_sec is not None:
        ok, msg = check_target(body.platform, body.target_sec)
        if not ok:
            raise HTTPException(400, msg)
    for m in body.music:
        if db.get(MusicTrack, m.track_id) is None:
            raise HTTPException(404, f"Music track {m.track_id} not found")
    if body.caption_preset not in CAPTION_PRESETS:
        raise HTTPException(400, f"Unknown caption preset: {body.caption_preset}")
    ids, active = _prepare(db, body.video_ids)
    base = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    base.pop("video_ids", None)
    created, skipped = [], []
    for vid in ids:
        if vid in active:
            skipped.append(vid)
            continue
        job = Job(type="batch_pipeline", video_id=vid, status="queued",
                  payload=json.dumps({**base, "video_id": vid}))
        db.add(job)
        db.flush()
        created.append(job.id)
    db.commit()
    return {"created": len(created), "job_ids": created, "skipped_video_ids": skipped}


@router.get("/jobs")
def batch_jobs(limit: int = 50, db: Session = Depends(get_db)):
    jobs = db.scalars(
        select(Job).where(Job.type.in_(BATCH_TYPES)).order_by(Job.id.desc()).limit(min(max(limit, 1), 200))
    ).all()
    vids = {j.video_id for j in jobs if j.video_id}
    names = {v.id: v.original_name for v in db.scalars(select(Video).where(Video.id.in_(vids))).all()} if vids else {}
    counts: dict = {}
    if vids:
        for vid, status, n in db.execute(
            select(Clip.video_id, Clip.status, func.count()).where(Clip.video_id.in_(vids)).group_by(Clip.video_id, Clip.status)
        ).all():
            counts.setdefault(vid, {})[status] = n
    results: dict = {}
    if jobs:
        keys = [f"batch_result:{j.id}" for j in jobs]
        for s in db.scalars(select(Setting).where(Setting.key.in_(keys))).all():
            try:
                results[s.key] = json.loads(s.value)
            except ValueError:
                pass
    items = []
    for j in jobs:
        c = counts.get(j.video_id, {})
        r = results.get(f"batch_result:{j.id}", {})
        items.append({
            "job_id": j.id, "type": j.type, "video_id": j.video_id,
            "video_name": names.get(j.video_id, f"Video {j.video_id}"),
            "status": j.status, "progress": j.progress, "error": j.error,
            "clips_total": sum(c.values()), "clips_ready": c.get("ready", 0),
            "clips_active": c.get("pending", 0) + c.get("processing", 0),
            "reels_ready": r.get("reels_ready", 0), "reels_failed": r.get("reels_failed", 0),
            "captions_ready": r.get("captions_ready", 0), "captions_skipped": r.get("captions_skipped", 0),
            "notes": r.get("notes", []),
            "created_at": j.created_at.isoformat(),
        })
    return {"items": items}