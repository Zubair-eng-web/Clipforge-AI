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
- [ ] Performance tuning from real timings (Whisper speed, RAM during analysis)

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
- [ ] 10.4 Real video test (fighting, romantic, comedy, multiple categories, fixed 1/3 min, custom, complete scene, duplicates, failed AI)
- [ ] 10.5 README notes + final limitations report
- [ ] Pending from Phase 9: performance timing test (Whisper base, analyze time, peak RAM)
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
- [ ] 11.5 Real test (fighting, romantic, comedy clip + own music; original ON/OFF; mixed; trim; fades; loop; export; playback; old features still work)
- [ ] 11.6 README (install, usage, testing) + final report (modified files, results, limitations)
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
- [~] 12.3 AI Gaming Highlights page (built, real test pending)
  - [ ] Cards: thumbnail, category, start/end, duration, AI description, confidence
  - [ ] Preview, Extract Clip, multi-select batch extract
- [x] 12.4 Captions Studio (real burn test passed)
  - [ ] 8 presets (Gaming, Viral Reels, Cinematic, Bold Highlight, Minimal, Word-by-Word, Karaoke, Custom)
  - [ ] Customization (font, size, colors, outline, shadow, position, alignment, line spacing, words per line, timing, animation)
  - [ ] Word-by-word highlight (ASS karaoke), manual correction, language choice (Whisper)
  - [ ] Export SRT, VTT, burned MP4, separate subtitle files; caption preview before export
  - [ ] Manual text overlays for gameplay without speech
- [~] 12.5 Reels and Shorts backend (done except intro/outro 12.5b)
  - [x] Platform presets (YouTube Shorts, Instagram, Facebook, TikTok-compatible), formats 9:16, 1:1, 16:9, 1080x1920
  - [x] Durations 15/30/45/60/90 s, 3 min, custom (respect platform limits)
  - [x] AI reel pipeline: most active audio window, dead-time trim, reframe, optional music, thumbnail, MP4 (captions: use Captions Studio on the reel clip)
  - [x] Manual crop/reposition (cx, cy), start/end change, brightness/contrast/saturation
  - [ ] Intro/outro (12.5b)
- [x] 12.6 Reels Studio UI (page /reels, real reel test passed)
- [ ] 12.7 Social text generator
  - [ ] Title, description, caption, hashtags, keywords, CTA, pinned comment
  - [ ] Tones (viral, funny, cinematic, professional, suspenseful, minimal); text based on real video content; user edits and approves
- [ ] 12.8 Video Editor upgrade
  - [ ] Video, audio and caption timelines, multiple audio tracks
  - [ ] Text overlays, trim, split, clip arrangement, transitions, undo/redo
- [ ] 12.9 Thumbnail Studio upgrade (AI suggestions, platforms, crop, background effects, PNG/JPG)
- [ ] 12.10 Batch Processing upgrade (multi-video analyze, highlights, reels, caption style and music for many clips, progress/cancel/retry)
- [ ] 12.11 Performance (8GB RAM, low-memory sampling, lower-resolution analysis option) + cleanup for new folders
- [ ] 12.12 Full workflow test (16-point list from spec) + old pending tests (10.4, 11.5) + regression (all old tests pass)
- [ ] 12.13 README update + final report (modified files, test results, limitations)

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
- Done: Phase 1 to 9, 10.1-10.3, 11.1-11.4, 12.0 to 12.2, 12.5 (backend, no intro/outro)
- Built, test pending: 12.3 AI Gaming Highlights page
- Done: 12.4 Captions Studio
- Done: 12.6 Reels Studio UI
- Next: 12.7 Social text generator
- Pending real tests: 9 (performance), 10.4, 11.5 (all in 12.12)

### Phase 12.5 Notes: Reels and Shorts backend
- Files: `backend/reels/` (presets.py, engine.py), `backend/workers/reel_handlers.py` (job `reel_create`), `backend/api/reels_studio.py`. Tests: `tests/test_phase12_reels.py` (real generated video, checks size, duration, codec, source untouched).
- Endpoints: `GET /api/reels-studio/platforms`, `POST /api/reels-studio/create` (clip_id, platform, ratio, size 1080|720, mode face|center|blur|manual, cx, cy, target_sec, start_sec+end_sec, trim_dead_time, brightness, contrast, saturation, music[], original_audio_on, original_volume, title).
- Flow: ready clip -> segment (longer than target: most active audio window; dead time at start/end trimmed; no audio: first seconds) -> reframe -> ONE x264 encode -> optional music mix (video copied) -> thumbnail. Result is a NEW clip in `storage/edited_clips/` (also in Generated Clips, so Captions Studio and Audio Studio work on it). A row in `reels` is saved when the columns match.
- Platform limits are in `backend/reels/presets.py` (check the current rules of each platform and edit there). A target above the platform limit is refused.
- Limits: segment choice uses audio loudness only (no meaning of the scene), so check start/end by hand for important reels. Face mode = fixed crop (no moving camera). Intro/outro not yet. Music only from your own library.
