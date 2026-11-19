# CLIPFORGE AI
**Turn Long Videos Into Powerful Clips.**

Local-first AI video clipping and repurposing studio. Runs fully on a Windows PC (Core i5, 8GB RAM, CPU only). No cloud deployment.

## Tech Stack
| Layer | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS, Lucide Icons |
| Backend | Python 3.11, FastAPI, Pydantic |
| Video | FFmpeg, FFprobe, OpenCV (4.x), PySceneDetect, MoviePy |
| AI | faster-whisper (small, int8), Gemini API (text only), Pyannote (optional, later) |
| Import | yt-dlp (authorized sources only) |
| Database | SQLite (WAL mode) + SQLAlchemy |
| Queue | SQLite-backed job queue + Python workers |
| Progress | Server-Sent Events (SSE) |

## Sidebar Structure
**WORKSPACE:** Dashboard, Upload Videos, YouTube Import, AI Auto Clipper, Manual Clipper, Scene Detection, AI Highlights, Video Editor, Smart Captions, AI Reframing, Thumbnail Studio, Batch Processing

**LIBRARY:** My Projects, Video Library, Generated Clips, Collections, History (with queue manager), Storage Manager, AI Analytics, Settings

## Project Structure
```text
CLIPFORGE_AI/
  backend/
    main.py              FastAPI app, /api/health, /api/dashboard, router registration
    config.py            storage paths, allowed file types
    api/                 videos, clips, jobs (SSE), previews, analysis, autoclips, captions,
                         reframe, editor, thumbnails, youtube, batch, settings,
                         queue, library (projects/collections/history),
                         storage_manager, analytics, diagnostics
    database/            db.py (SQLite WAL), models.py
    video_processing/    ffmpeg_service.py, ffprobe.py, frames.py
    workers/             runner.py (job queue), handlers.py, analysis_handlers.py,
                         caption_handlers.py, reframe_handlers.py, editor_handlers.py,
                         youtube_handlers.py, batch_handlers.py
    audio_processing/    transcribe.py, word_transcribe.py
    scene_detection/     detector.py
    ai/                  gemini_client.py, highlights.py
    clip_generation/     selector.py
    captions/            builder.py, burn.py
    reframing/           reframe.py
    editor/              ops.py
    importers/           youtube.py
    services/            paths.py, cleanup.py
  frontend/              Next.js app (sidebar + pages, lib/nav.ts, lib/api8.ts)
  scripts/               setup, start-backend/frontend/all, stop-all, check, diagnose
  storage/               original_videos, generated_clips, edited_clips, thumbnails,
                         previews, temporary (git-ignored)
  tests/                 pytest tests per phase
  _unused/               old Phase 4 files and page backups (safe to delete)
  logs/
```

## How To Run
1. `.\scripts\setup.ps1`            (one time, backend setup)
2. `.\scripts\start-backend.ps1`    (http://localhost:8000/api/health)
3. `.\scripts\start-frontend.ps1`   (http://localhost:3000)

Shortcuts: `.\scripts\start-all.ps1`, `.\scripts\stop-all.ps1`, `.\scripts\check.ps1`, `.\scripts\diagnose.ps1`
Tests: `.\.venv\Scripts\python.exe -m pytest -q`
Problems: see `TROUBLESHOOTING.md`.

## Environment (.env)
- `GEMINI_API_KEY`: used from Phase 4 (verify the model name in Google AI Studio). Without it, local scoring is used.
- `MAX_CONCURRENT_JOBS`: default 1 (8GB RAM), max 4.
- Optional: `WHISPER_MODEL`, `WHISPER_LANGUAGE`, `WHISPER_BEAM_SIZE`, `WHISPER_VAD`, `SCENE_THRESHOLD`, `HIGHLIGHT_MAX_CANDIDATES`, `HIGHLIGHT_GEMINI_MAX`, `YOUTUBE_MAX_MINUTES` (default 60), `MAX_UPLOAD_GB` (default 5).

## Key Rules
- Original videos are never modified.
- Edited, captioned and reframed results are always NEW clips.
- Permanent content is never saved in temporary folders.
- Max concurrent jobs is configurable (default 1) for 8GB RAM.
- No fake analytics data. Only real measured data.
- Only process videos the user has permission to use.

---

## Feature Notes

### Phase 3: Manual Clipper (FFmpeg + job queue)
Pick a video, mark start/end (I / O keys), export an MP4 clip. Modes: `accurate` (re-encode, frame exact) and `fast` (stream copy, may start at the previous keyframe, falls back to accurate).
- `POST /api/clips` (video_id, start_sec, end_sec, title, mode) returns clip + job_id
- `GET /api/clips`, `GET /api/clips/{id}`, `/stream`, `/download`, `/thumbnail`, `DELETE /api/clips/{id}`
- `GET /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs/{id}/events` (SSE), `POST /api/jobs/{id}/cancel`
- `POST|GET /api/videos/{id}/proxy` (browser preview for MOV/MKV/AVI/HEVC)
- Files: `ffmpeg_service.py`, `workers/runner.py`, `workers/handlers.py`, `api/clips.py`, `api/jobs.py`, `api/previews.py`
- Tests: `tests/test_phase3_pipeline.py`

### Phase 4: AI Analysis
One `analyze` job per video: transcript (faster-whisper small int8) -> scenes (PySceneDetect) -> highlight candidates (15-60 s, max 50% overlap) -> scores (local heuristic, re-scored by Gemini with text only; retry on 429/503, local fallback on 403 or no key).
- `POST /api/videos/{id}/analyze`, `GET /api/videos/{id}/analysis`
- `GET /api/analysis/status`, `POST /api/analysis/videos/{id}/run` (steps, use_gemini, force), `GET /api/analysis/videos/{id}`, `/transcript`, `/scenes`, `/highlights`, `DELETE /api/analysis/videos/{id}`
- "Analyze again" reuses the saved transcript. `force: true` or a language choice redoes it.
- Files: `transcribe.py`, `scene_detection/detector.py`, `ai/highlights.py`, `workers/analysis_handlers.py`, `api/analysis.py`
- Tables: `transcripts`, `scenes`, `highlights`, `video_analysis`
- Tests: `test_phase4_analysis.py`, `test_phase4_compat.py`, `test_phase4_scenes_only.py`

### Phase 5: AI Auto Clipper
`POST /api/videos/{id}/auto-clips` (count 1-20, min_score, mode, pad_before, pad_after). Needs a finished analysis. Picks best highlights by score, never overlapping, clamps to video length, skips clips overlapping existing ones.
- Files: `clip_generation/selector.py`, `api/autoclips.py`. Tests: `test_phase5_autoclips.py`

### Phase 6.1: Smart Captions
Word-level captions from a clip, edit text, download SRT, burn into the video (styles classic, bold, highlight; position bottom, center, top). Result is a NEW clip in `storage/edited_clips/`.
- `POST /api/clips/{id}/captions/generate`, `GET|PUT /api/clips/{id}/captions`, `GET /api/clips/{id}/captions.srt`, `POST /api/clips/{id}/captions/burn`
- An edited line loses its word timing. Burn-in needs FFmpeg with libass.
- Files: `captions/builder.py`, `captions/burn.py`, `audio_processing/word_transcribe.py`, `api/captions.py`. Table: `clip_captions`. Tests: `test_phase6_captions.py`

### Phase 6.2: AI Reframing
Ratios 9:16, 1:1, 16:9. Modes: `face` (fixed crop around median face position, center fallback), `center`, `blur`. Output 720x1280, 720x720, 1280x720. Result is a NEW clip.
- `POST /api/clips/{id}/reframe`. Files: `reframing/reframe.py`, `api/reframe.py`. Limit: no moving camera yet.

### Phase 6.3: Video Editor
Edit one clip (trim, speed 0.5-2x, volume/mute, fades, brightness/contrast/saturation, flip) or merge 2-10 clips. Results are NEW clips. Clips without audio get silence when merged.
- `POST /api/clips/{id}/edit`, `POST /api/editor/merge`. Files: `editor/ops.py`, `api/editor.py`.

### Phase 7: Thumbnails, Batch, YouTube, Settings
- Thumbnail Studio: pick a frame, add text (drawn in the browser canvas), save or download. `GET /api/clips/{id}/frame?t=`, `GET|POST /api/thumbnails`, `DELETE /api/thumbnails/{id}`.
- Batch: `POST /api/batch/start` (video_ids, count, mode, min_score, use_gemini), `GET /api/batch/jobs`. One `batch_video` job per video.
- YouTube Import: `POST /api/youtube/info`, `POST /api/youtube/import` (confirm_rights must be true). One video per link, max 1080p.
- Settings: `GET /api/settings` read-only status. The Gemini key is never returned.
- Tests: `test_phase7_youtube_thumbnails.py`, `test_phase6_editor_batch.py`, `test_phase6_reframe_settings.py`

### Phase 8: Queue, Library, Storage, Analytics
- Queue: `GET /api/queue/summary`, `POST /api/queue/{id}/retry`, `POST /api/queue/cancel-queued`, `POST /api/queue/clear-finished` (UI inside History).
- Projects: `GET|POST /api/projects`, `GET|PATCH|DELETE /api/projects/{id}` (deleting keeps videos and clips).
- Collections: `GET|POST /api/collections`, `GET|DELETE /api/collections/{id}`, `POST /api/collections/{id}/clips`, `DELETE /api/collections/{id}/clips/{clip_id}`.
- History: `GET /api/history?limit=&kind=`.
- Storage Manager: `GET /api/storage-manager/overview`, `POST /api/storage-manager/cleanup` (previews | temporary | orphans | failed_clips). Only deletes inside `storage/`. Originals and ready clips are never touched.
- Analytics: `GET /api/analytics` (only real measured data).
- Tests: `tests/test_phase8.py`

### Phase 9: Diagnostics
`GET /api/diagnostics` and `.\scripts\diagnose.ps1` check FFmpeg, FFprobe, RAM, disk, Gemini key and key Python packages. Tests: `tests/test_phase9_diagnostics.py`

---

## Progress Tracker

### Phase 1: Foundation
- [x] Folder structure, README, .env.example, .gitignore
- [x] Backend skeleton, setup and start scripts
- [x] Frontend, sidebar, dashboard
- [x] SQLite database + models

### Phase 2: Upload and Storage
- [x] Upload API, FFprobe metadata, video preview, permanent storage

### Phase 3: FFmpeg and Manual Clipper
- [x] FFmpeg service, job runner + SSE, clips API, Manual Clipper UI, tests
- [x] Manual end-to-end test

### Phase 4: AI Analysis
- [x] Transcription, scenes, highlights + Gemini scoring, analyze job, pages, tests
- [x] Real video test

### Phase 5: Auto Multi-Clip Generation
- [x] Selector, auto-clips API, AI Auto Clipper page
- [x] Real video test

### Phase 6: Editor, Captions, Reframing
- [x] Video editor, smart captions + SRT, AI reframing
- [x] Test

### Phase 7: Thumbnails, Batch, YouTube, Settings
- [x] Thumbnail Studio, batch processing, YouTube import, settings page
- [x] Test

### Phase 8: Queue, Library, Analytics
- [x] Queue manager, projects, collections, history
- [x] Storage manager, AI analytics
- [x] Test (109 passed, 2 skipped)

### Phase 9: Testing and Docs
- [x] Full test pass
- [x] Diagnostics endpoint and script
- [x] Troubleshooting docs
- [ ] Performance tuning from real timings (Whisper speed, RAM during analysis)

### Phase 10: Advanced Scene Detection (category-based clips)
- [ ] 10.0 Inspect existing code (detector, Gemini client, highlights, clip export, Scene Detection page)
- [ ] 10.1 Detection engine
  - [ ] Frame sampling (3-4 small frames per scene, FFmpeg, low RAM)
  - [ ] Reuse saved transcript and existing PySceneDetect scenes
  - [ ] Batched Gemini vision classification (6-8 scenes per call, JSON output, retry on 429/503)
  - [ ] 20 categories + custom category (free text)
  - [ ] Category-specific rules (fighting vs angry talk, romantic vs friendship/family)
  - [ ] Confidence score + "uncertain" marking, local keyword fallback when Gemini is unavailable
  - [ ] Merge consecutive related scenes, avoid duplicates
  - [ ] Duration logic: Complete Scene (Automatic), fixed 30s-20min, custom (no padding with unrelated footage)
  - [ ] Unit tests
- [ ] 10.2 Extraction and storage
  - [ ] Category folders (storage/generated_clips/fighting, romantic, comedy, ...)
  - [ ] Descriptive filenames (fighting_scene_001.mp4)
  - [ ] Reuse clip_export job, verify start/end after export, original never modified
  - [ ] Duplicate clip guard, manual boundary adjustment API
  - [ ] Optional subtitles and thumbnails, ZIP export of all categories
  - [ ] Cancel, retry, temporary file cleanup
- [ ] 10.3 Scene Detection page
  - [ ] "Select Which Scenes You Want to Extract" (checkboxes + icons)
  - [ ] Per-category duration dropdown
  - [ ] Extra options (min/max duration, confidence threshold, merge, preserve audio, etc.)
  - [ ] Result cards + timeline, preview, Extract Clip, select all, extract selected
- [ ] 10.4 Real video test (fighting, romantic, comedy, multiple categories, fixed 1/3 min, custom, complete scene, duplicates, failed AI)
- [ ] 10.5 README notes + final limitations report
- [ ] Pending from Phase 9: performance timing test (Whisper base, analyze time, peak RAM)
---

## Changelog
- 2026-11-20: Phase 10 planned (advanced scene detection, category-based clips). Tasks added to tracker.
- Phase 1: foundation, DB models, dashboard, sidebar, Gemini client, scripts.
- Phase 2: upload API with FFprobe validation, path-traversal protection, size limit, library, drag-drop UI. Resumable uploads postponed.
- Phase 3: FFmpeg service, job runner + SSE, clips API, preview proxy, Manual Clipper, tests.
- Phase 4: transcript, scenes, Gemini scoring with retry + local fallback, analyze job, AI Highlights page, Scene Detection page. Unified into one implementation (old files moved to `_unused/`).
- Phase 5: clip selector, auto-clips API, AI Auto Clipper page.
- Phase 6: Smart Captions, AI Reframing (OpenCV pinned to 4.x), Video Editor.
- Phase 7: Thumbnail Studio, Batch Processing, YouTube Import, Settings.
- Phase 8: queue manager, projects, collections, history, storage manager, analytics.
- Phase 9: diagnostics, README cleanup, TROUBLESHOOTING.md.
- 2026-11-20: all features built; 109 tests passing; manual checks done.

## Working Method
Small steps. Each step: code applied with a PowerShell script, tested, logged here. Every finished step gets a Changelog line and a tick in the Progress Tracker.