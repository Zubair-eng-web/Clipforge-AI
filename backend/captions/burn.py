"""Burn an ASS subtitle file into a video (needs an FFmpeg build with libass)."""
import collections
import re
import subprocess
from pathlib import Path
from typing import Callable, Optional

from backend.video_processing.ffmpeg_service import _NO_WINDOW, _PROGRESS_KEYS, FfmpegError, _exe

ProgressCb = Optional[Callable[[float], None]]
_CACHE = {}


def has_subtitles_filter() -> bool:
    if "v" not in _CACHE:
        try:
            r = subprocess.run([_exe(), "-hide_banner", "-filters"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=30, creationflags=_NO_WINDOW)
            _CACHE["v"] = bool(re.search(r"(?m)^\s*[A-Z.]{3}\s+subtitles\s", r.stdout))
        except Exception:
            _CACHE["v"] = False
    return _CACHE["v"]


def burn_captions(src, ass_path, dst, total_sec: float = 0.0, on_progress: ProgressCb = None) -> None:
    """Re-encode video with the captions drawn in. Audio is copied. Original is never modified.
    FFmpeg runs inside the .ass folder, so the filter gets a plain file name (no Windows path escaping)."""
    src, ass_path, dst = Path(src).resolve(), Path(ass_path).resolve(), Path(dst).resolve()
    cmd = [
        _exe(), "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats",
        "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", f"subtitles={ass_path.name}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-movflags", "+faststart", str(dst),
    ]
    tail = collections.deque(maxlen=25)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace", creationflags=_NO_WINDOW, cwd=str(ass_path.parent))
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.strip()
            if not line:
                continue
            if line.startswith(("out_time_us=", "out_time_ms=")):
                if on_progress and total_sec > 0:
                    try:
                        us = int(line.split("=", 1)[1])
                    except ValueError:
                        continue
                    on_progress(min(max(us / 1_000_000 / total_sec, 0.0), 1.0))
            elif not _PROGRESS_KEYS.match(line):
                tail.append(line)
        code = proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    if code != 0:
        msg = "\n".join(tail)[-800:] or f"ffmpeg exited with code {code}"
        if "subtitles" in msg and "No such filter" in msg:
            msg = "This FFmpeg build has no subtitles (libass) support. " + msg
        raise FfmpegError(msg)