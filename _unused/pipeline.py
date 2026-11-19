"""Analysis pipeline: transcript -> scenes -> highlight candidates -> scores."""
import time

from backend.ai.highlights import build_candidates, score_candidates

FIELDS = ("start", "end", "duration", "score", "local_score", "title", "reason", "text", "source")


def analyze_video(
    path,
    duration,
    progress,
    language=None,
    use_gemini=True,
    transcribe_fn=None,
    scenes_fn=None,
    ask=None,
    sleep=time.sleep,
) -> dict:
    """Run the full analysis. progress(0..1) is called between stages."""
    if transcribe_fn is None:
        from backend.audio_processing.transcribe import transcribe as transcribe_fn
    if scenes_fn is None:
        from backend.scene_detection.detect import detect_scenes as scenes_fn

    progress(0.02)
    tr = transcribe_fn(path, duration, lambda p: progress(0.02 + 0.68 * p), language)
    segments = tr.get("segments", [])
    progress(0.70)
    scenes = scenes_fn(path)
    progress(0.85)
    cands = build_candidates(segments, scenes)
    scored, source, note = score_candidates(cands, use_gemini, ask=ask, sleep=sleep)
    progress(0.97)
    if not segments:
        note = "No speech detected - nothing to score."
    highlights = [
        {"rank": rank, **{k: c[k] for k in FIELDS}} for rank, c in enumerate(scored, 1)
    ]
    return {
        "language": tr.get("language"),
        "segments": segments,
        "scenes": scenes,
        "highlights": highlights,
        "scoring_source": source,
        "note": note,
    }