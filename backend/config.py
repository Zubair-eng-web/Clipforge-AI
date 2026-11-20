import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORAGE_DIR = Path(os.getenv("CLIPFORGE_STORAGE_DIR", ROOT / "storage"))

SUBDIRS = [
    "original_videos", "generated_clips", "edited_clips", "thumbnails", "subtitles",
    "audio", "reels", "music", "captions", "projects", "collections", "exports", "temporary",
]

MEDIA_TYPES = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}
ALLOWED_EXTENSIONS = set(MEDIA_TYPES)


def max_upload_bytes() -> int:
    return int(float(os.getenv("MAX_UPLOAD_GB", "5")) * 1024**3)


def ensure_storage_dirs() -> None:
    for d in SUBDIRS:
        (STORAGE_DIR / d).mkdir(parents=True, exist_ok=True)


def safe_display_name(name: str) -> str:
    """Only used for DISPLAY. Files on disk always get random UUID names."""
    name = os.path.basename(name.replace("\\", "/"))
    name = re.sub(r'[\x00-\x1f<>:"|?*]', "_", name).strip(" .")
    return name[:200] or "video"