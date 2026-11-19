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
- [ ] 3.1 FFmpeg service (cut fast/copy + accurate/re-encode, frame grab, proxy MP4 for MOV/MKV/AVI)
- [ ] 3.2 Minimal job runner + SSE progress (needed early for long tasks)
- [ ] 3.3 Clips API (create, list, delete, stream, download)
- [ ] 3.4 Manual Clipper UI (timeline, start/end, preview, export)
- [ ] 3.5 Tests for FFmpeg service + clips API
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
- 2026-11-xx Phase 1 foundation scaffolded.
- Phase 1 COMPLETE: DB models, /api/dashboard, backend tests passing, Next.js build passing, sidebar + dashboard working.
- Added: Gemini client (gemini-3.1-flash-lite), scripts start-all/stop-all/check.
- Pending: add GEMINI_API_KEY in .env before Phase 4.
- Phase 2 COMPLETE: upload API with FFprobe validation, path-traversal protection, size limit, library list/search/stream/delete, drag-drop UI. 15 backend tests passing.
- Postponed: resumable uploads (browser sends one request per file; revisit if large files fail).
- Note: MOV/MKV/AVI preview depends on the browser; proxy previews now planned in Phase 3.1.
- 2026-11-19 README reviewed: structure auto-generated, Phase 3 split into steps, job runner moved earlier.
