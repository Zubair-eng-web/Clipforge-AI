import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database.db import get_db
from backend.database.models import CategoryScene, Clip, Transcript
from backend.database.models_phase12 import SocialText
from backend.social import generator as gen

router = APIRouter(prefix="/api/social", tags=["social"])


class GenIn(BaseModel):
    clip_id: int
    tone: str = "viral"
    platform: str = "general"
    notes: str = Field("", max_length=500)


class EditIn(BaseModel):
    title: Optional[str] = Field(None, max_length=300)
    description: Optional[str] = Field(None, max_length=2000)
    caption: Optional[str] = Field(None, max_length=1000)
    hashtags: Optional[str] = Field(None, max_length=600)
    keywords: Optional[str] = Field(None, max_length=600)
    cta: Optional[str] = Field(None, max_length=300)
    pinned_comment: Optional[str] = Field(None, max_length=600)
    approved: Optional[bool] = None


def row_dict(r: SocialText) -> dict:
    return {
        "id": r.id, "clip_id": r.clip_id, "tone": r.tone, "title": r.title or "", "description": r.description or "",
        "caption": r.caption or "", "hashtags": r.hashtags or "", "keywords": r.keywords or "", "cta": r.cta or "",
        "pinned_comment": r.pinned_comment or "", "approved": bool(r.approved),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _speech(db: Session, clip: Clip) -> str:
    tr = db.scalars(select(Transcript).where(Transcript.video_id == clip.video_id).order_by(Transcript.id.desc())).first()
    if not tr:
        return ""
    try:
        segs = json.loads(tr.segments or "[]")
    except ValueError:
        return ""
    a, b = float(clip.start_sec or 0), float(clip.end_sec or 0)
    parts = []
    for s in segs:
        try:
            st = float(s.get("start", 0))
            en = float(s.get("end", st))
        except (TypeError, ValueError, AttributeError):
            continue
        if en >= a and st <= b:
            parts.append(str(s.get("text", "")).strip())
    return " ".join(p for p in parts if p)[:1500]


@router.get("/options")
def options():
    return {"tones": list(gen.TONES), "platforms": gen.PLATFORMS}


@router.post("/generate")
def generate(body: GenIn, db: Session = Depends(get_db)):
    clip = db.get(Clip, body.clip_id)
    if not clip:
        raise HTTPException(404, "Clip not found")
    if body.tone not in gen.TONES:
        raise HTTPException(400, f"Unknown tone: {body.tone}")
    if body.platform not in gen.PLATFORMS:
        raise HTTPException(400, f"Unknown platform: {body.platform}")
    scene = db.scalars(select(CategoryScene).where(CategoryScene.clip_id == clip.id)).first()
    label = scene.category.replace("gta_", "").replace("_", " ").title() if scene else ""
    fields, source, warning = gen.generate(
        clip.title or "", label, (scene.description if scene else "") or "", _speech(db, clip),
        body.notes.strip(), body.tone, body.platform)
    row = SocialText(clip_id=clip.id, tone=body.tone, approved=False, **fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {**row_dict(row), "source": source, "warning": warning}


@router.get("")
def list_texts(clip_id: Optional[int] = None, db: Session = Depends(get_db)):
    stmt = select(SocialText)
    if clip_id is not None:
        stmt = stmt.where(SocialText.clip_id == clip_id)
    return {"items": [row_dict(r) for r in db.scalars(stmt.order_by(SocialText.id.desc()).limit(100)).all()]}


@router.put("/{text_id}")
def edit(text_id: int, body: EditIn, db: Session = Depends(get_db)):
    r = db.get(SocialText, text_id)
    if not r:
        raise HTTPException(404, "Not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return row_dict(r)


@router.delete("/{text_id}")
def delete(text_id: int, db: Session = Depends(get_db)):
    r = db.get(SocialText, text_id)
    if not r:
        raise HTTPException(404, "Not found")
    db.delete(r)
    db.commit()
    return {"deleted": text_id}