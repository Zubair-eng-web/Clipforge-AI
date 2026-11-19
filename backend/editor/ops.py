"""Video editor operations: single-clip edits (trim, speed, volume, fades, color, flip) and merging clips."""
import shutil
import subprocess

from backend.reframing.reframe import RATIOS
from backend.video_processing.ffmpeg_service import _NO_WINDOW, _run

_ENC = [
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
]


def has_audio(path) -> bool:
    exe = shutil.which("ffprobe")
    if not exe:
        return False
    try:
        r = subprocess.run(
            [exe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return False
    return r.returncode == 0 and "audio" in r.stdout


def edit_clip_file(src, dst, start, end, ops, on_progress=None) -> float:
    """Writes the edited MP4 to dst. start/end are seconds inside src. Returns the output duration."""
    dur = float(end) - float(start)
    if dur <= 0:
        raise ValueError("end must be greater than start")
    speed = float(ops.get("speed", 1.0))
    volume = float(ops.get("volume", 1.0))
    mute = bool(ops.get("mute", False))
    fade = float(ops.get("fade", 0.0))
    b = float(ops.get("brightness", 0.0))
    c = float(ops.get("contrast", 1.0))
    s = float(ops.get("saturation", 1.0))
    audio = has_audio(src) and not mute
    out_dur = dur / speed
    f = min(fade, out_dur / 2) if fade > 0 else 0.0

    vf = ["scale=trunc(iw/2)*2:trunc(ih/2)*2"]
    if ops.get("flip_h"):
        vf.append("hflip")
    if abs(b) > 1e-6 or abs(c - 1.0) > 1e-6 or abs(s - 1.0) > 1e-6:
        vf.append(f"eq=brightness={b:.3f}:contrast={c:.3f}:saturation={s:.3f}")
    if abs(speed - 1.0) > 1e-6:
        vf.append(f"setpts=PTS/{speed:.4f}")
    if f > 0.05:
        vf += [f"fade=t=in:st=0:d={f:.2f}", f"fade=t=out:st={max(out_dur - f, 0):.2f}:d={f:.2f}"]

    # -ss / -t before -i = input options, so the cut is taken from the source before the speed change
    args = ["-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(src), "-vf", ",".join(vf), "-map", "0:v:0"]
    if audio:
        af = []
        if abs(speed - 1.0) > 1e-6:
            af.append(f"atempo={speed:.4f}")
        if abs(volume - 1.0) > 1e-6:
            af.append(f"volume={volume:.3f}")
        if f > 0.05:
            af += [f"afade=t=in:st=0:d={f:.2f}", f"afade=t=out:st={max(out_dur - f, 0):.2f}:d={f:.2f}"]
        if af:
            args += ["-af", ",".join(af)]
        args += ["-map", "0:a:0"]
    else:
        args += ["-an"]
    args += [*_ENC, str(dst)]
    _run(args, out_dur, on_progress)
    return out_dur


def merge_clips_files(paths, durations, dst, ratio="first", first_size=None, on_progress=None) -> float:
    """Joins clips one after another. ratio: 'first' (size of the first clip) or 9:16 / 1:1 / 16:9."""
    if len(paths) < 2:
        raise ValueError("Need at least two clips to merge")
    if ratio == "first":
        if not first_size:
            raise ValueError("first_size is required for ratio 'first'")
        w, h = first_size
    else:
        w, h = RATIOS[ratio]
    w, h = int(w) - int(w) % 2, int(h) - int(h) % 2
    inputs, parts, labels = [], [], []
    for i, (p, d) in enumerate(zip(paths, durations)):
        inputs += ["-i", str(p)]
        parts.append(
            f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=30,format=yuv420p[v{i}]"
        )
        if has_audio(p):
            parts.append(f"[{i}:a:0]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
        else:
            parts.append(f"anullsrc=r=44100:cl=stereo:d={float(d):.3f},aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    fc = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(paths)}:v=1:a=1[v][a]"
    total = float(sum(durations))
    args = [*inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[a]", *_ENC, str(dst)]
    _run(args, total, on_progress)
    return total