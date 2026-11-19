"""FFmpeg helpers: cut clips, build browser-preview proxies, grab frames."""
import collections
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

ProgressCb = Optional[Callable[[float], None]]  # receives 0.0 .. 1.0

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_PROGRESS_KEYS = re.compile(
    r"^(frame|fps|stream_\d+_\d+_q|bitrate|total_size|out_time_us|out_time_ms|out_time|"
    r"dup_frames|drop_frames|speed|progress)="
)


class FfmpegError(Exception):
    pass


def _exe() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise FfmpegError("ffmpeg not found. Install FFmpeg and restart VS Code.")
    return exe


def _run(args: list, total_sec: float, on_progress: ProgressCb = None) -> None:
    cmd = [_exe(), "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", *args]
    tail = collections.deque(maxlen=25)
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", creationflags=_NO_WINDOW,
    )
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
        if proc.poll() is None:  # e.g. cancelled: stop ffmpeg
            proc.kill()
            proc.wait()
    if code != 0:
        raise FfmpegError("\n".join(tail)[-800:] or f"ffmpeg exited with code {code}")


def cut_clip(src, dst, start: float, end: float, mode: str = "accurate", on_progress: ProgressCb = None) -> None:
    """Cut [start, end] seconds of src into an MP4 at dst. Original is never modified.
    mode 'accurate' = re-encode (frame exact). mode 'fast' = stream copy (instant, keyframe aligned)."""
    dur = float(end) - float(start)
    if dur <= 0:
        raise ValueError("end must be greater than start")
    args = ["-ss", f"{start:.3f}", "-i", str(src), "-t", f"{dur:.3f}", "-map", "0:v:0", "-map", "0:a:0?"]
    if mode == "fast":
        args += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
    else:
        args += [
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k",
        ]
    args += ["-movflags", "+faststart", str(dst)]
    _run(args, dur, on_progress)


def make_proxy(src, dst, total_sec: float, on_progress: ProgressCb = None) -> None:
    """Small H.264/AAC MP4 (max 720p) so any browser can preview MOV/MKV/AVI/HEVC files."""
    args = [
        "-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", "scale=-2:'min(720,trunc(ih/2)*2)'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(dst),
    ]
    _run(args, total_sec, on_progress)


def grab_frame(src, dst, at_sec: float = 0.0) -> None:
    dst = Path(dst)
    dst.unlink(missing_ok=True)
    cmd = [
        _exe(), "-hide_banner", "-nostdin", "-y", "-ss", f"{max(at_sec, 0.0):.3f}", "-i", str(src),
        "-frames:v", "1", "-vf", "scale=480:-2", "-q:v", "4", str(dst),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=60, creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise FfmpegError("Frame grab timed out")
    if r.returncode != 0 or not dst.is_file() or dst.stat().st_size == 0:
        dst.unlink(missing_ok=True)
        raise FfmpegError((r.stderr or "Could not grab a frame")[-400:])
