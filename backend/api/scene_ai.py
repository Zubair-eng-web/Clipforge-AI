import json
import uuid
import zipfile
from typing import List, Literal, Union

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from backend import config
from backend.database.db import get_db
from backend.database.models import CategoryScene, Clip, Job, Setting, Transcript, Video
from backend.scene_ai.categories import CATEGORIES
from backend.scene_ai.extract import create_clips
from backend.services.paths import resolve_storage

router = APIRouter(prefix="/api/scene-ai", tags=["scene-ai"])


class CatIn(BaseModel):
    key: str
    custom_text: str = Field("", max_length=300)
    duration: Union[str, float] = "auto"  # "auto" = complete scene, or seconds


class OptIn(BaseModel):
    min_scene_sec: float = Field(10, ge=1, le=3600)
    max_scene_sec: float = Field(0, ge=0, le=7200)  # 0 = no limit
    confidence: float = Field(60, ge=10, le=100)
    merge: bool = True
    avoid_duplicates: bool = True
    complete_boundaries: bool = True
    subtitles: bool = False
    use_vision: bool = True
    use_speech: bool = True
    auto_extract: bool = True
    mode: Literal["accurate", "fast"] = "accurate"


class RunIn(BaseModel):
    categories: List[CatIn] = Field(min_length=1, max_length=20)
    options: OptIn = Field(default_factory=OptIn)


class AdjustIn(BaseModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)


class ExtractIn(BaseModel):
    scene_ids: List[int] = Field(min_length=1, max_length=500)
    mode: Literal["accurate", "fast"] = "accurate"
    subtitles: bool = False


def _video(db: Session, video_id: int) -> Video:
    v = db.get(Video, video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    return v


def scene_dict(r: CategoryScene, clip) -> dict:
    verified = None
    if clip is not None and clip.status == "ready" and clip.duration_sec:
        verified = abs(clip.duration_sec - (r.end_sec - r.start_sec)) <= 3.0
    return {
        "id": r.id, "category": r.category, "label": CATEGORIES.get(r.category, {}).get("label", r.category),
        "start_sec": r.start_sec, "end_sec": r.end_sec, "duration_sec": round(r.end_sec - r.start_sec, 2),
        "full_start_sec": r.full_start_sec, "full_end_sec": r.full_end_sec,
        "confidence": r.confidence, "status": r.status, "source": r.source, "description": r.description,
        "has_thumbnail": bool(r.thumbnail_path), "clip_id": r.clip_id,
        "clip_status": clip.status if clip is not None else None, "verified": verified, "filename": r.filename,
    }


@router.get("/categories")
def categories():
    return {"items": [{"key": k, "label": v["label"]} for k, v in CATEGORIES.items()]}


@router.post("/videos/{video_id}/run")
def run(video_id: int, body: RunIn, db: Session = Depends(get_db)):
    v = _video(db, video_id)
    if v.width is None:
        raise HTTPException(400, "Scene detection needs a video file (this file is audio only)")
    cats, seen = [], set()
    for c in body.categories:
        if c.key not in CATEGORIES:
            raise HTTPException(400, f"Unknown category: {c.key}")
        if c.key in seen:
            continue
        seen.add(c.key)
        if c.key == "custom" and len(c.custom_text.strip()) < 3:
            raise HTTPException(400, "Describe the custom scene category")
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
    active = db.scalars(select(Job).where(Job.type == "scene_classify", Job.video_id == video_id,
                                          Job.status.in_(["queued", "processing"]))).first()
    if active:
        return {"job_id": active.id, "already_running": True}
    payload = {"video_id": video_id, "categories": cats, "options": body.options.model_dump()}
    job = Job(type="scene_classify", video_id=video_id, status="queued", payload=json.dumps(payload))
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"job_id": job.id, "already_running": False}


@router.get("/videos/{video_id}/scenes")
def list_scenes(video_id: int, category: str = "", db: Session = Depends(get_db)):
    _video(db, video_id)
    stmt = select(CategoryScene).where(CategoryScene.video_id == video_id)
    if category:
        stmt = stmt.where(CategoryScene.category == category)
    rows = db.scalars(stmt.order_by(CategoryScene.category, CategoryScene.start_sec)).all()
    clips = {c.id: c for c in db.scalars(select(Clip).where(Clip.id.in_([r.clip_id for r in rows if r.clip_id]))).all()} if rows else {}
    info = db.get(Setting, f"scene_ai_info:{video_id}")
    return {"items": [scene_dict(r, clips.get(r.clip_id)) for r in rows],
            "info": json.loads(info.value) if info else None}


@router.get("/scenes/{scene_id}/thumbnail")
def scene_thumbnail(scene_id: int, db: Session = Depends(get_db)):
    r = db.get(CategoryScene, scene_id)
    if not r or not r.thumbnail_path:
        raise HTTPException(404, "No thumbnail")
    try:
        p = resolve_storage(r.thumbnail_path)
    except ValueError:
        raise HTTPException(400, "Invalid path")
    if not p.is_file():
        raise HTTPException(404, "Thumbnail missing on disk")
    return FileResponse(p, media_type="image/jpeg")


@router.patch("/scenes/{scene_id}")
def adjust_scene(scene_id: int, body: AdjustIn, db: Session = Depends(get_db)):
    r = db.get(CategoryScene, scene_id)
    if not r:
        raise HTTPException(404, "Scene not found")
    v = db.get(Video, r.video_id)
    end = body.end_sec
    if v is not None and v.duration_sec:
        end = min(end, v.duration_sec)
    if end - body.start_sec < 1.0:
        raise HTTPException(400, "A scene must be at least 1 second long")
    clip = db.get(Clip, r.clip_id) if r.clip_id else None
    if clip is not None and clip.status in ("pending", "processing", "ready"):
        raise HTTPException(409, "This scene was already extracted. Delete its clip first, then adjust it.")
    r.start_sec, r.end_sec = round(body.start_sec, 2), round(end, 2)
    db.commit()
    return scene_dict(r, clip)


@router.delete("/scenes/{scene_id}")
def delete_scene(scene_id: int, db: Session = Depends(get_db)):
    r = db.get(CategoryScene, scene_id)
    if not r:
        raise HTTPException(404, "Scene not found")
    db.delete(r)  # the exported clip (if any) stays in Generated Clips
    db.commit()
    return {"deleted": scene_id}


@router.delete("/videos/{video_id}/scenes")
def clear_scenes(video_id: int, db: Session = Depends(get_db)):
    _video(db, video_id)
    db.execute(delete(CategoryScene).where(CategoryScene.video_id == video_id))
    db.commit()
    return {"cleared": True}


@router.post("/videos/{video_id}/extract")
def extract(video_id: int, body: ExtractIn, db: Session = Depends(get_db)):
    v = _video(db, video_id)
    rows = db.scalars(select(CategoryScene).where(CategoryScene.video_id == video_id,
                                                  CategoryScene.id.in_(body.scene_ids))
                      .order_by(CategoryScene.category, CategoryScene.start_sec)).all()
    if not rows:
        raise HTTPException(404, "No matching scenes")
    segments = None
    if body.subtitles:
        tr = db.scalars(select(Transcript).where(Transcript.video_id == video_id).order_by(Transcript.id.desc())).first()
        segments = json.loads(tr.segments or "[]") if tr else None
    created = create_clips(db, v, rows, body.mode, body.subtitles, segments)
    return {"created": len(created), "clips": created}


@router.get("/videos/{video_id}/export.zip")
def export_zip(video_id: int, category: str = "", db: Session = Depends(get_db)):
    _video(db, video_id)
    stmt = select(CategoryScene).where(CategoryScene.video_id == video_id, CategoryScene.clip_id.is_not(None))
    if category:
        stmt = stmt.where(CategoryScene.category == category)
    files = []
    for r in db.scalars(stmt).all():
        c = db.get(Clip, r.clip_id)
        if c and c.status == "ready" and c.file_path:
            try:
                p = resolve_storage(c.file_path)
            except ValueError:
                continue
            if p.is_file():
                files.append((f"{r.category}/{p.name}", p))
                srt = p.with_suffix(".srt")
                if srt.is_file():
                    files.append((f"{r.category}/{srt.name}", srt))
    if not files:
        raise HTTPException(404, "No extracted clips to export yet")
    tmp = config.STORAGE_DIR / "temporary"
    tmp.mkdir(parents=True, exist_ok=True)
    zp = tmp / f"export_{video_id}_{uuid.uuid4().hex[:8]}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:
        for arc, p in files:
            z.write(p, arc)
    return FileResponse(zp, media_type="application/zip", filename=f"clipforge_scenes_{video_id}.zip",
                        background=BackgroundTask(lambda: zp.unlink(missing_ok=True)))