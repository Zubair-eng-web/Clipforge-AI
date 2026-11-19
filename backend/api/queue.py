import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from backend.database.db import get_db
from backend.database.models import Clip, Job, utcnow

router = APIRouter(prefix="/api/queue", tags=["queue"])
FINISHED = ["completed", "failed", "cancelled"]


def _clip_ids(payload):
    try:
        d = json.loads(payload or "{}")
    except ValueError:
        return []
    return [i for i in (d.get("clip_id"), d.get("new_clip_id")) if i]


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    rows = db.execute(select(Job.status, func.count()).group_by(Job.status)).all()
    counts = {s: n for s, n in rows}
    running = db.scalars(select(Job).where(Job.status == "processing").order_by(Job.id)).all()
    return {
        "counts": {k: counts.get(k, 0) for k in ["queued", "processing", "completed", "failed", "cancelled"]},
        "running": [{"id": j.id, "type": j.type, "progress": j.progress} for j in running],
    }


@router.post("/{job_id}/retry")
def retry(job_id: int, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    if j.status not in ("failed", "cancelled"):
        raise HTTPException(409, "Only failed or cancelled jobs can be retried")
    new = Job(type=j.type, video_id=j.video_id, payload=j.payload, status="queued", progress=0.0)
    db.add(new)
    for cid in _clip_ids(j.payload):
        db.execute(update(Clip).where(Clip.id == cid, Clip.status.in_(["failed", "cancelled"])).values(status="pending"))
    db.commit()
    db.refresh(new)
    return {"id": new.id, "type": new.type, "status": new.status}


@router.post("/cancel-queued")
def cancel_queued(db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).where(Job.status == "queued")).all()
    for j in jobs:
        j.status = "cancelled"
        j.error = "Cancelled by user"
        j.updated_at = utcnow()
        for cid in _clip_ids(j.payload):
            db.execute(update(Clip).where(Clip.id == cid, Clip.status.in_(["pending", "processing"])).values(status="cancelled"))
    db.commit()
    return {"cancelled": len(jobs)}


@router.post("/clear-finished")
def clear_finished(db: Session = Depends(get_db)):
    n = db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(FINISHED))) or 0
    db.execute(delete(Job).where(Job.status.in_(FINISHED)))
    db.commit()
    return {"deleted": n}