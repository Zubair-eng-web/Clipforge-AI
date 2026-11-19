"""yt-dlp wrapper: read link info and download one video (authorized sources only; no playlists)."""
import os
import re
from pathlib import Path

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
FORMAT = "bv*[height<=1080][vcodec^=avc1]+ba[acodec^=mp4a]/bv*[height<=1080]+ba/b[height<=1080]/b"


class YoutubeError(Exception):
    pass


def max_minutes() -> int:
    try:
        return max(1, int(os.getenv("YOUTUBE_MAX_MINUTES", "60") or 60))
    except ValueError:
        return 60


def _ydl():
    try:
        import yt_dlp
    except ImportError:
        raise YoutubeError("yt-dlp is not installed. Run: .\\.venv\\Scripts\\python.exe -m pip install yt-dlp")
    return yt_dlp


def _msg(e: Exception) -> str:
    text = _ANSI.sub("", str(e)).strip()
    return text[-300:] or e.__class__.__name__


def fetch_info(url: str) -> dict:
    yt = _ydl()
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True,
            "no_color": True, "socket_timeout": 30}
    try:
        with yt.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise YoutubeError(_msg(e))
    if not info:
        raise YoutubeError("No video found at this link")
    if info.get("_type") == "playlist":
        entries = [x for x in (info.get("entries") or []) if x]
        if not entries:
            raise YoutubeError("This link has no videos")
        info = entries[0]
    return {
        "title": info.get("title") or "video",
        "duration": info.get("duration"),
        "uploader": info.get("uploader") or info.get("channel"),
        "thumbnail": info.get("thumbnail"),
        "is_live": bool(info.get("is_live")),
    }


def check_limits(info: dict) -> None:
    if info.get("is_live"):
        raise YoutubeError("Live streams are not supported")
    dur = info.get("duration")
    if dur and dur > max_minutes() * 60:
        raise YoutubeError(f"Video is longer than {max_minutes()} minutes (YOUTUBE_MAX_MINUTES in .env)")


def download_video(url: str, dest_dir, name: str, on_progress=None):
    """Downloads into dest_dir/<name>.<ext>. Returns (path, title). Exceptions raised inside on_progress
    (e.g. job cancelled) propagate to the caller."""
    yt = _ydl()
    best = [0.0]

    def hook(d):
        if d.get("status") == "downloading" and on_progress:
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                best[0] = max(best[0], min(d.get("downloaded_bytes", 0) / total, 1.0))
                on_progress(best[0])

    dest_dir = Path(dest_dir)
    opts = {
        "quiet": True, "no_warnings": True, "noplaylist": True, "no_color": True,
        "outtmpl": str(dest_dir / f"{name}.%(ext)s"), "format": FORMAT, "merge_output_format": "mp4",
        "progress_hooks": [hook], "retries": 3, "socket_timeout": 30,
    }
    try:
        with yt.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt.utils.DownloadError as e:
        raise YoutubeError(_msg(e))
    files = [p for p in dest_dir.glob(f"{name}.*") if p.suffix.lower() not in (".part", ".ytdl", ".temp")]
    if not files:
        raise YoutubeError("Download finished but no file was found")
    files.sort(key=lambda p: (p.suffix.lower() != ".mp4", -p.stat().st_size))
    return files[0], ((info or {}).get("title") or "video")