import importlib.metadata as md
import os
import shutil
import sys

import psutil
from fastapi import APIRouter

from backend.config import STORAGE_DIR

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


def _ver(pkg: str):
    try:
        return md.version(pkg)
    except md.PackageNotFoundError:
        return None


@router.get("")
def diagnostics():
    mem = psutil.virtual_memory()
    try:
        disk = shutil.disk_usage(STORAGE_DIR)
        disk_info = {"free_gb": round(disk.free / 1024**3, 1), "total_gb": round(disk.total / 1024**3, 1)}
    except OSError:
        disk_info = {"free_gb": None, "total_gb": None}
    tools = {"ffmpeg": shutil.which("ffmpeg"), "ffprobe": shutil.which("ffprobe")}
    packages = {p: _ver(p) for p in ("faster-whisper", "scenedetect", "opencv-python-headless", "yt-dlp", "fastapi", "sqlalchemy")}
    warnings = []
    if not tools["ffmpeg"]:
        warnings.append("FFmpeg not found in PATH. Clipping will not work.")
    if not tools["ffprobe"]:
        warnings.append("FFprobe not found in PATH. Upload validation will not work.")
    if mem.percent > 85:
        warnings.append("RAM is above 85%. Close other programs or keep MAX_CONCURRENT_JOBS=1.")
    if disk_info["free_gb"] is not None and disk_info["free_gb"] < 5:
        warnings.append("Less than 5 GB of disk space is free.")
    if not os.getenv("GEMINI_API_KEY"):
        warnings.append("GEMINI_API_KEY is not set. Scoring will use the local fallback only.")
    for name, v in packages.items():
        if v is None:
            warnings.append(f"Python package not installed: {name}")
    return {
        "python": sys.version.split()[0],
        "ram": {"used_percent": mem.percent, "available_gb": round(mem.available / 1024**3, 1)},
        "disk": disk_info,
        "tools": tools,
        "packages": packages,
        "gemini_key_set": bool(os.getenv("GEMINI_API_KEY")),
        "max_concurrent_jobs": os.getenv("MAX_CONCURRENT_JOBS", "1"),
        "warnings": warnings,
        "ok": not warnings,
    }