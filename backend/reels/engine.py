"""Reels engine (Phase 12.5): ready clip -> platform-ready reel.
Steps: pick the segment (most active audio window + dead-time trim) -> reframe (face/center/blur/manual)
-> optional colour tweak -> ONE x264 encode -> optional music mix (video stream copied).
The source file is never modified."""
import math
import subprocess
from pathlib import Path

import numpy as np

from backend.audio_studio.mix import mix_audio
from backend.reels.cards import add_cards
from backend.reels.presets import SIZES
from backend.reframing.reframe import compute_crop, detect_face_center
from backend.video_processing.ffmpeg_service import _exe, _run

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_ENC = [
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
]


def has_audio(path) -> bool:
    r = subprocess.run([_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=_NO_WINDOW)
    return "Audio:" in (r.stderr or "")


def audio_energy(src, limit_sec=None):
    """RMS loudness per second (8 kHz mono, streamed: low RAM). None = no audio."""
    cmd = [_exe(), "-hide_banner", "-nostdin", "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "8000"]
    if limit_sec:
        cmd += ["-t", f"{float(limit_sec):.3f}"]
    cmd += ["-f", "s16le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)
    out = []
    try:
        while True:
            buf = proc.stdout.read(16000)  # 1 second
            if not buf or len(buf) < 8000:
                break
            x = np.frombuffer(buf[: len(buf) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768.0
            out.append(float(np.sqrt(np.mean(x * x))))
    finally:
        if proc.poll() is None:
            proc.kill()
        try:
            proc.stdout.close()
        except Exception:
            pass
        proc.wait()
    return out or None


def _trim_dead(s, e, en, min_len):
    """Cuts up to 3 s of near-silence at the start and 2 s at the end."""
    if not en:
        return s, e
    thr = 0.12 * max(en)
    if thr <= 0:
        return s, e
    moved = 0
    while moved < 3 and e - s - 1 >= min_len and int(s) < len(en) and en[int(s)] < thr:
        s += 1.0
        moved += 1
    moved = 0
    while moved < 2 and e - s - 1 >= min_len:
        i = int(math.ceil(e)) - 1
        if i < 0 or i >= len(en) or en[i] >= thr:
            break
        e = float(i)
        moved += 1
    return s, e


def choose_window(duration, energy, target=None, trim_dead=True, min_len=3.0):
    """Returns (start, end) in seconds. Longer than target -> most active window; no audio -> first seconds."""
    duration = float(duration)
    if not target or target >= duration - 0.05:
        s, e = 0.0, duration
    else:
        s = 0.0
        if energy:
            k = min(max(1, int(round(target))), len(energy))
            run = sum(energy[:k])
            best, bi = run, 0
            for i in range(1, len(energy) - k + 1):
                run += energy[i + k - 1] - energy[i - 1]
                if run > best:
                    best, bi = run, i
            s = float(bi)
        e = min(duration, s + float(target))
        s = max(0.0, e - float(target))
    if trim_dead and energy:
        s, e = _trim_dead(s, e, energy, min(min_len, e - s))
    return round(s, 3), round(e, 3)


def _eq(brightness, contrast, saturation):
    if abs(brightness) < 1e-3 and abs(contrast - 1) < 1e-3 and abs(saturation - 1) < 1e-3:
        return ""
    return f"eq=brightness={brightness:.3f}:contrast={contrast:.3f}:saturation={saturation:.3f}"


def build_reel(src, dst, *, src_duration, w, h, ratio="9:16", size="1080", mode="face", cx=None, cy=None,
               target_sec=None, trim_dead=True, start=None, end=None, brightness=0.0, contrast=1.0,
               saturation=1.0, music=None, orig_on=True, orig_volume=1.0, on_progress=None,
               intro=None, outro=None) -> dict:
    """Writes the reel MP4 to dst. cx/cy (0..1) = wanted crop center for mode 'manual'.
    music = list of track dicts (path, tdur, volume, start, trim_in, trim_out, fade_in, fade_out, loop)."""
    src, dst = Path(src), Path(dst)
    ow, oh = SIZES[size][ratio]
    if start is not None and end is not None:
        s = max(0.0, float(start))
        e = min(float(end), float(src_duration))
        if e - s < 1.0:
            raise ValueError("Reel must be at least 1 second long")
    else:
        energy = audio_energy(src, float(src_duration) + 1.0) if (target_sec or trim_dead) else None
        s, e = choose_window(src_duration, energy, target_sec, trim_dead)
    dur = e - s
    if dur < 1.0:
        raise ValueError("Reel must be at least 1 second long")

    def prog(base, span):
        return (lambda p: on_progress(base + p * span)) if on_progress else None

    used = mode
    eq = _eq(brightness, contrast, saturation)
    if mode == "blur":
        bw, bh = max(2, (ow // 4) // 2 * 2), max(2, (oh // 4) // 2 * 2)
        fc = (
            f"[0:v]split=2[a][b];"
            f"[a]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},boxblur=8:2,scale={ow}:{oh}[bg];"
            f"[b]scale={ow}:{oh}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1" + (f",{eq}" if eq else "") + "[v]"
        )
        body = ["-filter_complex", fc, "-map", "[v]"]
    else:
        fx = fy = None
        if mode == "manual":
            fx = (0.5 if cx is None else float(cx)) * w
            fy = (0.5 if cy is None else float(cy)) * h
        elif mode == "face":
            found = detect_face_center(src, src_duration)
            if found:
                fx, fy = found
            else:
                used = "center"
        cw, ch, x, y = compute_crop(int(w), int(h), ratio, fx, fy)
        vf = f"crop={cw}:{ch}:{x}:{y},scale={ow}:{oh}:flags=lanczos,setsar=1" + (f",{eq}" if eq else "")
        body = ["-vf", vf, "-map", "0:v:0"]

    cards = [c for c in (intro, outro) if c and str(c.get("text", "")).strip()]
    pre = dst.with_name(dst.stem + "_pre.mp4")
    wrapped = dst.with_name(dst.stem + "_cards.mp4")
    staged = bool(music or cards)
    total = dur
    try:
        args = ["-ss", f"{s:.3f}", "-i", str(src), "-t", f"{dur:.3f}", *body, "-map", "0:a:0?", *_ENC,
                str(pre if staged else dst)]
        _run(args, dur, prog(0.0, 0.6 if staged else 0.97))
        cur = pre
        if cards:
            cur = wrapped if music else dst
            total = add_cards(pre, cur, dur, ow, oh, intro, outro, on_progress=prog(0.6, 0.2))
        if music:
            mix_audio(cur, dst, total, has_audio(cur), orig_on, orig_volume, music, on_progress=prog(0.8, 0.17))
    finally:
        pre.unlink(missing_ok=True)
        wrapped.unlink(missing_ok=True)
    return {"start": s, "end": e, "duration": total, "mode_used": used, "music": bool(music),
            "intro": bool(intro and str(intro.get("text", "")).strip()),
            "outro": bool(outro and str(outro.get("text", "")).strip()),
            "width": ow, "height": oh}
