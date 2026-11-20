"""Audio energy signal (FFmpeg, streamed 1 second at a time = low RAM, no numpy)."""
import math, shutil, subprocess
from array import array

def _ffmpeg():
    return shutil.which("ffmpeg") or "ffmpeg"

def audio_energy_profile(path, start=0.0, duration=None, window=1.0, ref=0.25, timeout=600):
    """Return list of 0..1 loudness values, one per `window` seconds. [] if no audio / ffmpeg error."""
    rate = 8000
    cmd = [_ffmpeg(), "-v", "error", "-ss", str(max(0.0, float(start)))]
    if duration:
        cmd += ["-t", str(float(duration))]
    cmd += ["-i", str(path), "-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"]
    chunk = int(rate * window) * 2
    out = []
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except OSError:
        return []
    try:
        while True:
            buf = p.stdout.read(chunk)
            if not buf or len(buf) < 2:
                break
            if len(buf) % 2:
                buf = buf[:-1]
            a = array("h")
            a.frombytes(buf)
            ms = sum(x * x for x in a) / len(a)
            out.append(min(1.0, (math.sqrt(ms) / 32768.0) / ref))
    finally:
        try:
            p.stdout.close()
            p.wait(timeout=timeout)
        except Exception:
            p.kill()
    return out

def summarize_audio(profile):
    if not profile:
        return {"mean": 0.0, "peak": 0.0, "dynamic": 0.0, "available": False}
    mean = sum(profile) / len(profile)
    var = sum((x - mean) ** 2 for x in profile) / len(profile)
    return {"mean": mean, "peak": max(profile), "dynamic": min(1.0, math.sqrt(var) * 2), "available": True}