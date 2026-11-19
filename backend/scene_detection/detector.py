"""Scene detection with PySceneDetect (content based, CPU)."""
import os
from typing import Callable, Optional

ProgressCb = Optional[Callable[[float], None]]  # 0.0 .. 1.0


def _seconds(tc) -> float:
    """FrameTimecode -> seconds (works with old get_seconds() and new .seconds)."""
    v = getattr(tc, "seconds", None)
    if v is None:
        return float(tc.get_seconds())
    return float(v() if callable(v) else v)


def _frames(tc) -> int:
    v = getattr(tc, "frame_num", None)
    if v is None:
        return int(tc.get_frames())
    return int(v() if callable(v) else v)


def detect_scenes(src, duration_sec: float = 0.0, on_progress: ProgressCb = None) -> list:
    """Returns [{idx, start, end}] in seconds. A video with no cuts gives one scene."""
    from scenedetect import ContentDetector, SceneManager, open_video

    threshold = float(os.getenv("SCENE_THRESHOLD", "27") or 27)
    video = open_video(str(src))
    try:
        video_seconds = _seconds(video.duration)
    except Exception:
        video_seconds = float(duration_sec or 0.0)
    try:
        total_frames = _frames(video.duration)
    except Exception:
        total_frames = 0

    manager = SceneManager()
    manager.add_detector(ContentDetector(threshold=threshold))

    def cb(_img, pos):
        if not on_progress:
            return
        frac = None
        try:
            if hasattr(pos, "get_seconds") or hasattr(pos, "seconds"):
                if video_seconds > 0:
                    frac = _seconds(pos) / video_seconds
            elif total_frames > 0:
                frac = float(pos) / total_frames
        except Exception:
            frac = None
        if frac is not None:  # called outside try so a cancel (JobCancelled) still stops the job
            on_progress(min(max(frac, 0.0), 1.0))

    manager.detect_scenes(video, callback=cb, show_progress=False)
    scenes = [
        {"idx": i, "start": round(_seconds(s), 3), "end": round(_seconds(e), 3)}
        for i, (s, e) in enumerate(manager.get_scene_list())
    ]
    if not scenes:
        scenes = [{"idx": 0, "start": 0.0, "end": round(video_seconds or float(duration_sec or 0.0), 3)}]
    return scenes