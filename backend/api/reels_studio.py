import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.clips import clip_dict
from backend.database.db import get_db
from backend.database.models import Clip, Job, MusicTrack
from backend.reels.presets import DURATIONS, MODES, PLATFORMS, SIZES, check_target

router = APIRouter(prefix="/api/reels-studio", tags=["reels"])


class MusicItem(BaseModel):
    track_id: int
    volume: float = Field(default=0.6, ge=0, le=1)
    start: float = Field(default=0.0, ge=0)
    trim_in: float = Field(default=0.0, ge=0)
    trim_out: float = Field(default=0.0, ge=0)
    fade_in: float = Field(default=1.0, ge=0, le=30)
    fade_out: float = Field(default=1.5, ge=0, le=30)
    loop: bool = True


class Card(BaseModel):
    text: str = Field(..., min_length=1, max_length=80)
    seconds: float = Field(default=2.0, ge=1, le=5)
    bg: str = Field(default="#111827", pattern=r"^#[0-9a-fA-F]{6}$")
    fg: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")


class ReelBody(BaseModel):
    clip_id: int
    platform: str = "youtube_shorts"
    ratio: Optional[Literal["9:16", "1:1", "16:9"]] = None
    size: Literal["1080", "720"] = "1080"
    mode: Literal["face", "center", "blur", "manual"] = "face"
    cx: Optional[float] = Field(default=None, ge=0, le=1)
    cy: Optional[float] = Field(default=None, ge=0, le=1)
    target_sec: Optional[float] = Field(default=None, gt=0)
    start_sec: Optional[float] = Field(default=None, ge=0)
    end_sec: Optional[float] = Field(default=None, gt=0)
    trim_dead_time: bool = True
    brightness: float = Field(default=0.0, ge=-0.5, le=0.5)
    contrast: float = Field(default=1.0, ge=0.5, le=1.5)
    saturation: float = Field(default=1.0, ge=0.0, le=2.0)
    music: list[MusicItem] = Field(default_factory=list)
    original_audio_on: bool = True
    original_volume: float = Field(default=1.0, ge=0, le=1)
    title: str = Field(default="", max_length=200)
    intro: Optional[Card] = None
    outro: Optional[Card] = None


@router.get("/platforms")
def platforms():
    return {
        "platforms": PLATFORMS,
        "durations": DURATIONS,
        "sizes": {k: {r: list(v) for r, v in d.items()} for k, d in SIZES.items()},
        "modes": list(MODES),
    }


@router.post("/create")
def create_reel(body: ReelBody, db: Session = Depends(get_db)):
    plat = PLATFORMS.get(body.platform)
    if plat is None:
        raise HTTPException(400, f"Unknown platform: {body.platform}")
    clip = db.get(Clip, body.clip_id)
    if not clip:
        raise HTTPException(404, "Clip not found")
    if clip.status != "ready" or not clip.file_path:
        raise HTTPException(409, "The clip is not ready yet")
    if len(body.music) > 5:
        raise HTTPException(400, "At most 5 music tracks")
    for m in body.music:
        if db.get(MusicTrack, m.track_id) is None:
            raise HTTPException(404, f"Music track {m.track_id} not found")
    if (body.start_sec is None) != (body.end_sec is None):
        raise HTTPException(400, "Give both start_sec and end_sec, or neither")

    clip_dur = float(clip.duration_sec or 0.0)
    target = body.target_sec
    if body.start_sec is not None:
        if body.end_sec <= body.start_sec:
            raise HTTPException(400, "end_sec must be greater than start_sec")
        ok, msg = check_target(body.platform, body.end_sec - body.start_sec)
        target = None
    else:
        ok, msg = check_target(body.platform, target)
        if ok and target is None and clip_dur > plat["max_sec"]:
            target = float(plat["max_sec"])  # long clip: fit the platform limit automatically
    if not ok:
        raise HTTPException(400, msg)

    ratio = body.ratio or plat["ratio"]
    title = (body.title.strip() or f"{clip.title} - {plat['label']}")[:200]
    new = Clip(video_id=clip.video_id, title=title, start_sec=clip.start_sec, end_sec=clip.end_sec,
               duration_sec=clip.duration_sec, ai_score=clip.ai_score, status="pending")
    db.add(new)
    db.flush()
    payload = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    payload.update({"clip_id": clip.id, "new_clip_id": new.id, "ratio": ratio, "target_sec": target})
    job = Job(type="reel_create", video_id=clip.video_id, status="queued", payload=json.dumps(payload))
    db.add(job)
    db.commit()
    db.refresh(new)
    db.refresh(job)
    return {"clip": clip_dict(new), "clip_id": new.id, "job_id": job.id, "platform": body.platform,
            "ratio": ratio, "target_sec": target}