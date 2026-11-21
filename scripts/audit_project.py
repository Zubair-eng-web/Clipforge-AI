"""CLIPFORGE AI audit: README vs disk vs running backend. Standard library only."""
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://localhost:8000"
rows = []


def add(kind, name, note=""):
    rows.append((kind, name, note))
    print("[%s] %s %s" % (kind, name, note))


FILES = [
    "backend/main.py", "backend/config.py",
    "backend/database/db.py", "backend/database/models.py", "backend/database/models_phase12.py",
    "backend/video_processing/ffmpeg_service.py", "backend/workers/runner.py",
    "backend/workers/handlers.py", "backend/workers/analysis_handlers.py",
    "backend/workers/caption_handlers.py", "backend/workers/scene_handlers.py",
    "backend/workers/audio_handlers.py", "backend/workers/gaming_handlers.py",
    "backend/workers/reel_handlers.py", "backend/workers/timeline_handlers.py",
    "backend/workers/compose_handlers.py", "backend/workers/batch_pipeline_handlers.py",
    "backend/scene_ai/categories.py", "backend/scene_ai/engine.py", "backend/scene_ai/extract.py",
    "backend/audio_studio/mix.py", "backend/audio_studio/waveform.py", "backend/audio_studio/suggest.py",
    "backend/gaming/categories.py", "backend/gaming/signals.py", "backend/gaming/scoring.py",
    "backend/gaming/pipeline.py", "backend/reels/presets.py", "backend/reels/engine.py",
    "backend/reels/cards.py", "backend/captions/presets.py", "backend/captions/builder.py",
    "backend/captions/burn.py", "backend/social/generator.py", "backend/editor/timeline.py",
    "backend/thumbs/suggest.py", "backend/services/performance.py",
    "backend/api/gemini_key.py",
    "backend/api/reels_media.py", "backend/api/studio_stats.py",
    "frontend/lib/nav.ts", "frontend/components/StudioStats.tsx",
    "scripts/setup.ps1", "scripts/start-backend.ps1", "scripts/start-frontend.ps1",
    "scripts/start-all.ps1", "scripts/stop-all.ps1", "scripts/check.ps1", "scripts/diagnose.ps1",
    "scripts/real_workflow_test.py", "scripts/benchmark.py", "scripts/test_one_click_chain.py",
    "README.md", "FINAL_REPORT.md", "TROUBLESHOOTING.md", ".env.example",
]
ROUTES = [
    "scene-detection", "gaming-highlights", "music", "audio-studio", "reels", "reels-library",
    "captions-studio", "social-text", "timeline-editor", "clips-gallery", "batch", "performance",
    "gemini-key", "about", "queue", "one-click-reel", "thumbnails",
]
GET_ENDPOINTS = [
    "/api/health", "/api/dashboard", "/api/studio/stats", "/api/about", "/api/reels",
    "/api/clips", "/api/jobs", "/api/settings", "/api/queue/summary", "/api/projects",
    "/api/collections", "/api/history", "/api/storage-manager/overview", "/api/analytics",
    "/api/diagnostics", "/api/analysis/status", "/api/scene-ai/categories",
    "/api/gaming/categories", "/api/music", "/api/music-collections",
    "/api/reels-studio/platforms", "/api/social/options", "/api/thumbnails",
    "/api/thumbnails/platforms", "/api/gemini-key/status", "/api/performance",
    "/api/batch/jobs", 
]

print("== 1. Files (README vs disk) ==")
for f in FILES:
    add("PASS" if (ROOT / f).exists() else "FAIL", "file " + f)

print("== 2. Frontend pages and sidebar ==")
nav = ROOT / "frontend/lib/nav.ts"
nav_text = nav.read_text(encoding="utf-8", errors="ignore") if nav.exists() else ""
for r in ROUTES:
    page = ROOT / "frontend/app" / r / "page.tsx"
    add("PASS" if page.exists() else "WARN", "page /" + r, "" if page.exists() else "(page.tsx not found)")
    add("PASS" if ("/" + r) in nav_text else "WARN", "nav /" + r)

print("== 3. Safety ==")
gi = ROOT / ".gitignore"
gi_text = gi.read_text(encoding="utf-8", errors="ignore") if gi.exists() else ""
add("PASS" if "storage" in gi_text else "FAIL", "storage is git-ignored")
add("PASS" if ".env" in gi_text else "FAIL", ".env is git-ignored")

print("== 4. Live API (backend must run on port 8000) ==")
down = False
details = {}
for ep in GET_ENDPOINTS:
    if down:
        add("SKIP", "GET " + ep, "backend not running")
        continue
    try:
        with urllib.request.urlopen(BASE + ep, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            add("PASS", "GET " + ep, str(resp.status))
            if ep in ("/api/diagnostics", "/api/publish/youtube/status", "/api/gemini-key/status"):
                try:
                    details[ep] = json.loads(body)
                except Exception:
                    details[ep] = body[:300]
    except urllib.error.HTTPError as e:
        add("WARN" if e.code in (404, 405, 422) else "FAIL", "GET " + ep, str(e.code))
    except urllib.error.URLError:
        down = True
        add("SKIP", "GET " + ep, "backend not running (start-backend.ps1)")
    except Exception as e:
        add("FAIL", "GET " + ep, str(e)[:80])

counts = {}
for k, _, _ in rows:
    counts[k] = counts.get(k, 0) + 1
print("\nSUMMARY:", counts)

lines = ["# AUDIT REPORT", "", "Run: " + datetime.now().strftime("%Y-%m-%d %H:%M"), "",
         "Summary: " + json.dumps(counts), "", "| Result | Check | Note |", "|---|---|---|"]
for k, n, note in rows:
    lines.append("| %s | %s | %s |" % (k, n, note))
lines += ["", "## Details", "", "```json", json.dumps(details, indent=2, default=str)[:6000], "```", ""]
(ROOT / "AUDIT_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
print("Report saved: AUDIT_REPORT.md")
sys.exit(1 if counts.get("FAIL") else 0)
