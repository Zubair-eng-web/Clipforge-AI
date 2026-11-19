"""Scene detection with PySceneDetect (ContentDetector, CPU)."""
import logging
from pathlib import Path

log = logging.getLogger("clipforge.scenes")


def _sec(t) -> float:
    v = getattr(t, "seconds", None)
    if v is None:
        return float(t.get_seconds())
    return float(v() if callable(v) else v)


def detect_scenes(path: Path, threshold: float = 27.0, min_scene_len_sec: float = 1.0) -> list:
    """Return [{"index", "start", "end"}] in seconds. Empty list if no cuts or library missing."""
    try:
        from scenedetect import SceneManager, open_video
        from scenedetect.detectors import ContentDetector
    except ImportError:
        log.warning("scenedetect is not installed - skipping scene detection")
        return []

    video = open_video(str(path))
    fps = video.frame_rate or 25.0
    manager = SceneManager()
    manager.add_detector(
        ContentDetector(threshold=threshold, min_scene_len=max(int(fps * min_scene_len_sec), 1))
    )
    manager.detect_scenes(video, show_progress=False)
    scenes = manager.get_scene_list()
    return [
        {"index": i, "start": round(_sec(s), 2), "end": round(_sec(e), 2)}
        for i, (s, e) in enumerate(scenes)
    ]