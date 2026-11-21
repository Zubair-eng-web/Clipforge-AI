## Overview (for reviewers)
CLIPFORGE AI is a local-first AI video clipping and repurposing studio that runs fully on a Windows PC (Core i5, 8 GB RAM, CPU only). It turns long videos into short clips and reels: transcription (faster-whisper), scene detection (PySceneDetect), highlight scoring (Gemini API with local fallback), captions, reframing, music mixing, thumbnails and batch processing.

- **Stack:** Python 3.11, FastAPI, SQLAlchemy + SQLite (WAL), FFmpeg/OpenCV, Next.js + React + TypeScript + Tailwind.
- **Design:** SQLite-backed job queue with workers and SSE progress, RAM-aware (configurable concurrency, low-memory mode), originals never modified.
- **Quality:** 215 automated tests (pytest), live API audit script, real-video tests.
- **Legal:** Use only videos and music you have the rights to. No media files are included in this repository. A Gemini API key is needed for AI scoring (set in .env, never committed).

---
# CLIPFORGE AI
**Turn Long Videos Into Powerful Clips.**

Local-first AI video clipping and repurposing studio. Runs fully on a Windows PC (Core i5, 8GB RAM, CPU only). No cloud deployment.

## Tech Stack
| Layer | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS, Lucide Icons |
| Backend | Python 3.11, FastAPI, Pydantic |
| Video | FFmpeg, FFprobe, OpenCV (4.x), PySceneDetect, MoviePy |
| AI | faster-whisper (small, int8), Gemini API (text; small still frames only for Scene Detection / Gaming when 'Look at video frames' is on), Pyannote (optional, later) |
| Import | yt-dlp (authorized sources only) |
| Database | SQLite (WAL mode) + SQLAlchemy |
| Queue | SQLite-backed job queue + Python workers |
| Progress | Server-Sent Events (SSE) |

## Sidebar Structure
**WORKSPACE:** Dashboard, Upload Videos, YouTube Import, AI Auto Clipper, Manual Clipper, Scene Detection, AI Highlights, AI Gaming Highlights, Reels & Shorts Studio, Captions Studio, Custom Music Studio, Audio Studio, Video Editor, Timeline Editor, Smart Captions, AI Reframing, Thumbnail Studio, Social Text, Batch Processing

**LIBRARY:** My Projects, Video Library, Generated Clips, Clips Gallery, Reels Library, Music Library, Collections, History (with queue manager), Processing Queue, Storage Manager, AI Analytics, Performance, Gemini API Key, Settings, About CLIPFORGE AI (exact order: frontend/lib/nav.ts)

## Project Structure (Phase 1-9 base; Phase 10-12 modules are under 'Added Modules' and 'Modules added later in Phase 12')
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
- Phase 10-11: `SCENE_AI_MAX_UNITS` (default 150), `SCENE_AI_BATCH` (default 8), `MAX_MUSIC_MB` (default 300).

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

### Phase 10 Notes: Advanced Scene Detection (category clips)
Scene Detection page: pick categories (20, incl. custom text), set a duration per category (Complete Scene (Automatic), 30 s to 20 min, custom seconds), then Generate Clips. Tick "Preview before extraction" to only find scenes first.

Pipeline (job `scene_classify`, heavy job): PySceneDetect shots (reused) + saved transcript (reused, or transcribed once) -> shots merged into analysis units (about 12-90 s, max `SCENE_AI_MAX_UNITS`=150) -> 3 small frames per unit (FFmpeg, 384 px, in memory) + dialogue -> ONE Gemini call per `SCENE_AI_BATCH`=8 units (retry on 429/503) -> score 0-100 per category -> consecutive positive units become one scene (single weak unit bridged) -> confidence = duration weighted mean -> fixed duration picks the most relevant continuous window (never padded with unrelated footage) -> optional snap to shot cuts -> thumbnails -> clip_export jobs.
- Folders: `storage/generated_clips/<category>/<category>_scene_001.mp4` (optional `.srt` beside it). Scene thumbnails: `storage/thumbnails/scene_<id>.jpg`.
- Status: `detected` (confidence >= threshold, Gemini) or `uncertain` (weaker, or speech-keyword fallback). Only `detected` scenes are auto-extracted; uncertain ones can be extracted by hand. "Adjust" edits start/end before extraction.
- Duplicates: a scene overlapping an already extracted scene of the same category (50% or more) is skipped. After export the clip length is compared with the plan (`verified`).
- Original video is never changed. Audio is always kept.
- Files: `backend/scene_ai/` (categories.py, engine.py, extract.py), `backend/workers/scene_handlers.py`, `backend/api/scene_ai.py`, table `category_scenes`, `frontend/app/scene-detection/page.tsx`. Tests: `tests/test_phase10_scene_ai.py` (generates a real video, mocks only the AI call, checks the MP4 files).
- Endpoints: `GET /api/scene-ai/categories`, `POST /api/scene-ai/videos/{id}/run`, `GET /api/scene-ai/videos/{id}/scenes`, `PATCH|DELETE /api/scene-ai/scenes/{id}`, `POST /api/scene-ai/videos/{id}/extract`, `GET /api/scene-ai/videos/{id}/export.zip`.
- PRIVACY: with "Look at video frames" on, small still frames are sent to Google Gemini. Turn it off to send transcript text only.
- Limits: accuracy depends on Gemini (no key / 403 / quota = speech keywords only, always `uncertain`). Boundaries are as exact as the analysis unit (12-90 s, aligned to shot cuts), so check "Adjust" for important clips. Very long movies use fewer, longer units. Audio-only sounds (music without picture clues) are judged by frames and dialogue only.
### Phase 11 Notes: Custom Music and Audio Studio
Pages: **Music Library** (`/music`) and **Audio Studio** (`/audio-studio`). "Add Music" buttons: Scene Detection cards, Generated Clips, Manual Clipper clip list, Video Editor.

How to use: 1) Music Library: upload your own audio (MP3, WAV, AAC, M4A, FLAC and any FFmpeg format), optionally put it in a folder, add tags (epic, soft, funny...) and collections. 2) Open a clip, press Add Music (or open Audio Studio and pick a clip). 3) Add tracks, set volumes, start, trim, fades, loop. 4) Preview (first 20 s, not saved), then Export MP4 (saved as a NEW clip in `storage/edited_clips/`, also in Generated Clips). Suggest from my library: choose the scene type; only tracks from YOUR library are suggested, you must approve each one.

How the mix works (job `audio_mix`, a light job, progress + cancel): `ffmpeg -i clip -i music... -filter_complex ... -map 0:v:0 -c:v copy`. The picture is stream-copied: no re-encode, same resolution, frame rate, cuts and length. Only the audio is mixed (original audio at its volume + each music track: trim, loop, fades, delay, volume) with `amix normalize=0`, a safety limiter, padded and cut to the clip length (music never makes the clip longer). Original sound effects are kept unless you turn the original audio off. Codec AAC / MP3 / Opus, 96-320 kbps.
- Waveforms: 8 kHz mono stream from FFmpeg, ~240 peaks cached in `storage/music/peaks/`. Library files: `storage/music/`.
- Tables: `music_tracks`, `music_collections`, `music_collection_tracks`. Files: `backend/audio_studio/` (mix.py, waveform.py, suggest.py), `backend/workers/audio_handlers.py`, `backend/api/audio_studio.py`, `frontend/app/music/page.tsx`, `frontend/app/audio-studio/page.tsx`, `frontend/components/Wave.tsx`. Tests: `tests/test_phase11_audio.py` (real video + real audio, checks codec, size, fps, duration, volumes, source untouched).
- Endpoints: `POST /api/music/upload`, `GET /api/music`, `PATCH|DELETE /api/music/{id}`, `GET /api/music/{id}/stream|waveform`, `GET|POST|DELETE /api/music-collections...`, `POST /api/audio-studio/clips/{id}/mix|preview`, `GET /api/audio-studio/preview/{job_id}`, `POST /api/audio-studio/suggest`. `.env`: `MAX_MUSIC_MB` (default 300).
- Limits: music file's own copyright is your responsibility (nothing is downloaded). Trim, start and fades are set with numbers and sliders (no drag-and-drop on the timeline). The preview is a short rendered file, not live real-time mixing. Suggestions use track names, folders and tags only (the AI cannot hear the audio), so tag your tracks. A very short or silent source clip stays silent where the original is off and no music plays. Original video with no audio works (music only).
### Phase 12.1 Notes: Foundation (storage, DB, sidebar, About, dashboard stats)
- New storage folders `reels`, `music`, `captions` (plus existing `subtitles`, `projects`, `collections`, `exports`), created at startup by `ensure_storage_dirs()`.
- New tables `reels`, `caption_styles`, `social_texts` in `backend/database/models_phase12.py` (auto-created by `init_db`).
- Endpoints: `GET /api/studio/stats` (real counts, storage per folder, recent projects and exports), `GET /api/about`, `GET /api/reels`, `GET|DELETE /api/reels/{id}` (delete only removes files inside `storage/reels` and `storage/thumbnails`).
- Frontend: new sidebar (`lib/nav.ts`), pages `/about`, `/reels` (placeholder until 12.5/12.6), `/reels-library`, `/queue` (opens History), `components/StudioStats.tsx` on the dashboard (stats + quick actions).
- Files: `backend/api/studio_stats.py`, `backend/database/models_phase12.py`. Tests: `tests/test_phase12_foundation.py`.

---

## Phase 12.2 Notes: Gaming intelligence module (`backend/gaming/`)
- `categories.py`: 25 gaming categories + custom text category (keywords, audio type, hint for Gemini).
- `signals.py`: audio energy per second via FFmpeg (streamed, low RAM). No audio = no signal.
- `scoring.py`: vision (Gemini frames) 50% + audio 25% + transcript 25%. Needs at least 2 positive signals to be `detected`, otherwise `uncertain`. No speech = no text signal (no fake data).
- Rules: police chase needs police cues (else capped, car chase wins); gunfight vs fist fight decided by gun cues.
- `pipeline.py`: score_units() reuses engine.classify (Gemini frames) + audio energy + transcript. Without Gemini vision a scene is always `uncertain`.
- Tests: `tests/test_phase12_gaming.py`, `tests/test_phase12_pipeline.py`. `workers/gaming_handlers.py` (job `gaming_classify`), `api/gaming.py`. Gaming scenes are stored in `category_scenes` with category `gta_<id>` (folder `storage/generated_clips/gta_<id>/`), hidden from the Scene Detection page. Thumbnail, adjust, delete and extract reuse `/api/scene-ai/...`.
- Endpoints: `GET /api/gaming/categories`, `POST /api/gaming/videos/{id}/run`, `GET /api/gaming/videos/{id}/highlights?category=`.
- Tests: `tests/test_phase12_gaming_job.py`. Real GTA video test comes in 12.12.
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
- [x] Performance tuning from real timings (Low-memory mode, frame size; benchmark in PERFORMANCE_REPORT.md)

### Phase 10: Advanced Scene Detection (category-based clips)
- [x] 10.0 Inspect existing code (detector, Gemini client, highlights, clip export, Scene Detection page)
- [x] 10.1 Detection engine
  - [x] Frame sampling (3-4 small frames per scene, FFmpeg, low RAM)
  - [x] Reuse saved transcript and existing PySceneDetect scenes
  - [x] Batched Gemini vision classification (6-8 scenes per call, JSON output, retry on 429/503)
  - [x] 20 categories + custom category (free text)
  - [x] Category-specific rules (fighting vs angry talk, romantic vs friendship/family)
  - [x] Confidence score + "uncertain" marking, local keyword fallback when Gemini is unavailable
  - [x] Merge consecutive related scenes, avoid duplicates
  - [x] Duration logic: Complete Scene (Automatic), fixed 30s-20min, custom (no padding with unrelated footage)
  - [x] Unit tests
- [x] 10.2 Extraction and storage
  - [x] Category folders (storage/generated_clips/fighting, romantic, comedy, ...)
  - [x] Descriptive filenames (fighting_scene_001.mp4)
  - [x] Reuse clip_export job, verify start/end after export, original never modified
  - [x] Duplicate clip guard, manual boundary adjustment API
  - [x] Optional subtitles and thumbnails, ZIP export of all categories
  - [x] Cancel, retry, temporary file cleanup
- [x] 10.3 Scene Detection page
  - [x] "Select Which Scenes You Want to Extract" (checkboxes + icons)
  - [x] Per-category duration dropdown
  - [x] Extra options (min/max duration, confidence threshold, merge, preserve audio, etc.)
  - [x] Result cards + timeline, preview, Extract Clip, select all, extract selected
- [x] 10.4 Real video test (2026-11-21: fighting, romantic, custom category, fixed 60 s and 180 s, duplicate guard, one failed Gemini batch handled; extract verified=True)
- [x] 10.5 README notes + final limitations report (Phase 10 Notes, FINAL_REPORT.md)
- [x] Phase 9 performance timing test done 2026-11-21 (see Phase 12.12 Update: benchmark)
### Phase 11: Custom Music and Audio Studio
- [x] 11.0 Inspect existing code (editor ops/handlers/API, clip export, caption/reframe handlers, clips + manual clipper + editor + scene pages, config, cleanup)
- [x] 11.1 Music library (backend)
  - [x] Upload MP3, WAV, AAC, M4A, FLAC and any FFmpeg-supported audio (ffprobe check, stored in storage/music/)
  - [x] Folders and collections, rename, delete, stream preview, reuse
  - [x] Waveform peaks (small JSON, made with FFmpeg, no big RAM)
- [x] 11.2 Audio mixing engine (FFmpeg)
  - [x] Original volume 0-100%, music volume 0-100%, original ON/OFF, music ON/OFF
  - [x] Music start offset, music trim (in/out), fade-in/out, loop when shorter
  - [x] Multiple music tracks
  - [x] Video stream copied (no re-encode), same resolution, fps and duration; original sound effects kept
  - [x] Audio codec and quality settings (AAC / MP3 / Opus, bitrate)
  - [x] Job `audio_mix`: progress, cancel, error handling; result is a NEW clip in storage/edited_clips/
  - [x] Quick preview render (low quality, short) before final export
  - [x] Unit tests with real generated video + audio
- [x] 11.3 Music suggestions
  - [x] Suggest tracks ONLY from the local library (by category: fighting, romantic, comedy, horror, emotional, ...)
  - [x] Gemini text only (track names, tags, mood); local keyword fallback; nothing is downloaded
  - [x] User must approve every suggestion
- [x] 11.4 UI
  - [x] Music Library page (upload, folders, collections, rename, delete, preview)
  - [x] Audio Studio page with dark timeline (video, original audio, music tracks, volume, trim, waveform)
  - [x] "Add Music" button in Scene Detection, Generated Clips, Manual Clipper and Video Editor
  - [x] Reset audio settings, preview, export, save to library
- [x] 11.5 Real test (API test passed with a generated tone; listen check by user; fighting, romantic, comedy clip + own music; original ON/OFF; mixed; trim; fades; loop; export; playback; old features still work)
- [x] 11.6 README (install, usage, testing) + final report (Phase 11 Notes, FINAL_REPORT.md)
---

### Phase 12: GTA 6 Gaming Studio (Reels, Captions, Gaming Highlights)
Goal: Upload GTA 6 video -> AI Scene Detection -> AI Highlights -> Select Scene -> Create Reel -> Add Custom Music -> Generate Captions -> Generate Social Text -> Preview -> Export.
Rules: upgrade existing CLIPFORGE AI (no new project). Originals never modified. No fake dialogue (captions only from real speech or user text). Music only from user's own library. Only process content the user is allowed to use (GTA 6 is copyrighted: follow publisher and platform policies). Test real backend before ticking any box.
- [x] 12.0 Inspect existing code and write gap list (captions, reframe, editor, thumbnails, batch, dashboard, sidebar, scene_ai categories)
- [x] 12.1 Foundation
  - [x] New storage folders: reels, subtitles, captions, projects, collections, exports
  - [x] New DB tables: reels, caption_styles, social_texts (gaming category fields come in 12.2)
  - [x] Sidebar update (Reels & Shorts Studio, Captions Studio, Custom Music Studio, Reels Library, Processing Queue, About CLIPFORGE AI)
  - [x] About page, dashboard stats (videos, clips, reels, captions, music, jobs, storage, recent projects/exports) + quick actions
- [x] 12.2 GTA gaming intelligence (code + unit tests; real video test in 12.12)
  - [x] 25 gaming categories (fighting, shooting, police chase, car chase, crash, explosions, mission, funny, cinematic, stealth, stunts, ... + custom)
  - [x] Multi-signal scoring: sampled frames + transcript + audio energy (never one frame alone)
  - [x] Gaming-specific rules (police chase vs car chase, fight vs gunfight) + tests
- [x] 12.3 AI Gaming Highlights page (API test + browser check by user DONE 2026-11-21)
  - [x] Cards: thumbnail, category, start/end, duration, AI description, confidence
  - [x] Preview, Extract Clip, multi-select batch extract
- [x] 12.4 Captions Studio (real burn test passed)
  - [x] 8 presets (Gaming, Viral Reels, Cinematic, Bold Highlight, Minimal, Word-by-Word, Karaoke, Custom)
  - [x] Customization (font, size, colors, outline, shadow, position, alignment, line spacing, words per line, timing, animation)
  - [x] Word-by-word highlight (ASS karaoke), manual correction, language choice (Whisper)
  - [x] Export SRT, VTT, burned MP4, separate subtitle files; caption preview before export
  - [x] Manual text overlays for gameplay without speech
- [x] 12.5 Reels and Shorts backend
  - [x] Platform presets (YouTube Shorts, Instagram, Facebook, TikTok-compatible), formats 9:16, 1:1, 16:9, 1080x1920
  - [x] Durations 15/30/45/60/90 s, 3 min, custom (respect platform limits)
  - [x] AI reel pipeline: most active audio window, dead-time trim, reframe, optional music, thumbnail, MP4 (captions: use Captions Studio on the reel clip)
  - [x] Manual crop/reposition (cx, cy), start/end change, brightness/contrast/saturation
  - [x] Intro/outro text cards (12.5b)
- [x] 12.6 Reels Studio UI (page /reels, real reel test passed)
- [x] 12.7 Social text generator
  - [x] Title, description, caption, hashtags, keywords, CTA, pinned comment
  - [x] Tones (viral, funny, cinematic, professional, suspenseful, minimal); text based on real video content; user edits and approves
- [x] 12.8 Video Editor upgrade (a: timeline/split/transitions, b: text overlays + music tracks, c: Timeline Editor page with undo/redo)
  - [x] Video, audio and caption timelines, multiple audio tracks
  - [x] Text overlays, trim, split, clip arrangement, transitions, undo/redo
- [x] 12.9 Thumbnail Studio upgrade (AI suggestions, platforms, crop, background effects, PNG/JPG)
- [x] 12.10 Batch Processing upgrade (a: multi-video analyze, clips, reels, music, progress/cancel/retry; b: caption preset per clip)
- [x] 12.11 Performance (low-memory mode, analysis frame size, safe stale-temp cleanup, /performance page)
- [x] 12.12 Full workflow test (live API run, benchmark, 10.4 retest, speech captions, real music, browser checks all DONE)
- [x] 12.13 README update + final report (see FINAL_REPORT.md; real tests still pending are listed there and in Known Findings)

### Phase 12.3 Notes: AI Gaming Highlights page
- Page: `frontend/app/gaming-highlights/page.tsx` (sidebar: AI Gaming Highlights, `/gaming-highlights`). Check script: `.\scripts\check-12-3.ps1`.
- Flow: pick video -> tick gaming categories (duration per category) -> "Find Gaming Highlights" (job `gaming_classify`, progress shown) -> cards (thumbnail, category, start/end, duration, description, confidence, Detected/Uncertain) -> Preview (plays the range in the player) -> Extract Clip or Select + "Extract selected" -> clips appear in Generated Clips.
- Uses `/api/gaming/categories`, `/api/gaming/videos/{id}/run`, `/api/gaming/videos/{id}/highlights`, and `/api/scene-ai/videos/{id}/extract`, `/api/scene-ai/scenes/{id}` (delete).
- PRIVACY: with "Look at video frames" on, small still frames go to Google Gemini. Off = audio and speech only, scenes stay "uncertain".
- Limits: Preview needs a browser-playable format (MP4/WebM). Boundaries are as exact as the analysis unit, so check important clips by hand.
### Phase 12.4 Notes: Captions Studio
- Page `/captions-studio`. Files: `backend/captions/` (presets.py, builder.py, burn.py, preview.py), `frontend/app/captions-studio/page.tsx`. Tests: `tests/test_phase12_captions_studio.py`, `tests/test_burn_filter_regex.py`.
- 8 presets, custom style, word-by-word and karaoke (ASS), manual text overlays (gameplay without speech), Whisper language choice.
- Endpoints: `GET /api/clips/{id}/captions/presets`, `POST .../captions/studio-preview` (JPEG frame), `POST .../captions/studio-burn` (NEW clip), `GET .../captions.srt|.vtt|.ass`.
- Fix: `has_subtitles_filter()` regex only matched 3-letter flags; FFmpeg 9.x prints 2-letter flags (`..`), so burn was always refused. Now flexible + regression test.
- Real burn test passed (generated video, overlay, ffprobe on result). Needs FFmpeg with libass.
### Phase 12.6 Notes: Reels Studio UI
- Page: `frontend/app/reels/page.tsx` (clip, platform, size, length, reframe mode, colour, audio, music from your library) -> `POST /api/reels-studio/create` -> job polling -> preview, download, links to Captions Studio and Audio Studio.
- Result is a NEW clip (original untouched). Platform limits come from `GET /api/reels-studio/platforms`.
- Real test: generated 1280x720 video -> Instagram Reels preset at 720 -> ffprobe gave 720x1280.

---
## Changelog
- 2026-11-21: Autostart verified: Startup shortcut checked/installed. PC on hone par servers hidden start hote hain aur Edge http://localhost:3000 kholta hai.
- 2026-11-21: 12.3 browser check DONE (user): gaming highlights find, cards, preview, extract all worked. All phases 1 to 13 complete. speech_music_test.py upload field fixed.
- 2026-11-21: Speech and music real test DONE: one-click chain on a video with real speech: reel 720x1280 PASS, captions 13 lines burned PASS, real mp3 mix PASS (length equal), social text PASS, final clip plays. Test script: scripts\speech_music_test.py (upload field is files, script falls back to newest library video). Still open: browser check of /gaming-highlights.
- 2026-11-21: Phase 13.3 DONE: full pytest (215 passed in 221.53s (0:03:41)), live audit 119 PASS / 0 FAIL, YouTube publish removed. Remaining optional checks: speaking-video captions, real music listening, /gaming-highlights browser check.
- 2026-11-21: Publish links removed from pages: clips, clips-gallery, one-click-reel, reels, reels-library (backups in _unused/youtube_publish_removed/).
- 2026-11-21: YouTube publish REMOVED: backend/publish, api/publish.py, /publish page, YouTubePublish panel, its tests and sidebar link moved to _unused/youtube_publish_removed/. Clips can still be downloaded and uploaded by hand.
- 2026-11-21: Phase 13.3 step 1: scripts\audit_project.py + scripts\audit.ps1 (README vs disk vs live API, writes AUDIT_REPORT.md), README status synced to Phase 13.
- 2026-11-21: Reels Library shows videos (poster + player, preload metadata) and every reel has Publish to YouTube. Clips Gallery and Generated Clips (/clips) cards got a Publish button. New backend/api/reels_media.py: GET /api/reels/{id}/stream, /thumbnail, /clip (reel to clip id for Publish).
- 2026-11-21: Publish panel: two buttons. Publish to YouTube opens 'Publish as Private' and 'Publish as Public'; a confirm box (rights, and a visibility warning for public) replaces the checkboxes and the privacy dropdown. The server still requires confirm (and confirm_public for public).
- 2026-11-21: Publish button on /reels: every reel result has Publish to YouTube (opens /publish?clip=ID, the clip is pre-selected).
- 2026-11-21: Publish page /publish added (any ready clip or reel, optional title/hashtag generator, uses the YouTube panel). The panel was only on /one-click-reel before, the old /reels page has no publish button yet.
- 2026-11-21: Phase 13.2 code: backend/publish/youtube.py, backend/api/publish.py (/api/publish/youtube/...), Publish panel on /one-click-reel (components/YouTubePublish.tsx), tests/test_phase13_publish.py, scripts/test_publish_api.py. 13.1 chain test: reel PASS, music PASS, captions skipped (no speech), social text retest in 13.2 run. Real login and upload pending.
- 2026-11-21: Phase 13.1 code: One-Click Reel page /one-click-reel (reel, captions, music, social text in one go, chained over the existing APIs, frontend only), scripts\test_one_click_chain.py. Real run pending.
- 2026-11-21: Autostart added: scripts\autostart.ps1, install-autostart.ps1, disable-autostart.ps1. At Windows login the servers start hidden and Microsoft Edge opens http://localhost:3000.
- 2026-11-21: Phase 9 benchmark DONE (video 697 s: Whisper 10.3 s with no speech found, scene detection 163 s, highlight scoring 4.2 s; backend peak 530 MB; PC free RAM dropped to 1.0 GB of 7.8 GB). 10.4 retest DONE: fixed 60 s, fixed 180 s, custom, duplicate guard all PASS. Ticked 10.4, 10.5, 11.6.
- 2026-11-21: Full pytest after Phase 12: 215 passed in 121 s (0 failed, 0 skipped). First full run since Phase 8 (109 passed). No regression.
- 2026-11-21: Phase 12.13: README cleanup (sidebar, added modules, status), FINAL_REPORT.md, scripts\heavy_tests.ps1 (full pytest, benchmark, 10.4 retest, one by one).
- 2026-11-21: Phase 12.12b runs 1-4 (video 1, 697 s): live API test via scripts\real_workflow_test.py and scripts\real_scene_cases.py. PASS: analysis, gaming highlights, extract, reel 720x1280, music preview + mix, suggestions, social text, scene detection, duplicate guard, custom category, 22 old endpoints, original untouched. Script bugs fixed (reel size type, music path, platforms dict, suggest category). Video has little speech, so no captions. 10.4 fixed 1/3 min not verified yet.
- 2026-11-21: Phase 12.12a: benchmark script (scripts/benchmark.py -> PERFORMANCE_REPORT.md) and REAL_TESTS.md checklist added. Real runs pending.
- 2026-11-21: Phase 12.11 DONE: Performance page (/performance): Low-memory mode, analysis frame size, safe stale-temporary and waveform-cache cleanup, cleanup at server start. Tests: tests/test_phase12_performance.py.
- 2026-11-21: Reels page: length selector (15/30/45/60/90/180/custom), auto or manual range (start/end with player buttons), several reels from one clip, platform limit warning. Frontend only. Tests: tests/test_phase12_reels_ranges.py.
- 2026-11-21: Phase 12.10b DONE: batch captions (optional): Whisper words + Captions Studio preset burned into every reel (or clip). No speech = no captions, noted. Tests: tests/test_phase12_batch_captions.py.
- 2026-11-21: Phase 12.10a DONE: batch pipeline (analyze -> clips -> optional reel + music per clip), POST /api/batch/pipeline, job batch_pipeline, new Batch page (retry, cancel). Tests: tests/test_phase12_batch_pipeline.py.
- 2026-11-21: README check: fixed broken file names (12.7 and Gemini key notes), ticked 12.8 sub-items. Next: 12.10 Batch upgrade.
- 2026-11-21: Phase 12.9 DONE: Thumbnail Studio upgrade (AI best-frame suggestions, text ideas, 6 platform sizes, crop/zoom, blurred background, effects, PNG/JPG). Tests: tests/test_phase12_thumbs.py. Old page backup: _unused/thumbnails_page_old.tsx.
- 2026-11-21: Phase 12.8c DONE: Timeline Editor page (/timeline-editor): video/text/audio tracks, split, transitions, text overlays, music tracks, undo/redo (Ctrl+Z / Ctrl+Y). Frontend only, uses /api/editor/timeline and /api/editor/compose.
- 2026-11-21: Phase 12.8b DONE (backend): editor compose = text overlays (ASS) + multiple music tracks in one NEW clip, job editor_compose. Tests: tests/test_phase12_compose.py. UI in 12.8c.
- 2026-11-21: Phase 12.8a DONE (backend): timeline engine (segments + transitions), split, job timeline_clips. Tests: tests/test_phase12_timeline.py. UI comes in 12.8c.
- 2026-11-21: Phase 12.5b DONE: intro/outro text cards for reels (backend/reels/cards.py, API fields intro/outro, Reels page controls), real tests in tests/test_phase12_reels_cards.py.
- 2026-11-21: Gemini API Key page (/gemini-key): change the key live from the sidebar, no .env editing. Saved in storage/settings, never shown in full. Test: tests/test_gemini_key_api.py.
- 2026-11-21: Phase 12.7 DONE: social text API end-to-end test added. Fix: reels row now saves clip_id and aspect (ratio->aspect). README tracker synced (12.4 boxes ticked).
- 2026-11-21: Phase 12.6 DONE: Reels Studio page, real reel test passed (720x1280).
- 2026-11-21: Phase 12.4 DONE: fixed libass detection regex (FFmpeg 9.x), real burn test passed. runner.py restored, gaming_classify HEAVY.
- 2026-11-20: Phase 12.3 code: AI Gaming Highlights page + sidebar link + check script. Real test pending.
- 2026-11-20: Phase 12.5 DONE (except intro/outro): reels engine (platform presets, limits, audio-energy segment pick, dead-time trim, face/center/blur/manual reframe 1080/720, colour tweak, optional music), job reel_create, /api/reels-studio. Fix: gaming_classify is now a HEAVY job.
- 2026-11-20: Phase 12.2 DONE (part 3): gaming_classify job, /api/gaming API, gta_ category prefix, tests. Full suite passes. Gaming Highlights page (12.3) next.
- 2026-11-20: Phase 12.2 (part 2): gaming pipeline (frames + audio + transcript scoring, reuses scene_ai engine) + tests. Test fix (sine amplitude).
- 2026-11-20: Phase 12.2 (part 1): backend/gaming module (25 categories, audio signal, multi-signal scoring, police/gun rules) + tests. Wiring to scene_ai engine pending.
- 2026-11-20: Phase 12.0 + 12.1 done: gap inspect, new storage folders, tables (reels, caption_styles, social_texts), studio stats and About/Reels Library APIs, new sidebar, dashboard stats.
- 2026-11-20: Phase 12 planned (GTA 6 Gaming Studio: reels, captions studio, gaming highlights, social text). Tasks added to tracker.
- 2026-11-20: Phase 11.1-11.4 code: music library, audio mixing (video copy), suggestions, Audio Studio. Real-clip test pending (11.5).
- 2026-11-20: Phase 11 planned (Custom Music and Audio Studio). Tasks added to tracker.
- 2026-11-20: Phase 10.1-10.3 code: category scene detection (Gemini vision, batched), category folders, duplicate guard, ZIP, new Scene Detection page. Real-video test pending (10.4).
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

---

## Added Modules (Phase 10 to 12)
```text
backend/
  scene_ai/        categories.py, engine.py, extract.py        (Phase 10)
  audio_studio/    mix.py, waveform.py, suggest.py             (Phase 11)
  gaming/          categories.py, signals.py, scoring.py, pipeline.py   (Phase 12.2)
  reels/           presets.py, engine.py                       (Phase 12.5)
  workers/         scene_handlers.py, audio_handlers.py, gaming_handlers.py, reel_handlers.py
  api/             scene_ai.py, audio_studio.py, gaming.py, reels_studio.py, studio_stats.py
  database/        models_phase12.py (reels, caption_styles, social_texts)
frontend/app/      scene-detection, music, audio-studio, about, reels, reels-library, queue, gaming-highlights
storage/           + music, reels, captions, subtitles, projects, collections, exports
```

## Sidebar (Phase 12.1 additions)
Reels & Shorts Studio, Captions Studio, Custom Music Studio, Reels Library, Processing Queue, About CLIPFORGE AI.

## Current Status (update after every step)
- Done: Phase 1 to 9, 10.1-10.3, 11.1-11.4, 12.0 to 12.2, 12.5 (backend, with intro/outro text cards)
- Done: 12.3 AI Gaming Highlights page (browser check passed)
- Done: 12.4 Captions Studio
- Done: 12.6 Reels Studio UI
- Done: 12.7 Social text generator (API test added)
- Done: 12.8 Video Editor upgrade (a, b, c)
- Done: 12.9 Thumbnail Studio upgrade
- Done: 12.10a Batch pipeline (clips + reels + music, progress/cancel/retry)
- Done: 12.10b Batch captions (Whisper + Captions Studio preset per clip/reel)
- Done: 12.11 Performance (low-memory mode, frame size, safe cleanup)
- Next: benchmark + 10.4 retest (heavy_tests.ps1), captions test with a speaking video, browser check of /gaming-highlights. 12.13 is done (FINAL_REPORT.md). Full pytest: 215 passed.
- Pending real tests: none

### Phase 12.5 Notes: Reels and Shorts backend
- Files: `backend/reels/` (presets.py, engine.py), `backend/workers/reel_handlers.py` (job `reel_create`), `backend/api/reels_studio.py`. Tests: `tests/test_phase12_reels.py` (real generated video, checks size, duration, codec, source untouched).
- Endpoints: `GET /api/reels-studio/platforms`, `POST /api/reels-studio/create` (clip_id, platform, ratio, size 1080|720, mode face|center|blur|manual, cx, cy, target_sec, start_sec+end_sec, trim_dead_time, brightness, contrast, saturation, music[], original_audio_on, original_volume, title).
- Flow: ready clip -> segment (longer than target: most active audio window; dead time at start/end trimmed; no audio: first seconds) -> reframe -> ONE x264 encode -> optional music mix (video copied) -> thumbnail. Result is a NEW clip in `storage/edited_clips/` (also in Generated Clips, so Captions Studio and Audio Studio work on it). A row in `reels` is saved when the columns match.
- Platform limits are in `backend/reels/presets.py` (check the current rules of each platform and edit there). A target above the platform limit is refused.
- Limits: segment choice uses audio loudness only (no meaning of the scene), so check start/end by hand for important reels. Face mode = fixed crop (no moving camera). Intro/outro not yet. Music only from your own library.

### Phase 12.7 Notes: Social Text Generator
- Page /social-text. Files: backend/social/generator.py, backend/api/social.py, frontend/app/social-text/page.tsx. Table: social_texts. Tests: tests/test_phase12_social.py, tests/test_phase12_social_api.py.
- Endpoints: GET /api/social/options, POST /api/social/generate (clip_id, tone, platform, notes), GET /api/social?clip_id=, PUT /api/social/{id} (edit, approve), DELETE /api/social/{id}.
- Text is built only from the clip title, scene description and real speech. Without a Gemini key a local template is used. PRIVACY: with a key, this text (no video frames) goes to Google Gemini. The user must edit and approve.


### Gemini API Key page
- Page /gemini-key (sidebar: Gemini API Key). Files: backend/api/gemini_key.py, frontend/app/gemini-key/page.tsx. Endpoints: GET /api/gemini-key/status, POST /api/gemini-key, DELETE /api/gemini-key, POST /api/gemini-key/test.
- A saved key (storage/settings/gemini_key.json) wins over .env and is active at once. Removing it falls back to .env. The full key is never returned by the API.



### Phase 12.5b Notes: Intro / Outro cards
- `backend/reels/cards.py`: text card image (Pillow if installed, else OpenCV with ASCII text) -> short MP4 (30 fps, silent audio) -> joined with the reel (one re-encode). Music, if any, is mixed over the full length after the cards are added.
- API: `intro` and `outro` in `POST /api/reels-studio/create`: `{text (max 80), seconds (1-5), bg (#RRGGBB), fg (#RRGGBB)}`.
- Limits: text cards only (own image/video intro later). Platform max length is checked on the reel part only, cards add 1-5 s each. Without Pillow, non-English text on the card shows as '?'. Tests: `tests/test_phase12_reels_cards.py`.

### Clips Gallery page
- Page `/clips-gallery` (sidebar LIBRARY). File: `frontend/app/clips-gallery/page.tsx`. Shows only `ready` clips, 12 at a time, `preload=metadata` (low RAM). A clip whose video cannot load is hidden and can be removed with 'Delete broken'. Delete uses `DELETE /api/clips/{id}`.


### Phase 12.8a Notes: Timeline, split, transitions
- Files: `backend/editor/timeline.py`, `backend/workers/timeline_handlers.py` (job `timeline_clips`), `backend/api/timeline.py`.
- `POST /api/editor/timeline` (segments [{clip_id,start,end}] max 20, ratio first|9:16|1:1|16:9, transition none|fade|fadeblack|dissolve|wipeleft|slideleft|circleopen, transition_sec 0.2-2). `POST /api/editor/split` (clip_id, at) makes two NEW clips.
- Result is always a NEW clip, sources untouched, one re-encode, audio crossfades with video, silent segments get silence. Every segment must be at least 2x transition_sec long.

### Phase 12.8b Notes: Text overlays + music tracks in the editor
- Files: `backend/api/compose.py`, `backend/workers/compose_handlers.py` (job `editor_compose`). Reuses `captions.presets.to_ass_studio` + `burn_captions` and `audio_studio.mix.mix_audio`.
- `POST /api/editor/compose`: clip_id, overlays [{text, start, end, position}] max 30, style {font, font_size, primary, outline_color, bold, uppercase, animation}, music [{track_id, volume 0-100, start_sec, trim_in, trim_out, fade_in, fade_out, loop}] max 6, original_on, original_volume.
- Order: overlays burned first (video re-encoded once), then music mixed (video copied). Needs FFmpeg with libass for overlays. Music only from your own library. Result is a NEW clip.

### Phase 12.8c Notes: Timeline Editor page
- Page `/timeline-editor`, file `frontend/app/timeline-editor/page.tsx` (sidebar: Timeline Editor). The old Video Editor page is unchanged.
- Step 1: segments (any ready clip, start/end, reorder, split) + transition + output size -> Render timeline (NEW clip). Step 2: choose the clip (the rendered one is auto-selected), add text overlays and music tracks -> Apply text & music (NEW clip).
- Undo/redo covers all timeline, overlay, music and audio settings (50 steps). Typing inside a text box uses the browser's own undo.
- Limits: the three tracks are a display, no drag-and-drop (times are typed). No live preview of transitions: render to see them. Overlay and music times are relative to the clip they are applied to.

### Phase 12.9 Notes: Thumbnail Studio upgrade
- Files: `backend/thumbs/suggest.py`, `backend/api/thumbnails.py` (new routes), `frontend/app/thumbnails/page.tsx`.
- `POST /api/thumbnails/suggest` (clip_id, count, use_gemini): samples about 14 small frames one at a time, scores them with OpenCV (sharpness, brightness balance, contrast, colour) and returns the best spread-out times. Text ideas come only from the clip title and scene description (Gemini text only, local fallback). `GET /api/thumbnails/platforms`. `GET /api/clips/{id}/frame?t=&size=` (320-2560).
- Page: platform size, fill or blurred-background fit, zoom + crop position, brightness/contrast/saturation, vignette, shade, font, PNG or JPG. Drawn in the browser canvas.
- Limits: the score measures image quality, not meaning (it cannot tell a good moment from a nice-looking empty frame). Effects use canvas filters (Chrome/Edge/Firefox). Fonts depend on the PC.

### Phase 12.10a Notes: Batch pipeline (clips + reels + music)
- Files: `backend/api/batch.py` (new `POST /api/batch/pipeline`, `GET /api/batch/jobs` lists both batch types), `backend/workers/batch_pipeline_handlers.py` (job `batch_pipeline`, HEAVY), `frontend/app/batch/page.tsx`. Tests: `tests/test_phase12_batch_pipeline.py`.
- Flow per video (one video at a time, RAM safe): analyze if needed -> pick best highlights -> export clips -> optional reel for every clip (platform, size, reframe mode, music from your library) as NEW clips. One job runs all steps in order (it calls the clip_export and reel_create handlers directly, no waiting on the queue).
- Progress: one bar per video. Cancel: stops after the current step and marks unfinished clips cancelled. Retry: button in the table (`/api/queue/{id}/retry`).
- Result summary is saved in settings key `batch_result:<job_id>` (clips ready/failed, reels ready/failed, notes).
- Limits: caption style per clip is not in the batch yet (12.10b): use Captions Studio on the reel clips. If clips export but every reel fails, the job is marked failed and the clips stay (make reels in Reels Studio). The page offers one music track per batch (the API accepts up to 5).

### Phase 12.10b Notes: Batch captions
- Files: `backend/workers/batch_pipeline_handlers.py` (step 5), `backend/api/batch.py` (fields `captions`, `caption_preset`, `caption_language`), `frontend/app/batch/page.tsx`. Tests: `tests/test_phase12_batch_captions.py` (Whisper is mocked, FFmpeg burn is real, needs libass).
- Order per video: clips -> reels (optional) -> captions. Captions go on the reel when reels are on, otherwise on the plain clip. Each captioned result is a NEW clip titled "... (captions)"; the clip it came from is kept.
- Uses the existing `caption_generate` and `caption_burn` handlers with a Captions Studio preset (gaming, viral_reels, cinematic, bold_highlight, minimal, word_by_word, karaoke).
- Captions never fail the job. No speech or a Whisper/burn error = that clip stays without captions and a note is saved (`captions_skipped`). No libass = captions skipped with a note.
- Limits: Whisper runs for every clip (slow, needs RAM, keep the batch small on 8GB). A reel with original audio off and only music usually has no speech, so it gets no captions. Only the preset is chosen in the batch; fine tuning is in Captions Studio.

### Reels page: length, range and several reels
- File: `frontend/app/reels/page.tsx` (backend unchanged, it already had `target_sec`, `start_sec`/`end_sec` and the platform limit check). Test: `tests/test_phase12_reels_ranges.py`.
- Length: full clip, 15/30/45/60/90/180 s or custom seconds (options above the platform limit are hidden). Range: Auto (most active part) or Manual (start/end sliders, numbers and "= player time" buttons).
- "Make several reels": the chosen range is cut into equal parts of the chosen length (max 20; a last piece under 3 s is dropped). One `POST /api/reels-studio/create` per part, titles "... - part N", the page follows all jobs and shows every reel.
- A length or range above the platform limit shows a red message and the button is disabled. Intro/outro seconds are added on top of every reel.
- Limits: manual range times are relative to the selected clip. Parts run through the normal queue (one after another on 8GB RAM). Dead-time trim applies only to the auto range.

### Phase 12.11 Notes: Performance
- Files: `backend/services/performance.py`, `backend/api/performance.py`, `frontend/app/performance/page.tsx` (sidebar: Performance), small patches in `backend/main.py` (startup housekeeping + router) and `backend/scene_ai/engine.py` (`grab_jpeg` reads `FRAME_WIDTH`, default 384). Tests: `tests/test_phase12_performance.py`.
- Settings are saved in `storage/settings/performance.json` and applied to the running server at once (Whisper, Gemini batches and frame size read their env values on every call). Turning a setting off restores what `.env` had.
- Low-memory mode: `WHISPER_MODEL=base`, `WHISPER_BEAM_SIZE=1`, `SCENE_AI_BATCH=4`, `SCENE_AI_MAX_UNITS=80`, `FRAME_WIDTH=256`. Frame size can also be set alone (256/320/384/512); it affects Scene Detection and Gaming Highlights (both use `engine.grab_jpeg`).
- Cleanup: `GET /api/performance`, `POST /api/performance` (low_memory, frame_width), `POST /api/performance/cleanup` (target `stale_temporary` = files older than 6 h inside `storage/temporary`, `music_peaks` = waveform cache only). At server start, temporary files older than 24 h are removed. The old Storage Manager "temporary" button still empties the whole folder: use it only when no job is running.
- Limits: the real timing and peak RAM measurements (Whisper speed, analysis time) are still pending in 12.12. The `base` Whisper model is less accurate than `small`, especially for non-English speech.

### Phase 12.12a Notes: Benchmark and real test checklist
- `scripts/benchmark.py` (backend must be running, no other jobs): runs Whisper transcript, scene detection and highlight scoring one by one on an uploaded video, measures seconds and the peak RAM of the backend process (sampled every 0.5 s), and appends a table to `PERFORMANCE_REPORT.md`. Options: `--video-id`, `--gemini`, `--gaming`, `--vision`, `--timeout`. Run it with low-memory mode off and on to compare. It redoes the transcript of the chosen video.
- `REAL_TESTS.md`: manual checklist for 12.3 (gaming highlights), 10.4 (scene detection), 11.5 (audio studio) and the full workflow. Test: `tests/test_phase12_benchmark.py`.

### Phase 12.12b Notes: Live workflow test
- File: `scripts/real_workflow_test.py` (standard library only; big uploads use curl.exe). The backend must be running (`.\scripts\start-all.ps1`).
- Run: `.\.venv\Scripts\python.exe scripts\real_workflow_test.py --video-id 1 --music-file "E:\music\song.mp3"`. Without `--video-id` the latest video with picture is used. `--video-file` uploads one first.
- Options: `--cats a,b,c` (gaming categories), `--platform`, `--confidence` (default 40), `--no-gemini`, `--no-scene-ai`, `--timeout` (seconds per job).
- Steps: health, Gemini/Whisper status, video, AI analysis, gaming highlights + thumbnail (12.3), extract clips, reel (12.5), music preview + mix (11.5), music suggestions (11.3), captions (12.4), social text (12.7), Scene Detection category + extract (10.4), 22 old GET endpoints (regression), original video untouched (file size before and after).
- Result: table on screen and appended to `REAL_TEST_RESULT.md`. PASS / WARN / FAIL / SKIP. WARN is acceptable (for example no speech = no captions). Every FAIL must be fixed first.
- Limits: it checks API results and that files play, not whether the AI chose the right scene: watch the extracted clips yourself. Boxes 12.3, 10.4, 11.5 and 12.12 are ticked only after a run without FAIL.

### Pages added in Phase 10 to 12 (sidebar routes)
`/scene-detection`, `/gaming-highlights`, `/music`, `/audio-studio`, `/reels`, `/reels-library`, `/captions-studio`, `/social-text`, `/timeline-editor`, `/clips-gallery`, `/batch`, `/performance`, `/gemini-key`, `/about`, `/queue`. A full cleanup of the Sidebar and Project Structure sections comes in 12.13.

- Re-run only some steps: `.\.venv\Scripts\python.exe scripts\real_workflow_test.py --video-id 1 --only reel,music,social --music-file "<your mp3>"` (uses the latest ready clip, or `--clip-id N`).

### Phase 12.12 Known Findings (real tests on video 1, 697 s GTA comparison)
- Live API run (`scripts\real_workflow_test.py`): analysis, gaming highlights + thumbnails, clip extract, reel (720x1280), music preview + mix (length equals source), music suggestions, social text, Scene Detection + extract, 22 old endpoints, original file untouched: all PASS. Only WARN: no speech, so no captions.
- Speech: this video is mostly music and game sound. Whisper `base` with VAD on finds no speech (0 segments). With VAD off it returns 27 segments, mostly invented text (repeated words, wrong language guess) and a few real English lines. Decision: keep VAD on. Result: videos without clear speech get no transcript, so no AI Highlights (they need one) and no captions. Test captions on a video with clear commentary and pick the language by hand if auto detect is wrong.
- 10.4: fixed 1 and 3 minute durations are NOT verified. The test run only found an older extracted scene (231 s), which is kept on purpose; new scenes overlapping it by 50% or more are skipped as duplicates. `scripts\real_scene_cases.py` now removes old scenes of the category first (clips are kept) so the retest is valid.
- Gemini: one batch failed ("returned no usable unit"). The job still finished with the other batches and the page shows a warning. No crash.
- Deferred on purpose (heavy for an 8 GB PC at 73-83% RAM): Phase 9 benchmark (`scripts\benchmark.py`), 10.4 retest (`scripts\real_scene_cases.py 1`), captions test with a speaking video, browser check of `/gaming-highlights` and `/clips-gallery`.

## Modules added later in Phase 12
```text
backend/
  captions/        presets.py, preview.py (Captions Studio, 12.4)
  reels/           cards.py (intro/outro, 12.5b)
  social/          generator.py                                  (12.7)
  editor/          timeline.py                                   (12.8a)
  thumbs/          suggest.py                                    (12.9)
  services/        performance.py                                (12.11)
  workers/         timeline_handlers.py, compose_handlers.py, batch_pipeline_handlers.py
  api/             social.py, timeline.py, compose.py, gemini_key.py, performance.py
frontend/app/      captions-studio, social-text, timeline-editor, clips-gallery, batch, performance, gemini-key, thumbnails
scripts/           real_workflow_test.py, real_scene_cases.py, benchmark.py, heavy_tests.ps1
```
Reports: `FINAL_REPORT.md` (results and limits), `REAL_TEST_RESULT.md` (raw test tables), `PERFORMANCE_REPORT.md` (after benchmark), `REAL_TESTS.md` (manual checklist).

### Phase 12.12 Update: benchmark and 10.4 retest (2026-11-21)
- Benchmark (`scripts\benchmark.py --video-id 1`, low-memory off, Gemini off): Whisper base 10.3 s, scene detection 163 s, highlight scoring 4.2 s on a 697 s video. Backend peak RAM 530 MB. PC RAM: lowest free 1.0 GB of 7.8 GB, so close the browser and other apps for long videos. Details in `PERFORMANCE_REPORT.md`.
- The Whisper time is NOT a real speed: VAD found no speech in this video, so almost nothing was transcribed. Measure Whisper speed with a video that has clear speech. Scene detection is the slowest step (about 4.3 video seconds per work second): a 1 hour video needs roughly 15 minutes.
- 10.4 retest (old scenes removed first, clips kept): fixed 60 s gave scenes of 34 s and 60 s, fixed 180 s gave 139 s (none longer than the limit), custom category job completed (0 scenes, no helicopter in the video), duplicate guard kept one scene for an already extracted range.
- Full pytest: 215 passed in 121 s.
- Still open: captions test with a speaking video, listening check of a clip mixed with real music.

### Autostart (Windows login, Microsoft Edge)
- Turn on: `.\scripts\install-autostart.ps1` (puts a shortcut in the Windows Startup folder, no admin needed). Turn off: `.\scripts\disable-autostart.ps1`.
- At login `scripts\autostart.ps1` waits 15 s, starts the backend (port 8000) and frontend (port 3000) hidden, waits up to 3 minutes until both answer, then opens `http://localhost:3000` in Microsoft Edge. If the servers already run, it only opens Edge.
- Log: `logs\autostart.log` (if nothing opens, read it first). Stop the servers: `.\scripts\stop-all.ps1` (pids are saved in `logs\pids.txt`). Manual start with visible windows: `.\scripts\start-all.ps1` (opens the default browser).
- Limits: the servers use RAM all the time (8 GB PC: close them with stop-all when you do not need the app). The frontend starts in the mode set in `start-frontend.ps1`.

### Phase 13: One-Click Reel and YouTube publish
- [x] 13.1 One-Click Reel: chain test done (reel PASS, social text PASS, captions WARN = no speech, music chain pending a real mp3)
- [-] 13.2 Publish to YouTube: REMOVED by owner (2026-11-21). Files saved in _unused/youtube_publish_removed/
- [x] 13.3 Tests and README final (full pytest + audit done)

### Phase 13.1 Notes: One-Click Reel
- Page `/one-click-reel` (sidebar: One-Click Reel), file `frontend/app/one-click-reel/page.tsx`. Frontend only: it calls existing APIs one after another and follows each clip until it is ready.
- Order: reel (`POST /api/reels-studio/create`) -> captions (`captions/generate`, then `captions/studio-burn` with `{preset}`) -> music (`POST /api/audio-studio/clips/{id}/mix`, video copied) -> social text (`POST /api/social/generate`). Captions run before music so Whisper hears the original sound.
- Every step gives a NEW clip. A captions error or no speech never stops the rest (a note is shown). Cancel stops the current job.
- Test: `.\.venv\Scripts\python.exe scripts\test_one_click_chain.py [clip_id] [tone.wav]` runs the same API chain (results in `REAL_TEST_RESULT.md`).
- Limits: no live preview of the final mix, music comes only from your own library (one track), whole chain needs RAM for Whisper (8 GB PC: close other apps). With a Gemini key the social text step sends text (no frames) to Google.

### Phase 13.2 Notes: Publish to YouTube
- Files: `backend/publish/youtube.py` (login, token, resumable upload in a background thread, progress, cancel), `backend/api/publish.py`, `frontend/components/YouTubePublish.tsx` (panel under the result on `/one-click-reel`). Tests: `tests/test_phase13_publish.py` (no network), `scripts/test_publish_api.py` (safe API checks, no upload).
- Setup once: Google Cloud project -> enable YouTube Data API v3 -> OAuth consent screen (add your channel email as a test user) -> OAuth client of type DESKTOP APP -> download the JSON as `storage\settings\youtube_client_secret.json` (never share it; `storage` is git-ignored). A `web` client is refused with a clear message. The token is saved in `storage\settings\youtube_token.json`.
- Endpoints: `GET /api/publish/youtube/status`, `POST .../connect` (opens the Google login in the browser), `POST .../disconnect`, `POST .../upload` (clip_id, title, description, tags, privacy, confirm, confirm_public), `GET .../uploads`, `GET .../uploads/{id}`, `POST .../uploads/{id}/cancel`.
- Safety: default privacy is private. Upload needs `confirm: true` (rights to the video and music), public needs `confirm_public` too. One upload at a time. Video is marked "not made for kids", category People and Blogs. `<` and `>` are removed from title and description.
- Limits: new Google API projects keep videos private until Google audits the project; the panel shows a note when YouTube changed the privacy. Daily quota is about 6 uploads (default 10,000 units, one upload about 1,600). In Testing mode of the consent screen the login token expires after about 7 days: connect again. GTA footage and songs can get copyright claims: upload only content you may use.
- Page `/publish` (sidebar: Publish to YouTube), file `frontend/app/publish/page.tsx`: choose any ready clip or reel, optionally generate title/description/hashtags (Social Text), then Connect YouTube and Publish (same panel as on `/one-click-reel`).

---

## Current Status (Phase 13 update, newest)
- Done: Phase 1 to 12 (code + API tests). Full pytest: 215 passed.
- In progress: Phase 13
  - [x] 13.1 One-Click Reel: chain test done (reel PASS, social PASS, captions WARN no speech)
  - [-] 13.2 Publish to YouTube: REMOVED (files in _unused/youtube_publish_removed/)
  - [x] 13.3 Tests and README final (audit 119 PASS)
- Pending real checks: browser check of /gaming-highlights and /clips-gallery, captions test with a speaking video, listening check of a clip with real music.
- Sidebar routes added in Phase 13: /one-click-reel, /publish (also /gemini-key, /clips-gallery, /performance, /batch from Phase 12).
- Audit: `.\scripts\audit.ps1` (needs backend running). Result in `AUDIT_REPORT.md`.

### Phase 13 backend additions
```text
backend/publish/youtube.py      login, token, resumable upload
backend/api/publish.py          /api/publish/youtube/...
backend/api/reels_media.py      /api/reels/{id}/stream|thumbnail|clip
frontend/app/one-click-reel, frontend/app/publish, frontend/components/YouTubePublish.tsx
scripts/test_one_click_chain.py, scripts/test_publish_api.py, scripts/audit_project.py, scripts/audit.ps1
```

> NOTE (2026-11-21): The sections 'Phase 13.2 Notes: Publish to YouTube', the Publish buttons and the /publish page described above no longer exist. Use Download and upload by hand.


## Final Status (2026-11-21)
- Done: Phase 1 to 13. Full pytest: 215 passed. Live audit: 119 PASS, 0 FAIL.
- Real tests done: captions on real speech, real music mix, reel, social text, scene detection, benchmark.
- Removed by owner: YouTube auto publish (files in _unused/youtube_publish_removed/). Upload clips by hand.
- Open (manual, by user): browser check of /gaming-highlights (12.3 boxes stay unticked until checked).
- Known: speech_music_test.py upload step uses the wrong form field (should be `files`), so it falls back to the newest library video.

## FINAL: ALL PHASES COMPLETE (2026-11-21)
- Open items: none. Optional future ideas (Phase 14): moving face-tracking reframe, drag-and-drop timeline, live music preview.
