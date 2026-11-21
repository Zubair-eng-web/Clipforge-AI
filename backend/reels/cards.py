"""Intro / outro text cards for reels (Phase 12.5b). Card = image -> short MP4 (30 fps, silent stereo audio),
then joined with the reel by FFmpeg. The reel's own picture is never changed, only re-encoded once."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from backend.video_processing.ffmpeg_service import _exe, _run

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FPS = 30
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _rgb(h, default):
    h = h if isinstance(h, str) and _HEX.match(h) else default
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _has_audio(path) -> bool:
    r = subprocess.run([_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=_NO_WINDOW)
    return "Audio:" in (r.stderr or "")


def _render_pil(path, text, w, h, bg, fg):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (w, h), bg)
    d = ImageDraw.Draw(img)
    size = max(20, int(min(w, h) * 0.085))
    font = None
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(name, size)
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()
    maxw = int(w * 0.86)
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if cur and d.textlength(t, font=font) > maxw:
            lines.append(cur)
            cur = word
        else:
            cur = t
    if cur:
        lines.append(cur)
    lh = int(size * 1.35)
    y = (h - lh * len(lines)) / 2
    for ln in lines:
        tw = d.textlength(ln, font=font)
        d.text(((w - tw) / 2, y), ln, font=font, fill=fg)
        y += lh
    img.save(str(path), "PNG")


def _render_cv(path, text, w, h, bg, fg):
    import cv2
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = (bg[2], bg[1], bg[0])
    text = "".join(ch if ord(ch) < 128 else "?" for ch in text)
    scale = max(0.6, min(w, h) / 500.0)
    th = max(1, int(scale * 2))
    maxw = int(w * 0.86)
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if cur and cv2.getTextSize(t, cv2.FONT_HERSHEY_SIMPLEX, scale, th)[0][0] > maxw:
            lines.append(cur)
            cur = word
        else:
            cur = t
    if cur:
        lines.append(cur)
    lh = int(scale * 45)
    y = int((h - lh * len(lines)) / 2 + lh * 0.7)
    for ln in lines:
        tw = cv2.getTextSize(ln, cv2.FONT_HERSHEY_SIMPLEX, scale, th)[0][0]
        cv2.putText(img, ln, (int((w - tw) / 2), y), cv2.FONT_HERSHEY_SIMPLEX, scale, (fg[2], fg[1], fg[0]), th, cv2.LINE_AA)
        y += lh
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("Could not draw the card")
    Path(path).write_bytes(buf.tobytes())


def render_card(path, text, w, h, bg="#111827", fg="#ffffff"):
    bgc, fgc = _rgb(bg, "#111827"), _rgb(fg, "#ffffff")
    text = str(text).strip()[:80]
    try:
        _render_pil(path, text, w, h, bgc, fgc)
    except ImportError:
        _render_cv(path, text, w, h, bgc, fgc)


def _card_video(png, out, secs, w, h):
    _run(["-loop", "1", "-framerate", str(FPS), "-i", str(png), "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
          "-t", f"{secs:.3f}", "-vf", f"scale={w}:{h},setsar=1,format=yuv420p",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-r", str(FPS),
          "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out)], secs)


def add_cards(main, dst, main_dur, w, h, intro=None, outro=None, on_progress=None) -> float:
    """Joins [intro card] + main + [outro card] into dst. Returns the total length in seconds."""
    main, dst = Path(main), Path(dst)
    tmp = Path(tempfile.mkdtemp(prefix="cards_"))
    try:
        segs, total = [], 0.0
        for name, c in (("intro", intro), ("main", None), ("outro", outro)):
            if name == "main":
                segs.append(("main", main, float(main_dur)))
                total += float(main_dur)
                continue
            if not c or not str(c.get("text", "")).strip():
                continue
            secs = min(max(float(c.get("seconds", 2) or 2), 1.0), 5.0)
            png, vid = tmp / f"{name}.png", tmp / f"{name}.mp4"
            render_card(png, c["text"], w, h, c.get("bg", "#111827"), c.get("fg", "#ffffff"))
            _card_video(png, vid, secs, w, h)
            segs.append((name, vid, secs))
            total += secs
        args, vparts, aparts, idx = [], [], [], 0
        for k, (_name, p, dur) in enumerate(segs):
            args += ["-i", str(p)]
            vi = idx
            idx += 1
            vparts.append(f"[{vi}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                          f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS},format=yuv420p[v{k}]")
            if _has_audio(p):
                aparts.append((k, f"[{vi}:a]"))
            else:
                args += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
                aparts.append((k, f"[{idx}:a]"))
                idx += 1
        fc = ";".join(vparts)
        for vi, ref in aparts:
            fc += f";{ref}aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{vi}]"
        n = len(segs)
        join = "".join(f"[v{i}][a{i}]" for i in range(n))
        fc += f";{join}concat=n={n}:v=1:a=1[v][a]"
        args += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
                 "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(dst)]
        _run(args, total, on_progress)
        return total
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
