from pathlib import Path

from backend import config


def resolve_storage(rel: str) -> Path:
    """Convert a relative path stored in the DB into an absolute path inside storage/.
    Raises ValueError if the path tries to escape the storage folder."""
    base = config.STORAGE_DIR.resolve()
    p = (base / rel).resolve()
    if base not in p.parents:
        raise ValueError("Invalid stored path")
    return p
