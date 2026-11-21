"""Timeline engine (Phase 12.8a): joins segments (clip, start, end) with optional transitions.
Source files are never modified. One re-encode. Silent segments get silence."""
from backend.editor.ops import _ENC, has_audio
from backend.video_processing.ffmpeg_service import _run

FPS = 30
TRANSITIONS = ("none", "fade", "fadeblack", "dissolve", "wipeleft", "slideleft", "circleopen")
_A = "aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo"


def build_timeline(segs, dst, w, h, transition="none", tsec=0.5, on_progress=None) -> float:
    """segs: list of {path, start, end}. Returns the output length in seconds."""
    n = len(segs)
    if n < 1:
        raise ValueError("Need at least one segment")
    if transition not in TRANSITIONS:
        raise ValueError(f"Unknown transition: {transition}")
    w, h = int(w) - int(w) % 2, int(h) - int(h) % 2
    use_x = transition != "none" and n > 1
    t = float(tsec) if use_x else 0.0
    inputs, parts, durs = [], [], []
    for i, s in enumerate(segs):
        st, en = float(s["start"]), float(s["end"])
        d = en - st
        if d < 0.3:
            raise ValueError("Each segment must be at least 0.3 seconds long")
        if use_x and d < 2 * t - 1e-6:
            raise ValueError(f"Segment {i + 1} is too short for a {t:g}s transition (needs {2 * t:g}s)")
        durs.append(d)
        inputs += ["-i", str(s["path"])]
        parts.append(
            f"[{i}:v]trim=start={st:.3f}:end={en:.3f},setpts=PTS-STARTPTS,"
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={FPS},format=yuv420p[v{i}]")
        if has_audio(s["path"]):
            parts.append(f"[{i}:a:0]atrim=start={st:.3f}:end={en:.3f},asetpts=PTS-STARTPTS,{_A},"
                         f"apad=whole_dur={d:.3f}[a{i}]")
        else:
            parts.append(f"anullsrc=r=44100:cl=stereo:d={d:.3f},{_A}[a{i}]")
    if n == 1:
        vl, al, total = "[v0]", "[a0]", durs[0]
    elif not use_x:
        join = "".join(f"[v{i}][a{i}]" for i in range(n))
        parts.append(f"{join}concat=n={n}:v=1:a=1[v][a]")
        vl, al, total = "[v]", "[a]", float(sum(durs))
    else:
        cum, pv, pa = durs[0], "[v0]", "[a0]"
        for k in range(1, n):
            parts.append(f"{pv}[v{k}]xfade=transition={transition}:duration={t:.3f}:offset={cum - t:.3f}[x{k}]")
            parts.append(f"{pa}[a{k}]acrossfade=d={t:.3f}[y{k}]")
            cum = cum + durs[k] - t
            pv, pa = f"[x{k}]", f"[y{k}]"
        vl, al, total = pv, pa, cum
    args = [*inputs, "-filter_complex", ";".join(parts), "-map", vl, "-map", al, *_ENC, str(dst)]
    _run(args, total, on_progress)
    return total
