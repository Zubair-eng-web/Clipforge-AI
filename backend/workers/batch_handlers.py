"""Job handler 'batch_video': analyze one video (if needed), then queue its best clips for export."""
import json

from sqlalchemy import select

from backend.clip_generation.selector import select_clips
from backend.database.db import SessionLocal
from backend.database.models import Clip, Job, Video, VideoAnalysis
from backend.workers.analysis_handlers import analyze
from backend.workers.runner import JobContext, register


class _SubContext:
    """Looks like a JobContext to the analyze handler but reports into the first 90% of this job."""

    def __init__(self, parent: JobContext, payload: dict):
        self.job_id = parent.job_id
        self.payload = payload
        self._parent = parent

    def progress(self, p: float) -> None:
        self._parent.progress(min(max(p, 0.0), 1.0) * 0.9)


def _analysis_ready(video_id: int) -> bool:
    with SessionLocal() as db:
        va = db.scalar(select(VideoAnalysis).where(VideoAnalysis.video_id == video_id))
        return va is not None and va.status == "ready"


@register("batch_video")
def batch_video(ctx: JobContext) -> None:
    p = ctx.payload
    video_id = int(p["video_id"])
    count = int(p.get("count", 5))
    mode = p.get("mode", "accurate")
    min_score = float(p.get("min_score", 0.0))
    use_gemini = bool(p.get("use_gemini", True))

    with SessionLocal() as db:
        video = db.get(Video, video_id)
        if video is None:
            raise RuntimeError("Video not found")
        duration = video.duration_sec

    if not _analysis_ready(video_id):
        analyze(_SubContext(ctx, {"video_id": video_id, "use_gemini": use_gemini}))

    with SessionLocal() as db:
        va = db.scalar(select(VideoAnalysis).where(VideoAnalysis.video_id == video_id))
        if va is None or va.status != "ready":
            raise RuntimeError("Analysis did not finish")
        try:
            highlights = json.loads(va.highlights_json or "[]")
        except ValueError:
            highlights = []
        if not highlights:
            raise RuntimeError("No highlights found (video may have no speech)")
        existing = db.scalars(
            select(Clip).where(Clip.video_id == video_id, Clip.status.in_(["pending", "processing", "ready"]))
        ).all()
        chosen = select_clips(
            highlights, count=count, min_score=min_score, duration=duration,
            pad_before=0.0, pad_after=0.0, blocked=[(c.start_sec, c.end_sec) for c in existing],
        )
        if not chosen:
            raise RuntimeError("No new clips available (all good highlights already used or score too low)")
        for c in chosen:
            clip = Clip(video_id=video_id, title=c["title"], start_sec=c["start"], end_sec=c["end"],
                        duration_sec=c["duration"], status="pending", ai_score=c["score"])
            db.add(clip)
            db.flush()
            db.add(Job(type="clip_export", video_id=video_id, status="queued",
                       payload=json.dumps({"clip_id": clip.id, "mode": mode})))
        db.commit()
    ctx.progress(1.0)