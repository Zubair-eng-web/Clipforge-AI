import json
from typing import List, Literal, Union

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.db import get_db
from backend.database.models import CategoryScene, Clip, Job, Setting, Video
from backend.gaming.categories import GAMING_CATEGORIES, get_categories

router = APIRouter(prefix="/api/gaming", tags=["gaming"])
VALID = {c["id"] for c in GAMING_CATEGORIES} | {"custom"}


class GCat(BaseModel):
    key: str
    custom_text: str = Field("", max_length=300)
    duration: Union[str, float] = "auto"


class GOpt(BaseModel):
    min_scene_sec: float = Field(8, ge=1, le=3600)
    max_scene_sec: float = Field(0, ge=0, le=7200)
    confidence: float = Field(55, ge=10, le=100)
    merge: bool = True
    avoid_duplicates: bool = True
    complete_boundaries: bool = True
    use_vision: bool = True
    use_speech: bool = True
    auto_extract: bool = False
    subtitles: bool = False
    mode: Literal["accurate", "fast"] = "accurate"


class GRun(BaseModel):
    categories: List[GCat] = Field(min_length=1, max_length=26)
    options: GOpt = Field(default_factory=GOpt)


def _video(db: Session, video_id: int) -> Video:
    v = db.get(Video, video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    return v


@router.get("/categories")
def categories():
    items = [{"key": c["id"], "label": c["label"], "hint": c["hint"]} for c in GAMING_CATEGORIES]
    items.append({"key": "custom", "label": "Custom", "hint": "Describe your own category"})
    return {"items": items}


@router.post("/videos/{video_id}/run")
def run(video_id: int, body: GRun, db: Session = Depends(get_db)):
    v = _video(db, video_id)
    if v.width is None:
        raise HTTPException(400, "Gaming highlights need a video file (this file is audio only)")
    cats, seen = [], set()
    for c in body.categories:
        if c.key not in VALID:
            raise HTTPException(400, f"Unknown gaming category: {c.key}")
        if c.key in seen:
            continue
        seen.add(c.key)
        if c.key == "custom" and len(c.custom_text.strip()) < 3:
            raise HTTPException(400, "Describe the custom category")
        if c.duration == "auto":
            dur = "auto"
        else:
            try:
                dur = float(c.duration)
            except ValueError:
                raise HTTPException(400, f"Invalid duration for {c.key}")
            if not 5 <= dur <= 3600:
                raise HTTPException(400, f"Duration for {c.key} must be between 5 and 3600 seconds")
        cats.append({"key": c.key, "custom_text": c.custom_text.strip(), "duration": dur})
    active = db.scalars(select(Job).where(Job.type == "gaming_classify", Job.video_id == video_id,
                                          Job.status.in_(["queued", "processing"]))).first()
    if active:
        return {"job_id": active.id, "already_running": True}
    payload = {"video_id": video_id, "categories": cats, "options": body.options.model_dump()}
    job = Job(type="gaming_classify", video_id=video_id, status="queued", payload=json.dumps(payload))
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"job_id": job.id, "already_running": False}


@router.get("/videos/{video_id}/highlights")
def highlights(video_id: int, category: str = "", db: Session = Depends(get_db)):
    _video(db, video_id)
    stmt = select(CategoryScene).where(CategoryScene.video_id == video_id, CategoryScene.category.like("gta%"))
    if category:
        stmt = stmt.where(CategoryScene.category == "gta_" + category)
    rows = db.scalars(stmt.order_by(CategoryScene.confidence.desc())).all()
    clip_ids = [r.clip_id for r in rows if r.clip_id]
    clips = {c.id: c for c in db.scalars(select(Clip).where(Clip.id.in_(clip_ids))).all()} if clip_ids else {}
    labels = {c["id"]: c["label"] for c in get_categories()}
    items = []
    for r in rows:
        cid = r.category[4:]
        clip = clips.get(r.clip_id)
        items.append({
            "id": r.id, "category": cid, "label": labels.get(cid, cid.replace("_", " ").title()),
            "start_sec": r.start_sec, "end_sec": r.end_sec, "duration_sec": round(r.end_sec - r.start_sec, 2),
            "confidence": r.confidence, "status": r.status, "source": r.source, "description": r.description,
            "thumbnail_url": f"/api/scene-ai/scenes/{r.id}/thumbnail" if r.thumbnail_path else None,
            "clip_id": r.clip_id, "clip_status": clip.status if clip is not None else None, "filename": r.filename,
        })
    info = db.get(Setting, f"gaming_info:{video_id}")
    return {"items": items, "info": json.loads(info.value) if info else None}