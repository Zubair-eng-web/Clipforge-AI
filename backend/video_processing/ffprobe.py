import json
import shutil
import subprocess


class ProbeError(Exception):
    pass


def probe(path) -> dict:
    exe = shutil.which("ffprobe")
    if not exe:
        raise ProbeError("ffprobe not found. Install FFmpeg and restart VS Code.")
    try:
        r = subprocess.run(
            [exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
    except subprocess.TimeoutExpired:
        raise ProbeError("ffprobe timed out while reading the file")
    if r.returncode != 0:
        raise ProbeError("This is not a valid audio/video file")
    try:
        data = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        raise ProbeError("Could not read media information")

    streams = data.get("streams", [])
    video = next(
        (s for s in streams
         if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic", 0) != 1),
        None,
    )
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not video and not audio:
        raise ProbeError("No audio or video stream found in this file")

    raw = data.get("format", {}).get("duration") or (video or audio).get("duration")
    try:
        duration = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        duration = None

    return {
        "duration_sec": duration,
        "width": video.get("width") if video else None,
        "height": video.get("height") if video else None,
    }