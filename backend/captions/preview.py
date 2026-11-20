"""Render ONE caption preview frame (JPEG) with FFmpeg + libass. Nothing is saved permanently."""
import shutil
import subprocess
import uuid
from pathlib import Path

from backend import config
from backend.video_processing.ffmpeg_service import _NO_WINDOW, _exe


def render_preview(src, ass_text: str, t: float, width: int = 720) -> bytes:
    work = config.STORAGE_DIR / "temporary" / ("cp_" + uuid.uuid4().hex)
    work.mkdir(parents=True, exist_ok=True)
    try:
        ass = work / "p.ass"
        ass.write_text(ass_text, encoding="utf-8")
        out = work / "p.jpg"
        cmd = [_exe(), "-hide_banner", "-nostdin", "-y", "-i", str(Path(src).resolve()),
               "-vf", f"subtitles={ass.name},scale={int(width)}:-2", "-ss", f"{max(t, 0.0):.3f}",
               "-frames:v", "1", "-q:v", "3", str(out.resolve())]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=120, creationflags=_NO_WINDOW, cwd=str(work))
        if r.returncode != 0 or not out.is_file():
            raise RuntimeError((r.stderr or "FFmpeg could not render a preview frame")[-400:])
        return out.read_bytes()
    finally:
        shutil.rmtree(work, ignore_errors=True)