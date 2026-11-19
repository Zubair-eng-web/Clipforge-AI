from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database.db import get_db
from backend.database.models import Clip, Collection, CollectionClip, Job, Project, Thumbnail, Video, utcnow

projects_router = APIRouter(prefix="/api/projects", tags=["projects"])
collections_router = APIRouter(prefix="/api/collections", tags=["collections"])
history_router = APIRouter(prefix="/api/history", tags=["history"])


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    video_id: Optional[int] = None


class ProjectPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    video_id: Optional[int] = None


class CollectionIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ClipIds(BaseModel):
    clip_ids: List[int] = Field(min_length=1, max_length=100)


def _project(p: Project, db: Session) -> dict:
    v = db.get(Video, p.video_id) if p.video_id else None
    n = db.scalar(select(func.count()).select_from(Clip).where(Clip.video_id == p.video_id)) if p.video_id else 0
    return {
        "id": p.id, "name": p.name, "description": p.description, "video_id": p.video_id,
        "video_name": v.original_name if v else None, "clip_count": n or 0,
        "created_at": p.created_at.isoformat(), "updated_at": p.updated_at.isoformat(),
    }


def _check_video(db: Session, video_id):
    if video_id is not None and db.get(Video, video_id) is None:
        raise HTTPException(404, "Video not found")


@projects_router.get("")
def list_projects(db: Session = Depends(get_db)):
    rows = db.scalars(select(Project).order_by(Project.id.desc())).all()
    return {"items": [_project(p, db) for p in rows]}


@projects_router.post("")
def create_project(body: ProjectIn, db: Session = Depends(get_db)):
    _check_video(db, body.video_id)
    p = Project(name=body.name.strip(), description=body.description, video_id=body.video_id)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _project(p, db)


@projects_router.get("/{pid}")
def get_project(pid: int, db: Session = Depends(get_db)):
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "Project not found")
    out = _project(p, db)
    clips = db.scalars(select(Clip).where(Clip.video_id == p.video_id).order_by(Clip.id.desc())).all() if p.video_id else []
    out["clips"] = [{"id": c.id, "title": c.title, "status": c.status, "duration_sec": c.duration_sec} for c in clips]
    return out


@projects_router.patch("/{pid}")
def update_project(pid: int, body: ProjectPatch, db: Session = Depends(get_db)):
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "Project not found")
    data = body.model_dump(exclude_unset=True)
    if "video_id" in data:
        _check_video(db, data["video_id"])
    for k, v in data.items():
        if k == "name" and v is not None:
            v = v.strip()
        setattr(p, k, v)
    p.updated_at = utcnow()
    db.commit()
    return _project(p, db)


@projects_router.delete("/{pid}")
def delete_project(pid: int, db: Session = Depends(get_db)):
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "Project not found")
    db.delete(p)  # only the project entry; videos and clips stay
    db.commit()
    return {"deleted": pid}


def _collection(c: Collection, db: Session) -> dict:
    n = db.scalar(select(func.count()).select_from(CollectionClip).where(CollectionClip.collection_id == c.id)) or 0
    return {"id": c.id, "name": c.name, "description": c.description, "clip_count": n, "created_at": c.created_at.isoformat()}


@collections_router.get("")
def list_collections(db: Session = Depends(get_db)):
    rows = db.scalars(select(Collection).order_by(Collection.id.desc())).all()
    return {"items": [_collection(c, db) for c in rows]}


@collections_router.post("")
def create_collection(body: CollectionIn, db: Session = Depends(get_db)):
    c = Collection(name=body.name.strip(), description=body.description)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _collection(c, db)


@collections_router.get("/{cid}")
def get_collection(cid: int, db: Session = Depends(get_db)):
    c = db.get(Collection, cid)
    if not c:
        raise HTTPException(404, "Collection not found")
    out = _collection(c, db)
    clips = db.scalars(
        select(Clip).join(CollectionClip, CollectionClip.clip_id == Clip.id)
        .where(CollectionClip.collection_id == cid).order_by(CollectionClip.id.desc())
    ).all()
    out["clips"] = [{"id": k.id, "title": k.title, "status": k.status, "duration_sec": k.duration_sec} for k in clips]
    return out


@collections_router.delete("/{cid}")
def delete_collection(cid: int, db: Session = Depends(get_db)):
    c = db.get(Collection, cid)
    if not c:
        raise HTTPException(404, "Collection not found")
    db.delete(c)  # clips themselves are not deleted
    db.commit()
    return {"deleted": cid}


@collections_router.post("/{cid}/clips")
def add_clips(cid: int, body: ClipIds, db: Session = Depends(get_db)):
    if not db.get(Collection, cid):
        raise HTTPException(404, "Collection not found")
    have = set(db.scalars(select(CollectionClip.clip_id).where(CollectionClip.collection_id == cid)).all())
    added = 0
    for clip_id in dict.fromkeys(body.clip_ids):
        if clip_id in have or db.get(Clip, clip_id) is None:
            continue
        db.add(CollectionClip(collection_id=cid, clip_id=clip_id))
        added += 1
    db.commit()
    return {"added": added}


@collections_router.delete("/{cid}/clips/{clip_id}")
def remove_clip(cid: int, clip_id: int, db: Session = Depends(get_db)):
    row = db.scalar(select(CollectionClip).where(CollectionClip.collection_id == cid, CollectionClip.clip_id == clip_id))
    if not row:
        raise HTTPException(404, "Clip is not in this collection")
    db.delete(row)
    db.commit()
    return {"removed": clip_id}


@history_router.get("")
def history(limit: int = 60, kind: str = "", db: Session = Depends(get_db)):
    limit = min(max(limit, 1), 200)
    items = []
    if kind in ("", "video"):
        for v in db.scalars(select(Video).order_by(Video.id.desc()).limit(limit)).all():
            items.append({"kind": "video", "id": v.id, "title": v.original_name, "status": v.status, "at": v.created_at.isoformat()})
    if kind in ("", "clip"):
        for c in db.scalars(select(Clip).order_by(Clip.id.desc()).limit(limit)).all():
            items.append({"kind": "clip", "id": c.id, "title": c.title, "status": c.status, "at": c.created_at.isoformat()})
    if kind in ("", "job"):
        for j in db.scalars(select(Job).order_by(Job.id.desc()).limit(limit)).all():
            items.append({"kind": "job", "id": j.id, "title": j.type, "status": j.status, "at": j.created_at.isoformat()})
    if kind in ("", "thumbnail"):
        for t in db.scalars(select(Thumbnail).order_by(Thumbnail.id.desc()).limit(limit)).all():
            items.append({"kind": "thumbnail", "id": t.id, "title": t.title or "Thumbnail", "status": "saved", "at": t.created_at.isoformat()})
    items.sort(key=lambda x: x["at"], reverse=True)
    return {"items": items[:limit]}