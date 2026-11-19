"""Read-only app status for the Settings page. The Gemini key itself is NEVER returned."""
import importlib.util
import os
import platform
import shutil

import psutil
from fastapi import APIRouter

from backend import config

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _dir_stats(path):
    total = files = 0
    for dp, _dirs, fs in os.walk(path):
        for f in fs:
            try:
                total += os.path.getsize(os.path.join(dp, f))
                files += 1
            except OSError:
                pass
    return total, files


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _libass() -> bool:
    try:
        from backend.captions.burn import has_subtitles_filter
        return bool(has_subtitles_filter())
    except Exception:
        return False


@router.get("")
def get_settings():
    try:
        jobs = int(os.getenv("MAX_CONCURRENT_JOBS", "1") or 1)
    except ValueError:
        jobs = 1
    jobs = min(max(jobs, 1), 4)

    base = config.STORAGE_DIR
    folders = []
    used = 0
    for name in config.SUBDIRS:
        size, files = _dir_stats(base / name)
        used += size
        folders.append({"name": name, "bytes": size, "files": files})
    try:
        du = shutil.disk_usage(base)
        free, total = du.free, du.total
    except OSError:
        free = total = 0
    mem = psutil.virtual_memory()
    return {
        "python": platform.python_version(),
        "max_concurrent_jobs": jobs,
        "ai": {
            "gemini_key_set": bool(os.getenv("GEMINI_API_KEY", "").strip()),
            "whisper_model": os.getenv("WHISPER_MODEL", "small"),
            "whisper_language": os.getenv("WHISPER_LANGUAGE", "") or "auto",
        },
        "tools": {
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "ffprobe": shutil.which("ffprobe") is not None,
            "libass": _libass(),
            "opencv": _opencv_ok(),
            "faster_whisper": _has_module("faster_whisper"),
            "scenedetect": _has_module("scenedetect"),
            "yt_dlp": _has_module("yt_dlp"),
        },
        "storage": {"path": str(base), "used_bytes": used, "free_bytes": free, "total_bytes": total, "folders": folders},
        "system": {"ram_percent": mem.percent, "ram_total_bytes": mem.total},
    }


def _opencv_ok() -> bool:
    """True only if OpenCV imports AND has the face detector (needed for face tracking)."""
    try:
        import cv2
        return hasattr(cv2, "CascadeClassifier")
    except Exception:
        return False
