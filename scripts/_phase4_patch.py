import re
import sys
from pathlib import Path

root = Path.cwd()

MODEL = '''class VideoAnalysis(Base):
    """Result of the AI analysis of one video (transcript, scenes, highlights as JSON text)."""
    __tablename__ = "video_analysis"
    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="none")
    language: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    transcript_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scenes_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    highlights_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scoring_source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
'''

NOTES = '''## Phase 4 Notes (AI Analysis)
**What it does:** one "analyze" job per video: transcript (faster-whisper) -> scenes (PySceneDetect) -> highlight candidates -> scores (Gemini, text only; local fallback). The original video is never changed.

**Flow and files**
| Step | File |
|---|---|
| Transcription (small, int8, CPU; model loaded per job and released) | `backend/audio_processing/transcribe.py` |
| Scene detection (ContentDetector) | `backend/scene_detection/detect.py` |
| Candidates (20-60 s, sentence aligned, max 50% overlap) + scoring + retry + fallback | `backend/ai/highlights.py` |
| Pipeline (stages and progress) | `backend/ai/pipeline.py` |
| Job handler `analyze` | `backend/workers/ai_handlers.py` |
| API | `backend/api/analysis.py` |
| DB table `video_analysis` (created automatically) | `backend/database/models.py` |
| UI | `frontend/.../ai-highlights/page.tsx` |

**Endpoints**
- `POST /api/videos/{id}/analyze` (optional body: language e.g. "en"/"hi"/null=auto, use_gemini) returns job_id. Progress via `GET /api/jobs/{job_id}/events` (SSE).
- `GET /api/videos/{id}/analysis` returns status, transcript, scenes, highlights (sorted by score), scoring_source, note.

**Scoring:** final = 0.7 * Gemini + 0.3 * local heuristic. If Gemini fails (429/503 are retried 3 times with backoff; 403/404/no key are not) the local score is used and `note` says why. Only transcript text is sent to Gemini, never video.

**Config (.env):** `WHISPER_MODEL=small` (default), `GEMINI_MODEL` (verify the name in Google AI Studio), `GEMINI_API_KEY`.

**First run:** faster-whisper downloads the Whisper model once (about 500 MB, internet needed). CPU only, so long videos take time.

**Tests:** `.\\.venv\\Scripts\\python.exe -m pytest -q` (the Whisper test is optional: `$env:RUN_WHISPER_TEST=1`).

**Manual test checklist**
1. Upload a short video (1-2 min) with clear speech.
2. AI Highlights -> select the video -> Analyze. Progress bar moves.
3. Highlights appear with title, score, time range; transcript can be opened.
4. Export clip on one highlight -> clip appears in Generated Clips.
5. Turn off the internet or remove the Gemini key: analysis still finishes with source "local".
'''


def rd(rel):
    p = root / rel
    return p, (p.read_text(encoding="utf-8") if p.exists() else None)


def patch_once(rel, guard, old, new):
    p, t = rd(rel)
    if t is None:
        print(f"  WARNING: {rel} not found")
        return
    if guard in t:
        print(f"  {rel}: already patched")
        return
    if old not in t:
        print(f"  WARNING: anchor not found in {rel} (send me this file)")
        return
    p.write_text(t.replace(old, new, 1), encoding="utf-8")
    print(f"  patched {rel}")


def apply():
    p, t = rd("backend/database/models.py")
    if t is not None and "class VideoAnalysis" not in t:
        p.write_text(t.rstrip() + "\n\n\n" + MODEL, encoding="utf-8")
        print("  patched backend/database/models.py")
    else:
        print("  models.py: already patched or missing")

    patch_once("backend/workers/runner.py", "ai_handlers",
               "from backend.workers import handlers",
               "from backend.workers import ai_handlers, handlers  # noqa: F401")
    patch_once("backend/main.py", "analysis_router",
               "from backend.api.clips import router as clips_router",
               "from backend.api.analysis import router as analysis_router\nfrom backend.api.clips import router as clips_router")
    p, t = rd("backend/main.py")
    if t is not None and "include_router(analysis_router)" not in t:
        t = t.replace("app.include_router(jobs_router)", "app.include_router(jobs_router)\napp.include_router(analysis_router)", 1)
        t = t.replace('version="0.3.0"', 'version="0.4.0"', 1)
        p.write_text(t, encoding="utf-8")
        print("  patched main.py (router + version)")

    p, t = rd("requirements.txt")
    if t is not None:
        lines = t.splitlines()
        for pkg in ("faster-whisper", "scenedetect[opencv-headless]"):
            if not any(l.strip().lower().startswith(pkg.split("[")[0]) for l in lines):
                lines.append(pkg)
                print(f"  requirements.txt: added {pkg}")
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    p, t = rd(".env.example")
    if t is not None and "WHISPER_MODEL" not in t:
        p.write_text(t.rstrip() + "\nWHISPER_MODEL=small\n", encoding="utf-8")
        print("  .env.example: added WHISPER_MODEL")


def readme(passed):
    p, t = rd("README.md")
    if t is None:
        print("  README.md not found, skipped")
        return
    m = "x" if passed else " "
    block = (
        "### Phase 4: AI Analysis\n"
        f"- [{m}] 4.1 faster-whisper transcription (`backend/audio_processing/transcribe.py`)\n"
        f"- [{m}] 4.2 PySceneDetect scenes (`backend/scene_detection/detect.py`)\n"
        f"- [{m}] 4.3 Highlight candidates + Gemini scoring with retry and local fallback (`backend/ai/highlights.py`)\n"
        f"- [{m}] 4.4 Analyze job + API + AI Highlights page\n"
        f"- [{m}] 4.5 Unit tests (`tests/test_phase4_analysis.py`)\n"
        "- [ ] Test: transcript + scenes + scores on a real sample video (manual)\n\n"
    )
    if "### Phase 4: AI Analysis" in t:
        t = re.sub(r"### Phase 4: AI Analysis.*?(?=### Phase 5)", lambda _: block, t, count=1, flags=re.S)
    if "## Phase 4 Notes" not in t and "## Progress Tracker" in t:
        t = t.replace("## Progress Tracker", NOTES + "\n## Progress Tracker", 1)
    t = t.replace("audio_processing/, scene_detection/, clip_generation/   (empty, Phase 4-5)",
                  "audio_processing/transcribe.py, scene_detection/detect.py, clip_generation/ (empty, Phase 5)")
    t = t.replace("ai/                  gemini_client.py", "ai/                  gemini_client.py, highlights.py, pipeline.py", 1) if "highlights.py, pipeline.py" not in t else t
    if "Phase 4 code added" not in t:
        status = "unit tests passing" if passed else "tests need a check"
        t = t.rstrip() + f"\n- 2026-11-19 Phase 4 code added: transcript, scenes, Gemini scoring with retry + local fallback, analyze job, API, AI Highlights page ({status}). Next: manual test on a real video, then Phase 5.\n"
    p.write_text(t, encoding="utf-8")
    print("  README.md updated")


if __name__ == "__main__":
    if sys.argv[1] == "apply":
        apply()
    else:
        readme(sys.argv[2] == "pass")