import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.clips import clip_dict
from backend.api.editor import _ready
from backend.captions.burn import has_subtitles_filter
from backend.database.db import get_db
from backend.database.models import Clip, Job, MusicTrack

router = APIRouter(prefix="/api/editor", tags=["editor-compose"])
HEX = r"^#[0-9a-fA-F]{6}$"


class Overlay(BaseModel):
    text: str = Field(min_length=1, max_length=200)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    position: Literal["top", "center", "bottom"] = "center"


class Style(BaseModel):
    font: str = Field("Arial", max_length=60)
    font_size: int = Field(0, ge=0, le=300)
    primary: str = Field("#FFFFFF", pattern=HEX)
    outline_color: str = Field("#000000", pattern=HEX)
    bold: bool = True
    uppercase: bool = False
    animation: Literal["none", "fade", "pop"] = "none"


class MusicIn(BaseModel):
    track_id: int
    volume: float = Field(50, ge=0, le=100)
    start_sec: float = Field(0, ge=0)
    trim_in: float = Field(0, ge=0)
    trim_out: Optional[float] = Field(None, gt=0)
    fade_in: float = Field(0, ge=0, le=30)
    fade_out: float = Field(0, ge=0, le=30)
    loop: bool = False


class ComposeBody(BaseModel):
    clip_id: int
    overlays: list[Overlay] = Field(default_factory=list, max_length=30)
    music: list[MusicIn] = Field(default_factory=list, max_length=6)
    original_on: bool = True
    original_volume: float = Field(100, ge=0, le=100)
    style: Style = Field(default_factory=Style)
    title: str = Field("", max_length=200)


@router.post("/compose")
def compose(body: ComposeBody, db: Session = Depends(get_db)):
    clip = _ready(db, body.clip_id)
    dur = float(clip.duration_sec or 0.0)
    music = [m for m in body.music if m.volume > 0]
    if not body.overlays and not music:
        raise HTTPException(400, "Add at least one text overlay or one music track (volume above 0)")
    if body.overlays and not has_subtitles_filter():
        raise HTTPException(400, "This FFmpeg build has no subtitles (libass) support. Install a full FFmpeg build.")
    for i, o in enumerate(body.overlays, 1):
        if o.end <= o.start:
            raise HTTPException(400, f"Overlay {i}: end must be after start")
        if dur and o.start >= dur - 0.05:
            raise HTTPException(400, f"Overlay {i} starts after the end of the clip ({dur:g}s)")
    for m in music:
        t = db.get(MusicTrack, m.track_id)
        if t is None:
            raise HTTPException(404, f"Music track {m.track_id} not found")
        if dur and m.start_sec >= dur - 0.05:
            raise HTTPException(400, "A music track starts after the end of the clip")
        if m.trim_out is not None and m.trim_out <= m.trim_in:
            raise HTTPException(400, "Music trim end must be after trim start")
        td = float(t.duration_sec or 0.0)
        if td and m.trim_in >= td - 0.05:
            raise HTTPException(400, "Music trim start is beyond the end of the track")
    new = Clip(video_id=clip.video_id, title=(body.title.strip() or f"{clip.title} (composed)")[:200],
               start_sec=clip.start_sec, end_sec=clip.end_sec, duration_sec=clip.duration_sec,
               width=clip.width, height=clip.height, aspect_ratio=clip.aspect_ratio,
               ai_score=clip.ai_score, status="pending")
    db.add(new)
    db.flush()
    payload = {"clip_id": clip.id, "new_clip_id": new.id, "overlays": [o.model_dump() for o in body.overlays],
               "music": [m.model_dump() for m in music], "original_on": body.original_on,
               "original_volume": body.original_volume, "style": body.style.model_dump()}
    job = Job(type="editor_compose", video_id=clip.video_id, status="queued", payload=json.dumps(payload))
    db.add(job)
    db.commit()
    db.refresh(new)
    db.refresh(job)
    return {"clip": clip_dict(new), "clip_id": new.id, "job_id": job.id}
