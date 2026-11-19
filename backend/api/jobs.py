import asyncio
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.database.db import SessionLocal, get_db
from backend.database.models import Clip, Job, utcnow

router = APIRouter(prefix="/api/jobs", tags=["jobs"])
TERMINAL = {"completed", "failed", "cancelled"}


def job_dict(j: Job) -> dict:
    return {
        "id": j.id,
        "type": j.type,
        "video_id": j.video_id,
        "status": j.status,
        "progress": j.progress,
        "error": j.error,
        "created_at": j.created_at.isoformat(),
        "updated_at": j.updated_at.isoformat(),
    }


@router.get("")
def list_jobs(status: str = "", limit: int = 50, db: Session = Depends(get_db)):
    stmt = select(Job)
    if status:
        stmt = stmt.where(Job.status == status)
    rows = db.scalars(stmt.order_by(Job.id.desc()).limit(min(max(limit, 1), 200))).all()
    return {"items": [job_dict(j) for j in rows]}


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    return job_dict(j)


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, "Job not found")
    if j.status in TERMINAL:
        raise HTTPException(409, "Job already finished")
    try:
        clip_id = json.loads(j.payload or "{}").get("clip_id")
    except ValueError:
        clip_id = None
    db.execute(
        update(Job).where(Job.id == job_id, Job.status.in_(["queued", "processing"]))
        .values(status="cancelled", error="Cancelled by user", updated_at=utcnow())
    )
    try:
        new_clip_id = json.loads(j.payload or "{}").get("new_clip_id")
    except ValueError:
        new_clip_id = None
    if new_clip_id:
        db.execute(update(Clip).where(Clip.id == new_clip_id, Clip.status.in_(["pending", "processing"]))
                   .values(status="cancelled"))
    if clip_id:
        db.execute(update(Clip).where(Clip.id == clip_id, Clip.status.in_(["pending", "processing"]))
                   .values(status="cancelled"))
    db.commit()
    db.refresh(j)
    return job_dict(j)


@router.get("/{job_id}/events")
async def job_events(job_id: int, request: Request):
    """Server-Sent Events: streams job progress until the job finishes."""
    with SessionLocal() as db:
        if db.get(Job, job_id) is None:
            raise HTTPException(404, "Job not found")

    async def gen():
        last = None
        last_send = time.monotonic()
        while True:
            if await request.is_disconnected():
                break
            with SessionLocal() as db:
                j = db.get(Job, job_id)
                data = job_dict(j) if j else None
            if data is None:
                yield 'data: {"status": "failed", "error": "Job disappeared"}\n\n'
                break
            payload = json.dumps(data)
            if payload != last:
                yield f"data: {payload}\n\n"
                last, last_send = payload, time.monotonic()
            elif time.monotonic() - last_send > 15:
                yield ": ping\n\n"
                last_send = time.monotonic()
            if data["status"] in TERMINAL:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
