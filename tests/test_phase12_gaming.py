import shutil, subprocess
import pytest
from backend.gaming import GAMING_CATEGORIES, get_categories, classify_unit, best_categories
from backend.gaming import audio_energy_profile, summarize_audio

LOUD = {"mean": 0.9, "peak": 1.0, "dynamic": 0.3, "available": True}
QUIET = {"mean": 0.1, "peak": 0.2, "dynamic": 0.1, "available": True}

def test_25_unique_categories_and_custom():
    ids = [c["id"] for c in GAMING_CATEGORIES]
    assert len(ids) == 25 and len(set(ids)) == 25
    assert get_categories("monster truck")[-1]["id"] == "custom"

def test_police_chase_needs_police_cues():
    with_police = classify_unit("police siren wanted chase", ["police car"], LOUD, {"police_chase": 80, "car_chase": 80})
    assert with_police["police_chase"]["status"] == "detected"
    assert with_police["police_chase"]["score"] > with_police["car_chase"]["score"]
    no_police = classify_unit("chase him go go", ["red car"], LOUD, {"police_chase": 80, "car_chase": 80})
    assert no_police["police_chase"]["status"] != "detected"
    assert no_police["car_chase"]["status"] == "detected"

def test_fight_vs_gunfight():
    gun = classify_unit("shoot him gun reload", ["pistol"], LOUD, {"fighting": 80, "shooting": 80})
    assert gun["shooting"]["score"] > gun["fighting"]["score"]
    fist = classify_unit("fight punch kick", ["two men"], LOUD, {"fighting": 80, "shooting": 80})
    assert fist["fighting"]["status"] == "detected"
    assert fist["shooting"]["status"] != "detected"

def test_one_signal_alone_is_not_detected():
    only_vision = classify_unit("", [], None, {"explosions": 100})
    assert only_vision["explosions"]["status"] != "detected"
    two = classify_unit("", [], LOUD, {"explosions": 100})
    assert two["explosions"]["status"] == "detected"

def test_silent_gameplay_has_no_fake_text_signal():
    r = classify_unit("", [], QUIET, {"scenery": 90})
    assert "text" not in r["scenery"]["signals"]

def test_best_categories_sorted():
    r = classify_unit("explosion boom bomb", ["fire"], LOUD, {"explosions": 90})
    assert best_categories(r)[0]["category"] == "explosions"

@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg missing")
def test_audio_energy_real_ffmpeg(tmp_path):
    def make(name, vol):
        f = tmp_path / name
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration=3,volume={vol}", str(f)], check=True)
        return f
    loud = summarize_audio(audio_energy_profile(make("loud.wav", 4)))
    quiet = summarize_audio(audio_energy_profile(make("quiet.wav", 0.02)))
    assert loud["available"] and loud["mean"] > quiet["mean"] + 0.3