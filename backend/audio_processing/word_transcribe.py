"""Word-level speech to text for short clips (Smart Captions)."""
import os
import uuid
from typing import Callable, Optional

from backend import config
from backend.audio_processing.transcribe import _get_model, whisper_model_name
from backend.video_processing.ffmpeg_service import FfmpegError, _run

ProgressCb = Optional[Callable[[float], None]]


def transcribe_words(src, duration_sec: float = 0.0, on_progress: ProgressCb = None,
                     language: Optional[str] = None) -> dict:
    """Returns {language, duration_sec, model, words:[{start, end, word}]}."""
    def report(p: float) -> None:
        if on_progress:
            on_progress(min(max(p, 0.0), 1.0))

    tmp_dir = config.STORAGE_DIR / "temporary"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    wav = tmp_dir / f"{uuid.uuid4().hex}.wav"
    try:
        try:
            _run(["-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
                 float(duration_sec or 0.0), lambda p: report(p * 0.1))
        except FfmpegError as e:
            raise RuntimeError(f"Could not read the audio of this clip (no audio track?): {str(e)[-200:]}")
        report(0.1)
        model = _get_model()
        lang = (language or "").strip() or os.getenv("WHISPER_LANGUAGE", "").strip() or None
        beam = int(os.getenv("WHISPER_BEAM_SIZE", "1") or 1)
        vad = os.getenv("WHISPER_VAD", "1") != "0"
        segments, info = model.transcribe(
            str(wav), language=lang, beam_size=beam, vad_filter=vad,
            word_timestamps=True, condition_on_previous_text=False,
        )
        total = float(getattr(info, "duration", 0) or duration_sec or 0.0)
        words = []
        for seg in segments:
            for w in (seg.words or []):
                t = (w.word or "").strip()
                if t:
                    words.append({"start": round(float(w.start), 2), "end": round(float(w.end), 2), "word": t})
            if total > 0:
                report(0.1 + 0.9 * min(float(seg.end) / total, 1.0))
        report(1.0)
        return {"language": info.language, "duration_sec": total, "model": whisper_model_name(), "words": words}
    finally:
        wav.unlink(missing_ok=True)