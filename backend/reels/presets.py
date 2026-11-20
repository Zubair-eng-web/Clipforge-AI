"""Reel platform presets. Platform limits change over time: edit max_sec here if a platform changes its rules."""
PLATFORMS = {
    "youtube_shorts": {"label": "YouTube Shorts", "ratio": "9:16", "max_sec": 180},
    "instagram_reels": {"label": "Instagram Reels", "ratio": "9:16", "max_sec": 90},
    "facebook_reels": {"label": "Facebook Reels", "ratio": "9:16", "max_sec": 90},
    "tiktok": {"label": "TikTok-compatible", "ratio": "9:16", "max_sec": 180},
    "square": {"label": "Square 1:1", "ratio": "1:1", "max_sec": 600},
    "landscape": {"label": "Landscape 16:9", "ratio": "16:9", "max_sec": 3600},
    "custom": {"label": "Custom", "ratio": "9:16", "max_sec": 600},
}
DURATIONS = [15, 30, 45, 60, 90, 180]
SIZES = {
    "1080": {"9:16": (1080, 1920), "1:1": (1080, 1080), "16:9": (1920, 1080)},
    "720": {"9:16": (720, 1280), "1:1": (720, 720), "16:9": (1280, 720)},
}
MODES = ("face", "center", "blur", "manual")


def check_target(platform, seconds):
    """Returns (ok, message). Seconds above the platform limit are refused."""
    info = PLATFORMS.get(platform)
    if info is None:
        return False, f"Unknown platform: {platform}"
    if seconds is not None and seconds > info["max_sec"] + 1e-6:
        return False, f"{info['label']} allows at most {info['max_sec']} seconds (asked {seconds:g})"
    return True, ""