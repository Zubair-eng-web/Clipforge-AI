"""Speech to text with faster-whisper (CPU, int8). The model is loaded once and reused."""
import os
import threading
import uuid
from typing import Callable, Optional

from backend import config
from backend.video_processing.ffmpeg_service import FfmpegError, _run

ProgressCb = Optional[Callable[[float], None]]  # 0.0 .. 1.0

_lock = threading.Lock()
_model = None
_model_name = None


def whisper_model_name() -> str:
    return os.getenv("WHISPER_MODEL", "small").strip() or "small"


def _get_model():
    global _model, _model_name
    name = whisper_model_name()
    with _lock:
        if _model is None or _model_name != name:
            from faster_whisper import WhisperModel
            threads = int(os.getenv("WHISPER_CPU_THREADS", "0") or 0)
            _model = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=threads)
            _model_name = name
        return _model


def transcribe_media(src, duration_sec: float = 0.0, on_progress: ProgressCb = None, language: Optional[str] = None) -> dict:
    """Returns {language, language_probability, duration_sec, model, text, segments:[{start,end,text}]}."""
    def report(p: float) -> None:
        if on_progress:
            on_progress(min(max(p, 0.0), 1.0))

    tmp_dir = config.STORAGE_DIR / "temporary"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    wav = tmp_dir / f"{uuid.uuid4().hex}.wav"
    try:
        try:
            _run(["-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
                 float(duration_sec or 0.0), lambda p: report(p * 0.08))
        except FfmpegError as e:
            raise RuntimeError(f"Could not read the audio of this file (no audio track?): {str(e)[-200:]}")
        report(0.08)
        model = _get_model()
        lang = (language or "").strip() or os.getenv("WHISPER_LANGUAGE", "").strip() or None
        beam = int(os.getenv("WHISPER_BEAM_SIZE", "1") or 1)
        vad = os.getenv("WHISPER_VAD", "1") != "0"
        segments, info = model.transcribe(
            str(wav), language=lang, beam_size=beam, vad_filter=vad, condition_on_previous_text=False
        )
        total = float(getattr(info, "duration", 0) or duration_sec or 0.0)
        out = []
        for seg in segments:
            text = (seg.text or "").strip()
            if text:
                out.append({"start": round(float(seg.start), 2), "end": round(float(seg.end), 2), "text": text})
            if total > 0:
                report(0.08 + 0.92 * min(float(seg.end) / total, 1.0))
        report(1.0)
        return {
            "language": info.language,
            "language_probability": round(float(info.language_probability or 0.0), 3),
            "duration_sec": total,
            "model": whisper_model_name(),
            "text": " ".join(s["text"] for s in out),
            "segments": out,
        }
    finally:
        wav.unlink(missing_ok=True)