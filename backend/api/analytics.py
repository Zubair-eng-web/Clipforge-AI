from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.database.db import get_db
from backend.database.models import Clip, Highlight, Job, Video

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _naive(d):
    return d.replace(tzinfo=None) if d else None


@router.get("")
def analytics(db: Session = Depends(get_db)):
    videos = db.scalars(select(Video)).all()
    clips = db.scalars(select(Clip)).all()
    jobs = db.scalars(select(Job)).all()

    clip_status = Counter(c.status for c in clips)
    job_status = Counter(j.status for j in jobs)

    by_type = {}
    for j in jobs:
        t = by_type.setdefault(j.type, {"total": 0, "completed": 0, "failed": 0, "secs": []})
        t["total"] += 1
        if j.status == "completed":
            t["completed"] += 1
            if j.created_at and j.updated_at:
                t["secs"].append((_naive(j.updated_at) - _naive(j.created_at)).total_seconds())
        elif j.status == "failed":
            t["failed"] += 1
    job_types = [
        {"type": k, "total": v["total"], "completed": v["completed"], "failed": v["failed"],
         "avg_seconds": round(sum(v["secs"]) / len(v["secs"]), 1) if v["secs"] else None}
        for k, v in sorted(by_type.items())
    ]

    today = datetime.now(timezone.utc).replace(tzinfo=None).date()
    days = [(today - timedelta(days=i)) for i in range(13, -1, -1)]
    per_day = Counter(_naive(c.created_at).date() for c in clips if c.created_at)
    clips_per_day = [{"day": d.isoformat(), "count": per_day.get(d, 0)} for d in days]

    scores = [c.ai_score for c in clips if c.ai_score is not None]
    ready = [c for c in clips if c.status == "ready"]
    src = dict(db.execute(select(Highlight.source, func.count()).group_by(Highlight.source)).all())
    finished = job_status.get("completed", 0) + job_status.get("failed", 0)

    return {
        "videos": {
            "total": len(videos),
            "total_minutes": round(sum(v.duration_sec or 0 for v in videos) / 60, 1),
            "total_bytes": sum(v.size_bytes or 0 for v in videos),
        },
        "clips": {
            "total": len(clips),
            "by_status": dict(clip_status),
            "ready_minutes": round(sum(c.duration_sec or 0 for c in ready) / 60, 1),
            "avg_ai_score": round(sum(scores) / len(scores), 2) if scores else None,
            "scored_clips": len(scores),
        },
        "jobs": {
            "by_status": dict(job_status),
            "success_rate_percent": round(100 * job_status.get("completed", 0) / finished, 1) if finished else None,
            "by_type": job_types,
        },
        "highlights": {"total": sum(src.values()), "by_source": src},
        "clips_per_day": clips_per_day,
    }