"""AI reframing: convert a clip to 9:16 / 1:1 / 16:9 (face-aware crop, center crop, or blurred-background fit)."""
import statistics

from backend.video_processing.ffmpeg_service import _run

RATIOS = {"9:16": (720, 1280), "1:1": (720, 720), "16:9": (1280, 720)}
MODES = ("face", "center", "blur")
_ENC = [
    "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
]


def compute_crop(w, h, ratio, cx=None, cy=None):
    """Largest crop box with the target aspect ratio. (cx, cy) = wanted center (e.g. a face); None = frame center."""
    tw, th = RATIOS[ratio]
    target = tw / th
    if w / h > target:
        cw, ch = int(round(h * target)), h
    else:
        cw, ch = w, int(round(w / target))
    cw = min(cw, w)
    ch = min(ch, h)
    cw = max(2, cw - cw % 2)
    ch = max(2, ch - ch % 2)
    x = (w - cw) / 2 if cx is None else cx - cw / 2
    y = (h - ch) / 2 if cy is None else cy - ch / 2
    x = int(min(max(x, 0), w - cw))
    y = int(min(max(y, 0), h - ch))
    return cw, ch, x, y


def _detect_face_center(src, duration, max_samples=30):
    """Samples ~1 frame per second, finds the biggest face with an OpenCV Haar cascade (CPU, light).
    Returns the median face center (cx, cy) in source pixels, or None if not enough faces were found."""
    try:
        import cv2
    except ImportError:
        return None
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if cascade.empty():
        return None
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        return None
    n = max(1, min(max_samples, int(duration) if duration else 1))
    xs, ys = [], []
    try:
        for i in range(n):
            t = (duration or 1.0) * (i + 0.5) / n
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            fh, fw = frame.shape[:2]
            scale = 480.0 / fw if fw > 480 else 1.0
            small = cv2.resize(frame, (int(fw * scale), int(fh * scale))) if scale != 1.0 else frame
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
            if len(faces) == 0:
                continue
            x, y, bw, bh = max(faces, key=lambda f: int(f[2]) * int(f[3]))
            xs.append((x + bw / 2.0) / scale)
            ys.append((y + bh / 2.0) / scale)
    finally:
        cap.release()
    if len(xs) < max(1, n // 5):
        return None
    return statistics.median(xs), statistics.median(ys)


def reframe_video(src, dst, ratio, mode, duration, w, h, on_progress=None):
    """Writes the reframed MP4 to dst. Returns the mode really used ('face' falls back to 'center')."""
    if ratio not in RATIOS:
        raise ValueError(f"Unknown ratio: {ratio}")
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}")
    ow, oh = RATIOS[ratio]
    used = mode
    if mode == "blur":
        fc = (
            f"[0:v]split=2[a][b];"
            f"[a]scale={ow}:{oh}:force_original_aspect_ratio=increase,crop={ow}:{oh},boxblur=20:2[bg];"
            f"[b]scale={ow}:{oh}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]"
        )
        args = ["-i", str(src), "-filter_complex", fc, "-map", "[v]", "-map", "0:a:0?", *_ENC, str(dst)]
    else:
        cx = cy = None
        if mode == "face":
            found = detect_face_center(src, duration)
            if found:
                cx, cy = found
            else:
                used = "center"
        cw, ch, x, y = compute_crop(w, h, ratio, cx, cy)
        vf = f"crop={cw}:{ch}:{x}:{y},scale={ow}:{oh}:flags=lanczos,setsar=1"
        args = ["-i", str(src), "-vf", vf, "-map", "0:v:0", "-map", "0:a:0?", *_ENC, str(dst)]
    _run(args, duration, on_progress)
    return used


def detect_face_center(src, duration, max_samples=30):
    """Safe wrapper: any OpenCV problem (broken install, missing cascade) simply means 'no face found'."""
    try:
        return _detect_face_center(src, duration, max_samples)
    except Exception:
        return None
