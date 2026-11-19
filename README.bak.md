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

## Project Structure

## How To Run
1. `.\scripts\setup.ps1`            (one time, backend setup)
2. `.\scripts\start-backend.ps1`    (http://localhost:8000/api/health)
3. `.\scripts\start-frontend.ps1`   (http://localhost:3000)

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
- [ ] FFmpeg service
- [ ] Manual clipper UI + export

### Phase 4: AI Analysis
- [ ] faster-whisper transcription
- [ ] PySceneDetect scenes
- [ ] Gemini highlight scoring

### Phase 5: Auto Multi-Clip Generation (1-20 min)
- [ ] Clip selection logic (no overlap)
- [ ] Clip generation + metadata

### Phase 6: Editor, Captions, Reframing
- [ ] Video editor
- [ ] Smart captions + SRT
- [ ] AI reframing (9:16, 1:1, 16:9)

### Phase 7: Thumbnails and Batch
- [ ] Thumbnail Studio
- [ ] Batch processing

### Phase 8: Queue, Library, Analytics
- [ ] Processing queue manager
- [ ] Library, collections, history
- [ ] Storage manager + AI analytics

### Phase 9: Testing and Docs
- [ ] Tests
- [ ] Performance optimization
- [ ] Troubleshooting docs

---
## Changelog
- Phase 1 foundation scaffolded.
- Phase 1 COMPLETE: DB models, /api/dashboard, backend tests passing, Next.js build passing, sidebar + dashboard working.
- Added: Gemini client (gemini-3.1-flash-lite), scripts start-all/stop-all/check.
- Pending: add GEMINI_API_KEY in .env before Phase 4.
- Phase 2 COMPLETE: upload API with FFprobe validation, path-traversal protection, size limit, library list/search/stream/delete, drag-drop UI. 15 backend tests passing.
- Postponed: resumable uploads (browser sends one request per file; will revisit if large files fail).
- Note: MOV/MKV/AVI preview depends on the browser; proxy previews planned in Phase 3.
