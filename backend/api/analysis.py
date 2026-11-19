import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.ai import gemini_client
from backend.audio_processing.transcribe import whisper_model_name
from backend.database.db import get_db
from backend.database.models import Highlight, Job, Scene, Setting, Transcript, Video, VideoAnalysis

router = APIRouter(prefix="/api/analysis", tags=["analysis"])
Step = Literal["transcribe", "scenes", "highlights"]


class RunBody(BaseModel):
    steps: list[Step] = Field(default_factory=lambda: ["transcribe", "scenes", "highlights"])
    use_gemini: bool = True
    force: bool = False  # True = redo the transcript even if one exists


def _video_or_404(db: Session, video_id: int) -> Video:
    v = db.get(Video, video_id)
    if not v:
        raise HTTPException(404, "Video not found")
    return v


def _count(db: Session, model, video_id: int) -> int:
    return db.scalar(select(func.count()).select_from(model).where(model.video_id == video_id)) or 0


def _active_job(db: Session, video_id: int):
    return db.scalars(
        select(Job).where(Job.type == "analyze", Job.video_id == video_id, Job.status.in_(["queued", "processing"]))
        .order_by(Job.id.desc())
    ).first()


@router.get("/status")
def analysis_status():
    return {
        "whisper_model": whisper_model_name(),
        "gemini_configured": gemini_client.is_configured(),
        "gemini_model": gemini_client.get_model(),
    }


@router.post("/videos/{video_id}/run")
def run_analysis(video_id: int, body: Optional[RunBody] = None, db: Session = Depends(get_db)):
    body = body or RunBody()
    v = _video_or_404(db, video_id)
    if not body.steps:
        raise HTTPException(400, "Choose at least one step")
    active = _active_job(db, video_id)
    if active:
        return {"job_id": active.id, "already_running": True}
    if "highlights" in body.steps and "transcribe" not in body.steps and _count(db, Transcript, video_id) == 0:
        raise HTTPException(400, "Highlights need a transcript. Include the 'transcribe' step.")
    if body.steps == ["scenes"] and v.width is None:
        raise HTTPException(400, "Scene detection needs a video file (this file is audio only)")
    job = Job(type="analyze", video_id=video_id, status="queued",
              payload=json.dumps({"video_id": video_id, "steps": body.steps,
                                  "use_gemini": body.use_gemini, "force": body.force}))
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"job_id": job.id, "already_running": False}


@router.get("/videos/{video_id}")
def analysis_summary(video_id: int, db: Session = Depends(get_db)):
    _video_or_404(db, video_id)
    tr = db.scalars(select(Transcript).where(Transcript.video_id == video_id).order_by(Transcript.id.desc())).first()
    sources = dict(db.execute(
        select(Highlight.source, func.count()).where(Highlight.video_id == video_id).group_by(Highlight.source)
    ).all())
    row = db.get(Setting, f"analysis_info:{video_id}")
    active = _active_job(db, video_id)
    return {
        "video_id": video_id,
        "has_transcript": tr is not None,
        "language": tr.language if tr else None,
        "transcript_chars": len(tr.text) if tr else 0,
        "scene_count": _count(db, Scene, video_id),
        "highlight_count": _count(db, Highlight, video_id),
        "highlight_sources": sources,
        "last_run_info": json.loads(row.value) if row else None,
        "active_job_id": active.id if active else None,
    }


@router.get("/videos/{video_id}/transcript")
def get_transcript(video_id: int, db: Session = Depends(get_db)):
    _video_or_404(db, video_id)
    tr = db.scalars(select(Transcript).where(Transcript.video_id == video_id).order_by(Transcript.id.desc())).first()
    if not tr:
        raise HTTPException(404, "No transcript yet. Run the analysis first.")
    return {
        "language": tr.language, "language_probability": tr.language_probability,
        "duration_sec": tr.duration_sec, "model": tr.model, "text": tr.text,
        "segments": json.loads(tr.segments or "[]"),
    }


@router.get("/videos/{video_id}/scenes")
def get_scenes(video_id: int, db: Session = Depends(get_db)):
    _video_or_404(db, video_id)
    rows = db.scalars(select(Scene).where(Scene.video_id == video_id).order_by(Scene.idx)).all()
    return {"total": len(rows),
            "items": [{"idx": s.idx, "start_sec": s.start_sec, "end_sec": s.end_sec} for s in rows]}


@router.get("/videos/{video_id}/highlights")
def get_highlights(video_id: int, min_score: float = 0.0, limit: int = 100, db: Session = Depends(get_db)):
    _video_or_404(db, video_id)
    rows = db.scalars(
        select(Highlight).where(Highlight.video_id == video_id, Highlight.score >= min_score)
        .order_by(Highlight.score.desc(), Highlight.id).limit(min(max(limit, 1), 500))
    ).all()
    return {"total": len(rows), "items": [
        {"id": h.id, "start_sec": h.start_sec, "end_sec": h.end_sec,
         "duration_sec": round(h.end_sec - h.start_sec, 2), "score": h.score, "local_score": h.local_score,
         "title": h.title, "reason": h.reason, "text": h.text, "source": h.source}
        for h in rows]}


@router.delete("/videos/{video_id}")
def clear_analysis(video_id: int, db: Session = Depends(get_db)):
    _video_or_404(db, video_id)
    if _active_job(db, video_id):
        raise HTTPException(409, "Analysis is running. Cancel the job first.")
    for model in (Transcript, Scene, Highlight):
        db.execute(delete(model).where(model.video_id == video_id))
    db.execute(delete(Setting).where(Setting.key == f"analysis_info:{video_id}"))
    db.execute(delete(VideoAnalysis).where(VideoAnalysis.video_id == video_id))
    db.commit()
    return {"cleared": True, "video_id": video_id}


# ---------- UI endpoints used by the AI Highlights and AI Auto Clipper pages ----------
compat_router = APIRouter(prefix="/api/videos", tags=["analysis-ui"])


class AnalyzeBody(BaseModel):
    language: Optional[str] = None   # None or "auto" = detect
    use_gemini: bool = True
    force: bool = False              # True = redo the transcript even if one exists


@compat_router.post("/{video_id}/analyze")
def analyze_for_ui(video_id: int, body: Optional[AnalyzeBody] = None, db: Session = Depends(get_db)):
    body = body or AnalyzeBody()
    _video_or_404(db, video_id)
    active = _active_job(db, video_id)
    if active:
        return {"job_id": active.id, "already_running": True}
    redo = body.force or bool(body.language and body.language != "auto")
    job = Job(type="analyze", video_id=video_id, status="queued",
              payload=json.dumps({"video_id": video_id, "language": body.language,
                                  "use_gemini": body.use_gemini, "force": redo}))
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"job_id": job.id, "already_running": False}


@compat_router.get("/{video_id}/analysis")
def analysis_for_ui(video_id: int, include_transcript: bool = True, db: Session = Depends(get_db)):
    _video_or_404(db, video_id)
    row = db.scalar(select(VideoAnalysis).where(VideoAnalysis.video_id == video_id))
    if row is None:
        return {"status": "processing" if _active_job(db, video_id) else "none"}
    segments = json.loads(row.transcript_json or "[]")
    out = {
        "status": row.status,
        "language": row.language,
        "scoring_source": row.scoring_source,
        "note": row.note,
        "error": row.error,
        "segment_count": len(segments),
        "scenes": json.loads(row.scenes_json or "[]"),
        "highlights": json.loads(row.highlights_json or "[]"),
    }
    if include_transcript:
        out["transcript"] = segments
    return out