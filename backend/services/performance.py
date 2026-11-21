"""Performance settings (Phase 12.11): low-memory mode, analysis frame size, safe cleanup of stale temp files.
Settings are saved in storage/settings/performance.json and applied to os.environ (read at call time by
Whisper and the scene/gaming analysis). Turning a setting off restores the value from .env."""
import json
import logging
import os
import time

from backend import config

log = logging.getLogger("clipforge.performance")

LOW_ENV = {
    "WHISPER_MODEL": "base",
    "WHISPER_BEAM_SIZE": "1",
    "SCENE_AI_BATCH": "4",
    "SCENE_AI_MAX_UNITS": "80",
    "FRAME_WIDTH": "256",
}
MANAGED = list(LOW_ENV)
WIDTHS = (256, 320, 384, 512)
DEFAULTS = {"low_memory": False, "frame_width": 384}
_orig: dict = {}


def _file():
    return config.STORAGE_DIR / "settings" / "performance.json"


def load() -> dict:
    s = dict(DEFAULTS)
    try:
        d = json.loads(_file().read_text(encoding="utf-8"))
        s["low_memory"] = bool(d.get("low_memory", False))
        w = int(d.get("frame_width", 384))
        if w in WIDTHS:
            s["frame_width"] = w
    except (OSError, ValueError, TypeError):
        pass
    return s


def save(s: dict) -> None:
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"low_memory": bool(s["low_memory"]), "frame_width": int(s["frame_width"])}),
                 encoding="utf-8")


def apply(s: dict) -> None:
    for k in MANAGED:
        if k not in _orig:
            _orig[k] = os.environ.get(k)
        o = _orig[k]
        if o is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = o
    if s.get("low_memory"):
        os.environ.update(LOW_ENV)
    elif int(s.get("frame_width", 384)) != 384:
        os.environ["FRAME_WIDTH"] = str(int(s["frame_width"]))


def effective() -> dict:
    return {k: os.environ.get(k) for k in MANAGED}


def _stale_files(max_age_hours: float):
    base = config.STORAGE_DIR / "temporary"
    if not base.is_dir():
        return
    limit = time.time() - max_age_hours * 3600
    for f in base.rglob("*"):
        try:
            if f.is_file() and not f.is_symlink() and f.stat().st_mtime < limit:
                yield f
        except OSError:
            continue


def stale_temporary_bytes(max_age_hours: float = 6.0) -> int:
    total = 0
    for f in _stale_files(max_age_hours):
        try:
            total += f.stat().st_size
        except OSError:
            pass
    return total


def clean_stale_temporary(max_age_hours: float = 6.0) -> dict:
    """Deletes only OLD files inside storage/temporary (default older than 6 h) and empty sub folders.
    Files of a job that is running right now are new, so they are never touched."""
    freed = count = 0
    for f in list(_stale_files(max_age_hours)):
        try:
            size = f.stat().st_size
            f.unlink()
            freed += size
            count += 1
        except OSError:
            continue
    base = config.STORAGE_DIR / "temporary"
    if base.is_dir():
        for d in sorted((x for x in base.rglob("*") if x.is_dir()), key=lambda x: len(x.parts), reverse=True):
            try:
                d.rmdir()  # only works when empty
            except OSError:
                pass
    return {"files": count, "freed_bytes": freed}


def _peaks_dir():
    return config.STORAGE_DIR / "music" / "peaks"


def peaks_bytes() -> int:
    d = _peaks_dir()
    total = 0
    if d.is_dir():
        for f in d.glob("*.json"):
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


def clean_peaks() -> dict:
    """Waveform cache only (it is rebuilt when a track is opened). Music files are never touched."""
    freed = count = 0
    d = _peaks_dir()
    if d.is_dir():
        for f in list(d.glob("*.json")):
            try:
                size = f.stat().st_size
                f.unlink()
                freed += size
                count += 1
            except OSError:
                continue
    return {"files": count, "freed_bytes": freed}


def startup_housekeeping() -> None:
    """Called once at server start. Never raises."""
    try:
        apply(load())
    except Exception:
        log.exception("could not apply performance settings")
    try:
        clean_stale_temporary(24.0)
    except Exception:
        log.exception("stale temporary cleanup failed")