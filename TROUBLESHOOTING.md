# CLIPFORGE AI - Troubleshooting

First step for any problem: start the backend and run `.\scripts\diagnose.ps1`. It lists missing tools, low RAM, low disk and a missing Gemini key.

## FFmpeg or FFprobe not found
- Symptom: upload fails, clip export fails, diagnose shows "FFmpeg not found".
- Fix: install FFmpeg (a full build, with libass), add its `bin` folder to PATH, close and reopen VS Code, then run `ffmpeg -version`.
- Caption burn-in needs an FFmpeg build with libass. If burn fails, install the "full" build.

## Port already in use (8000 or 3000)
- Run `.\scripts\stop-all.ps1`, then start again.
- Still busy: `netstat -ano | findstr :8000`, then `taskkill /PID <number> /F`.

## Gemini errors
| Error | Meaning | What happens |
|---|---|---|
| 403 | key invalid, billing or free tier problem | local fallback scoring is used |
| 429 | quota reached | retried, then local fallback |
| 503 | Gemini is busy | retried, then local fallback |
| no key | `GEMINI_API_KEY` empty | local scoring only |
- Check the key in `.env` and the model name in Google AI Studio. Restart the backend after changing `.env`.
- Analysis never fails only because Gemini is down. It falls back to local scoring.

## YouTube import fails
- Update yt-dlp: `.\.venv\Scripts\python.exe -m pip install -U yt-dlp`
- Only one video per link, max 1080p, length limit `YOUTUBE_MAX_MINUTES` (default 60).
- Private, age-restricted or protected videos cannot be imported.

## Slow analysis or out of RAM (8GB PC)
- Keep `MAX_CONCURRENT_JOBS=1` in `.env`.
- Close the browser tabs and other heavy programs while analysis runs.
- Transcription is the slowest step (CPU only). "Analyze again" reuses the saved transcript.
- Faster but less accurate: `WHISPER_MODEL=base` in `.env`. Better but slower: `small` (default).
- Long videos: use Batch and let it run in the background.

## Preview does not play (MOV, MKV, AVI)
- The app creates a browser preview automatically. Wait for "Preparing a browser preview".
- If it stays stuck: Storage Manager -> "Clear browser previews", then open the video again.

## Face reframing is not following the face
- Face mode uses one fixed crop around the median face position. If no face is found it uses the center.
- OpenCV must be 4.x (`opencv-python-headless<5`). Check with `.\.venv\Scripts\python.exe -c "import cv2; print(cv2.__version__)"`.
- Use `blur` mode when the subject moves a lot.

## Job stuck on "processing" or "Interrupted (server restarted)"
- If the server restarts, running jobs are marked failed. Open History and press Retry.
- A job that never finishes: press Cancel in History, then Retry.

## Disk full
- Storage Manager: clear previews and temporary files, delete failed and cancelled clips, delete orphan files.
- Originals and ready clips are never touched by cleanup.

## Database problems
- File: `storage/clipforge.db` (SQLite WAL, so you may also see `-wal` and `-shm` files; this is normal).
- Back up by copying the `storage` folder while the backend is stopped.

## Tests
- Run all: `.\.venv\Scripts\python.exe -m pytest -q`
- Skipped tests (live Gemini) are normal when Gemini is not reachable.