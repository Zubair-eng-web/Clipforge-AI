"""Job handler: analyze (transcript + scenes + highlight scores)."""
import json

from sqlalchemy import select

from backend.ai.pipeline import analyze_video
from backend.database.db import SessionLocal
from backend.database.models import Video, VideoAnalysis, utcnow
from backend.services.paths import resolve_storage
from backend.workers.runner import JobCancelled, JobContext, register


def _upsert(video_id: int, **values) -> None:
    with SessionLocal() as db:
        row = db.scalar(select(VideoAnalysis).where(VideoAnalysis.video_id == video_id))
        if row is None:
            row = VideoAnalysis(video_id=video_id)
            db.add(row)
        for k, v in values.items():
            setattr(row, k, v)
        row.updated_at = utcnow()
        db.commit()


@register("analyze")
def analyze(ctx: JobContext) -> None:
    video_id = int(ctx.payload["video_id"])
    language = ctx.payload.get("language") or None
    if language == "auto":
        language = None
    use_gemini = bool(ctx.payload.get("use_gemini", True))

    with SessionLocal() as db:
        v = db.get(Video, video_id)
        if v is None:
            raise RuntimeError("Video not found")
        stored, duration = v.stored_path, (v.duration_sec or 0.0)
    src = resolve_storage(stored)
    if not src.is_file():
        raise RuntimeError("Source video file is missing on disk")

    _upsert(video_id, status="processing", error=None)
    try:
        result = analyze_video(src, duration, ctx.progress, language=language, use_gemini=use_gemini)
    except JobCancelled:
        _upsert(video_id, status="cancelled")
        raise
    except Exception as e:
        _upsert(video_id, status="failed", error=(str(e) or e.__class__.__name__)[:500])
        raise

    _upsert(
        video_id,
        status="ready",
        language=result["language"],
        transcript_json=json.dumps(result["segments"], ensure_ascii=False),
        scenes_json=json.dumps(result["scenes"]),
        highlights_json=json.dumps(result["highlights"], ensure_ascii=False),
        scoring_source=result["scoring_source"],
        note=result["note"] or None,
        error=None,
    )