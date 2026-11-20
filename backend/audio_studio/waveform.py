"""Small waveform (peaks 0..1) made by streaming 8 kHz mono audio from FFmpeg. Uses very little RAM."""
import shutil
import subprocess
from array import array

from backend.video_processing.ffmpeg_service import _NO_WINDOW


def compute_peaks(path, duration, bins=240):
    exe = shutil.which("ffmpeg")
    if not exe:
        return []
    total = max(int((duration or 1.0) * 8000), 1)
    per = max(total // bins, 1)
    cmd = [exe, "-v", "error", "-nostdin", "-i", str(path), "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "pipe:1"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)
    peaks = []
    try:
        while True:
            data = proc.stdout.read(per * 2)
            if not data:
                break
            a = array("h")
            a.frombytes(data[: len(data) // 2 * 2])
            if a:
                peaks.append(max(max(a), -min(a)) / 32768.0)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    peaks = peaks[:bins]
    m = max(peaks) if peaks else 0.0
    return [round(p / m, 3) for p in peaks] if m > 0 else peaks