# CLIPFORGE AI
**Turn Long Videos Into Powerful Clips.**

Local-first AI video clipping and repurposing studio. Runs fully on a Windows PC (Core i5, 8GB RAM, CPU only). No cloud deployment.

## Tech Stack
| Layer | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS, Lucide Icons |
| Backend | Python 3.11, FastAPI, Pydantic |
| Video | FFmpeg, FFprobe, OpenCV, PySceneDetect, MoviePy |
| AI | faster-whisper (small, int8), Gemini API (text only), Pyannote (optional, later) |
| Import | yt-dlp (authorized sources only) |
| Database | SQLite (WAL mode) + SQLAlchemy |
| Queue | SQLite-backed job queue + Python workers |
| Progress | Server-Sent Events (SSE) |

## Sidebar Structure
**WORKSPACE:** Dashboard, Upload Videos, YouTube Import, AI Auto Clipper, Manual Clipper, Scene Detection, AI Highlights, Video Editor, Smart Captions, AI Reframing, Thumbnail Studio, Batch Processing

**LIBRARY:** My Projects, Video Library, Generated Clips, Collections, History, Storage Manager, AI Analytics, Settings

Pages not built yet show a "Coming in Phase X" placeholder.

## Project Structure
```text
CLIPFORGE_AI/
  backend/
    main.py              FastAPI app, /api/health, /api/dashboard
    config.py            storage paths, allowed file types
    api/                 videos.py, clips.py, jobs.py (SSE), previews.py
    database/            db.py (SQLite WAL), models.py (Video, Clip, Job, Setting)
    video_processing/    ffmpeg_service.py (cut/proxy/frame), ffprobe.py
    workers/             runner.py (job queue), handlers.py (clip_export, proxy)
    services/            paths.py (safe paths), cleanup.py (delete files)
    ai/                  gemini_client.py
    audio_processing/, scene_detection/, clip_generation/   (empty, Phase 4-5)
  frontend/              Next.js app (sidebar + pages)
  scripts/               setup, start-backend/frontend/all, stop-all, check
  storage/               original_videos, generated_clips, thumbnails, previews (git-ignored)
  tests/                 pytest tests (api, videos, clips, gemini, phase3 pipeline)
  logs/
```
## How To Run
1. `.\scripts\setup.ps1`            (one time, backend setup)
2. `.\scripts\start-backend.ps1`    (http://localhost:8000/api/health)
3. `.\scripts\start-frontend.ps1`   (http://localhost:3000)

Shortcuts: `.\scripts\start-all.ps1`, `.\scripts\stop-all.ps1`, `.\scripts\check.ps1`

## Environment (.env)
- `GEMINI_API_KEY` : required from Phase 4 (verify model name in Google AI Studio)
- Max concurrent jobs: configurable, default 1 (8GB RAM)

## Key Rules
- Original videos are never modified.
- Permanent content is never saved in temporary folders.
- Max concurrent jobs is configurable (default 1) for 8GB RAM.
- No fake analytics data. Only real measured data.
- Only process videos the user has permission to use.

---

## Phase 3 Notes (FFmpeg + Manual Clipper)
**What it does:** pick a video, mark start/end, export a clip as MP4. The original file is never changed.

**Backend**
| Piece | File |
|---|---|
| FFmpeg service (cut, proxy, frame grab) | `backend/video_processing/ffmpeg_service.py` |
| Job queue + worker threads (SQLite-backed) | `backend/workers/runner.py`, `backend/workers/handlers.py` |
| Clips API | `backend/api/clips.py` |
| Jobs API + SSE progress | `backend/api/jobs.py` |
| Browser preview proxy (MOV/MKV/AVI/HEVC) | `backend/api/previews.py` |

**Endpoints**
- `POST /api/clips` (video_id, start_sec, end_sec, title, mode=accurate|fast) returns clip + job_id
- `GET /api/clips?video_id=`, `GET /api/clips/{id}`, `/stream`, `/download`, `/thumbnail`, `DELETE /api/clips/{id}`
- `GET /api/jobs/{id}`, `GET /api/jobs/{id}/events` (SSE), `POST /api/jobs/{id}/cancel`
- `POST /api/videos/{id}/proxy` (start preview conversion), `GET /api/videos/{id}/proxy` (preview file)

**Modes:** `accurate` re-encodes (frame exact). `fast` copies streams (instant, may start at the previous keyframe; falls back to accurate if the codec cannot go into MP4).

**Files:** clips in `storage/generated_clips/`, thumbnails in `storage/thumbnails/`, previews in `storage/previews/` (regenerable cache). Deleting a video also deletes its clips and preview.

**Config:** `MAX_CONCURRENT_JOBS` in `.env` (default 1).

**DB:** new columns `videos.proxy_path`, `clips.thumbnail_path`, `jobs.payload` are added automatically at startup.

**Tests:** `.\.venv\Scripts\python.exe -m pytest -q`

**Manual test checklist**
1. Library -> scissors icon -> Manual Clipper opens with that video.
2. Set start/end (or press I / O while playing), Preview selection, Export.
3. Progress bar moves, clip plays, Download works, file appears in Generated Clips.
4. Upload an MOV/MKV/AVI: preview should auto-convert ("Preparing a browser preview").
5. Delete a clip and a video: files disappear from `storage/`.
## Phase 3.5 Notes (Tests)
- `tests/test_phase3_pipeline.py`: FFmpeg service tests (accurate/fast cut, proxy, frame grab, original untouched) and clip export end-to-end tests (upload, export, stream/download/thumbnail, SSE, delete, video delete cleanup). Uses tiny videos generated by FFmpeg.
- `tests/test_gemini.py::test_live_gemini_call` is skipped automatically when Gemini is not reachable (offline, 403 billing/free-tier, 429 quota, 503 high demand).
- Run all: `.\.venv\Scripts\python.exe -m pytest -q`
## Progress Tracker

### Phase 1: Foundation
- [x] Project folder structure created
- [x] README created
- [x] .env.example and .gitignore
- [x] Backend skeleton (FastAPI + health endpoint)
- [x] Setup and start scripts
- [x] Frontend (Next.js + Tailwind) created
- [x] Sidebar layout (dark theme, collapsible)
- [x] Dashboard page (cards + placeholders)
- [x] SQLite database + models (videos, clips, jobs, settings)

### Phase 2: Upload and Storage
- [x] Upload API (drag-drop, multi-file, validation)
- [x] FFprobe metadata (duration, resolution)
- [x] Video preview
- [x] Permanent storage handling

### Phase 3: FFmpeg and Manual Clipper
- [x] 3.1 FFmpeg service (cut fast/copy + accurate/re-encode, frame grab, proxy MP4 for MOV/MKV/AVI)
- [x] 3.2 Minimal job runner + SSE progress (needed early for long tasks)
- [x] 3.3 Clips API (create, list, delete, stream, download)
- [x] 3.4 Manual Clipper UI (timeline, start/end, preview, export)
- [x] 3.5 Tests for FFmpeg service + clips API
- [ ] Test: manual clip export works end to end

### Phase 4: AI Analysis
- [ ] faster-whisper transcription
- [ ] PySceneDetect scenes
- [ ] Gemini highlight scoring
- [ ] Test: transcript + scenes + scores on a sample video

### Phase 5: Auto Multi-Clip Generation (1-20 min source videos)
- [ ] Clip selection logic (no overlap)
- [ ] Clip generation + metadata
- [ ] Test

### Phase 6: Editor, Captions, Reframing
- [ ] Video editor
- [ ] Smart captions + SRT
- [ ] AI reframing (9:16, 1:1, 16:9)
- [ ] Test

### Phase 7: Thumbnails and Batch
- [ ] Thumbnail Studio
- [ ] Batch processing
- [ ] Test

### Phase 7b: YouTube Import and Settings
- [ ] YouTube Import page (yt-dlp, authorized sources only)
- [ ] Settings page (concurrent jobs, API key status, storage paths)
- [ ] Test
### Phase 8: Queue, Library, Analytics
- [ ] Full queue manager (extends 3.2)
- [ ] Library, collections, history
- [ ] Storage manager + AI analytics
- [ ] Test

### Phase 9: Testing and Docs
- [ ] Full test pass
- [ ] Performance optimization
- [ ] Troubleshooting docs

---
## Changelog
- Phase 1 foundation scaffolded.
- Phase 1 COMPLETE: DB models, /api/dashboard, backend tests passing, Next.js build passing, sidebar + dashboard working.
- Added: Gemini client (gemini-3.1-flash-lite), scripts start-all/stop-all/check.
- Pending: add GEMINI_API_KEY in .env before Phase 4.
- Phase 2 COMPLETE: upload API with FFprobe validation, path-traversal protection, size limit, library list/search/stream/delete, drag-drop UI. 15 backend tests passing.
- Postponed: resumable uploads (browser sends one request per file; revisit if large files fail).
- Note: MOV/MKV/AVI preview depends on the browser; proxy previews now planned in Phase 3.1.
- 2026-11-19 README reviewed: structure auto-generated, Phase 3 split into steps, job runner moved earlier.
- 2026-11-19 Phase 3 code added: FFmpeg service, job runner + SSE, clips API, preview proxy, Manual Clipper + Generated Clips pages. Waiting for tests (3.5) and manual end-to-end test.
- 2026-11-19 Step 3.5 DONE: FFmpeg service + clip export end-to-end tests added (tests/test_phase3_pipeline.py), 44 tests passing. Live Gemini test skips on offline/403/429/503. Gemini key reaches the API (a 503 high-demand error was seen once); Phase 4 will add retry + local fallback scoring. Added Phase 7b (YouTube Import, Settings) to the tracker. Next: manual end-to-end test in the browser, then Phase 4.
