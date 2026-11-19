"""High-quality single frame grab (used by Thumbnail Studio)."""
import subprocess
from pathlib import Path

from backend.video_processing.ffmpeg_service import _NO_WINDOW, FfmpegError, _exe


def grab_frame_hd(src, dst, at_sec: float = 0.0, long_side: int = 1280) -> None:
    dst = Path(dst)
    dst.unlink(missing_ok=True)
    vf = f"scale=w='if(gte(iw,ih),{long_side},-2)':h='if(gte(iw,ih),-2,{long_side})'"
    cmd = [_exe(), "-hide_banner", "-nostdin", "-y", "-ss", f"{max(at_sec, 0.0):.3f}", "-i", str(src),
           "-frames:v", "1", "-vf", vf, "-q:v", "2", str(dst)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=60, creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise FfmpegError("Frame grab timed out")
    if r.returncode != 0 or not dst.is_file() or dst.stat().st_size == 0:
        dst.unlink(missing_ok=True)
        raise FfmpegError((r.stderr or "Could not grab a frame")[-400:])