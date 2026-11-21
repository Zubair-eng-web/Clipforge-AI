# CLIPFORGE AI real test checklist (Phase 12.12)

Use ONE short video (2-5 minutes, with speech, ideally gameplay) and your own music file.
Tick each box only when you saw it work. Write what went wrong next to a failed item and send it to me.
Before you start: `.\scripts\start-all.ps1`, Gemini key set (Gemini API Key page), Performance page: Low-memory mode ON.
Keep a copy of your original video: after the whole test, its size must be unchanged (originals are never modified).

## A. 12.3 AI Gaming Highlights (real test)
- [ ] A1 Pick the video, tick 3 categories (for example fighting, shooting, car chase), press Find Gaming Highlights. Progress bar moves, no error.
- [ ] A2 Cards appear: thumbnail, category, start/end, duration, description, confidence, Detected/Uncertain.
- [ ] A3 Preview plays exactly the range of the card, then stops.
- [ ] A4 Extract Clip works for one card, a clip shows in Generated Clips and plays. Its length is close to the card.
- [ ] A5 Select 2 cards, Extract selected, both clips appear.
- [ ] A6 Turn "Look at video frames" off and run again: scenes are Uncertain (expected, audio and speech only).

## B. 10.4 Scene Detection (real test)
- [ ] B1 Pick 2 categories (for example comedy, romantic), Complete Scene (Automatic), Generate. Scenes appear.
- [ ] B2 Fixed length (1 minute): clips are not longer than the chosen length and are not padded with unrelated footage.
- [ ] B3 Custom category with your own text finds something sensible (or nothing, which is fine).
- [ ] B4 Run the same categories again: no duplicate scenes of the same category.
- [ ] B5 "Preview before extraction" only finds scenes (no clips). Extract one by hand afterwards.
- [ ] B6 Adjust start/end of an unextracted scene, then extract: the clip follows your times.
- [ ] B7 Remove the Gemini key (Gemini API Key page, Remove, or wrong key) and run: result is Uncertain with a warning, no crash. Put the key back after.
- [ ] B8 Export ZIP contains the category folders.

## C. 11.5 Custom Music and Audio Studio (real test)
- [ ] C1 Music Library: upload your own audio, add a folder and tags (epic, soft). Waveform shows.
- [ ] C2 Audio Studio: pick a clip, add the track, set volume 50 percent, Preview (20 s) plays with music.
- [ ] C3 Original audio OFF: only music is heard. Original ON: both.
- [ ] C4 Trim, fade in/out and loop (use a track shorter than the clip) all audible as set.
- [ ] C5 Export MP4: new clip in Generated Clips, same picture, same length, plays.
- [ ] C6 Suggest from my library: only tracks from YOUR library are shown, nothing is applied without your click.
- [ ] C7 "Add Music" buttons open Audio Studio from Scene Detection, Generated Clips, Manual Clipper, Video Editor.

## D. Full workflow (16 points)
- [ ] D1 Upload the video (Upload Videos). It appears in Video Library and plays.
- [ ] D2 AI Highlights: Analyze (language auto or your language). Transcript, scenes and highlights show.
- [ ] D3 AI Auto Clipper: make 3 clips. They appear and play.
- [ ] D4 Manual Clipper: make one clip with I/O keys (accurate) and one in fast mode.
- [ ] D5 Gaming Highlights to Extract Clip (same as A4).
- [ ] D6 Reels Studio: one reel, Auto range, 30 s, Instagram preset. Result is 9:16.
- [ ] D7 Reels Studio: Manual range using the "= player time" buttons.
- [ ] D8 Reels Studio: "Make several reels" from a clip of 60 s or more with length 15 or 30. All parts are made.
- [ ] D9 Reels Studio: choose a length above the platform limit. A red message shows and the button is disabled.
- [ ] D10 Captions Studio: generate captions on a clip with speech, pick the Gaming preset, preview, burn. NEW clip has captions.
- [ ] D11 Social Text: generate text for a clip, edit it and approve.
- [ ] D12 Thumbnail Studio: AI suggestion, add text, save and download PNG.
- [ ] D13 Timeline Editor: 2 segments + transition, render, then text overlay + music, apply. Undo and redo (Ctrl+Z, Ctrl+Y) work.
- [ ] D14 Batch Processing: 2 videos with reels and captions ticked. Progress per video, Cancel and Retry buttons work.
- [ ] D15 Reels Library, Clips Gallery, History/Queue, Storage Manager and Performance pages open and show real numbers. Cleanup buttons work.
- [ ] D16 Originals untouched: the size of the original video file is the same as before the test, and the old tests still pass (`.\.venv\Scripts\python.exe -m pytest -q`).

## Results
Write here: PC RAM, Whisper model, total time of the analysis, anything that failed.