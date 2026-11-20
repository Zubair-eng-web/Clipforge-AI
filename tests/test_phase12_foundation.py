import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCRIPT = r"""
import json
from fastapi.testclient import TestClient
from backend.main import app
with TestClient(app) as c:
    out = {
        "health": c.get("/api/health").status_code,
        "dashboard": c.get("/api/dashboard").status_code,
        "stats": c.get("/api/studio/stats").json(),
        "about": c.get("/api/about").json(),
        "reels": c.get("/api/reels").json(),
        "reel404": c.get("/api/reels/999").status_code,
        "del404": c.delete("/api/reels/999").status_code,
    }
print("RESULT=" + json.dumps(out))
"""


def test_phase12_foundation(tmp_path):
    storage = tmp_path / "storage"
    env = dict(os.environ)
    env["CLIPFORGE_STORAGE_DIR"] = str(storage)
    env["CLIPFORGE_DB_PATH"] = str(storage / "t.db")
    env["PYTHONPATH"] = str(ROOT)
    r = subprocess.run([sys.executable, "-c", SCRIPT], cwd=str(ROOT), env=env,
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-2000:]
    line = [ln for ln in r.stdout.splitlines() if ln.startswith("RESULT=")][-1]
    out = json.loads(line[len("RESULT="):])
    assert out["health"] == 200 and out["dashboard"] == 200
    assert out["reels"] == []
    assert out["reel404"] == 404 and out["del404"] == 404
    assert out["about"]["name"] == "CLIPFORGE AI"
    s = out["stats"]
    for key in ("videos", "clips", "reels", "captions", "music_tracks", "processing_jobs",
                "storage_bytes", "recent_projects", "recent_exports"):
        assert key in s
    assert s["reels"] == 0 and s["videos"] == 0
    for d in ("reels", "music", "captions", "subtitles", "projects", "collections", "exports"):
        assert (storage / d).is_dir(), d