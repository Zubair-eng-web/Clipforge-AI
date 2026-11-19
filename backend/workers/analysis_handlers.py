"""Job handler 'analyze': transcript + scenes + highlight scoring for one video.

Results are stored in the normalized tables (transcripts, scenes, highlights) AND in the
video_analysis row (JSON), which the AI Highlights / AI Auto Clipper pages and /auto-clips read."""
import json
import logging

from sqlalchemy import delete, func, select

from backend.ai.highlights import analyze_highlights
from backend.audio_processing.transcribe import transcribe_media
from backend.database.db import SessionLocal
from backend.database.models import Highlight, Scene, Setting, Transcript, Video, VideoAnalysis, utcnow
from backend.scene_detection.detector import detect_scenes
from backend.services.paths import resolve_storage
from backend.workers.runner import JobCancelled, JobContext, register

log = logging.getLogger("clipforge.analysis")
ORDER = ("transcribe", "scenes", "highlights")
WEIGHTS = {"transcribe": 70.0, "scenes": 20.0, "highlights": 10.0}


def info_key(video_id: int) -> str:
    return f"analysis_info:{video_id}"


def _sub(ctx: JobContext, lo: float, hi: float):
    def cb(p: float) -> None:
        ctx.progress(lo + (hi - lo) * min(max(p, 0.0), 1.0))
    return cb


def _upsert_va(video_id: int, **values) -> None:
    with SessionLocal() as db:
        row = db.scalar(select(VideoAnalysis).where(VideoAnalysis.video_id == video_id))
        if row is None:
            row = VideoAnalysis(video_id=video_id)
            db.add(row)
        for k, v in values.items():
            setattr(row, k, v)
        row.updated_at = utcnow()
        db.commit()


def _safe_upsert_va(video_id: int, **values) -> None:
    try:
        _upsert_va(video_id, **values)
    except Exception:
        log.exception("could not update video_analysis for video %s", video_id)


def _sync_va(video_id: int) -> None:
    """Rebuild the video_analysis row from the normalized tables."""
    with SessionLocal() as db:
        tr = db.scalars(select(Transcript).where(Transcript.video_id == video_id)
                        .order_by(Transcript.id.desc())).first()
        if tr is None:
            return
        language = tr.language
        segments_json = tr.segments or "[]"
        segments = json.loads(segments_json)
        scenes = [{"index": s.idx, "start": s.start_sec, "end": s.end_sec}
                  for s in db.scalars(select(Scene).where(Scene.video_id == video_id).order_by(Scene.idx)).all()]
        rows = db.scalars(select(Highlight).where(Highlight.video_id == video_id)
                          .order_by(Highlight.score.desc(), Highlight.id)).all()
        highlights = [
            {"rank": i, "start": h.start_sec, "end": h.end_sec, "duration": round(h.end_sec - h.start_sec, 2),
             "score": h.score, "local_score": h.local_score, "title": h.title, "reason": h.reason,
             "text": h.text, "source": h.source}
            for i, h in enumerate(rows, 1)
        ]
        row = db.get(Setting, info_key(video_id))
        info = json.loads(row.value) if row else {}
    source = "gemini" if info.get("gemini_used") else "local"
    note = "; ".join(info.get("warnings") or [])
    if not segments:
        note = "No speech detected - nothing to score."
    _upsert_va(
        video_id, status="ready", error=None, language=language, transcript_json=segments_json,
        scenes_json=json.dumps(scenes), highlights_json=json.dumps(highlights, ensure_ascii=False),
        scoring_source=source, note=(note[:500] or None),
    )


def _run_steps(ctx, video_id, src, duration, has_video, have_transcript, steps, use_gemini, force, language):
    todo = []
    for s in steps:
        if s == "scenes" and not has_video:
            continue
        if s == "transcribe" and have_transcript and not force:
            continue
        todo.append(s)
    if "highlights" in todo and "transcribe" not in todo and not have_transcript:
        raise RuntimeError("Highlights need a transcript. Run the transcribe step first.")

    total = sum(WEIGHTS[s] for s in todo) or 1.0
    done = 0.0
    for s in todo:
        cb = _sub(ctx, done / total, min((done + WEIGHTS[s]) / total, 0.99))

        if s == "transcribe":
            kwargs = {"language": language} if language else {}
            result = transcribe_media(src, duration, cb, **kwargs)
            with SessionLocal() as db:
                db.execute(delete(Transcript).where(Transcript.video_id == video_id))
                db.add(Transcript(
                    video_id=video_id,
                    language=result.get("language"),
                    language_probability=result.get("language_probability"),
                    duration_sec=result.get("duration_sec") or duration,
                    text=result.get("text", ""),
                    segments=json.dumps(result.get("segments", []), ensure_ascii=False),
                    model=result.get("model"),
                ))
                db.commit()

        elif s == "scenes":
            scenes = detect_scenes(src, duration, cb)
            with SessionLocal() as db:
                db.execute(delete(Scene).where(Scene.video_id == video_id))
                for sc in scenes:
                    db.add(Scene(video_id=video_id, idx=sc["idx"], start_sec=sc["start"], end_sec=sc["end"]))
                db.commit()

        elif s == "highlights":
            with SessionLocal() as db:
                tr = db.scalars(select(Transcript).where(Transcript.video_id == video_id)
                                .order_by(Transcript.id.desc())).first()
                segments = json.loads(tr.segments) if tr else []
            items, info = analyze_highlights(segments, use_gemini=use_gemini, on_progress=cb)
            with SessionLocal() as db:
                db.execute(delete(Highlight).where(Highlight.video_id == video_id))
                for h in items:
                    db.add(Highlight(
                        video_id=video_id, start_sec=h["start"], end_sec=h["end"], score=h["score"],
                        local_score=h["local_score"], title=h["title"][:300], reason=h["reason"],
                        text=h["text"], source=h["source"],
                    ))
                row = db.get(Setting, info_key(video_id))
                payload = json.dumps(info, ensure_ascii=False)
                if row:
                    row.value = payload
                else:
                    db.add(Setting(key=info_key(video_id), value=payload))
                db.commit()
            for w in info["warnings"]:
                log.warning("video %s: %s", video_id, w)
        done += WEIGHTS[s]


@register("analyze")
def analyze(ctx: JobContext) -> None:
    video_id = int(ctx.payload["video_id"])
    wanted = ctx.payload.get("steps") or list(ORDER)
    steps = [s for s in ORDER if s in wanted]
    use_gemini = bool(ctx.payload.get("use_gemini", True))
    force = bool(ctx.payload.get("force", False))
    language = ctx.payload.get("language") or None
    if language == "auto":
        language = None

    with SessionLocal() as db:
        v = db.get(Video, video_id)
        if v is None:
            raise RuntimeError("Video not found")
        stored, duration, has_video = v.stored_path, float(v.duration_sec or 0.0), v.width is not None
        have_transcript = (db.scalar(
            select(func.count()).select_from(Transcript).where(Transcript.video_id == video_id)) or 0) > 0

    src = resolve_storage(stored)
    if not src.is_file():
        raise RuntimeError("Source video file is missing on disk")

    touches_va = any(s in steps for s in ("transcribe", "highlights"))
    if touches_va:
        _safe_upsert_va(video_id, status="processing", error=None)
    try:
        _run_steps(ctx, video_id, src, duration, has_video, have_transcript, steps, use_gemini, force, language)
        _sync_va(video_id)
    except JobCancelled:
        if touches_va:
            _safe_upsert_va(video_id, status="cancelled")
        raise
    except Exception as e:
        if touches_va:
            _safe_upsert_va(video_id, status="failed", error=(str(e) or e.__class__.__name__)[:500])
        raise