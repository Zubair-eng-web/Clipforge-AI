import hashlib
import json
import re
import shutil
import subprocess
import time

import pytest

from backend import config
from backend.audio_studio import mix
from backend.database.db import SessionLocal
from backend.database.models import Clip, Video
from backend.video_processing import ffmpeg_service
from backend.video_processing.ffprobe import probe


def _t(**kw):
    d = {"path": "m.wav", "tdur": 4.0, "volume": 0.6, "start": 0.0, "trim_in": 0.0, "trim_out": None,
         "fade_in": 0.0, "fade_out": 0.0, "loop": False}
    d.update(kw)
    return d


def test_build_filter_rules():
    inputs, fc, n = mix.build_filter(10, True, True, 1.0, [_t(loop=True)])
    assert "-stream_loop" in inputs and n == 2 and "amix=inputs=2" in fc and "normalize=0" in fc
    with pytest.raises(ValueError):
        mix.build_filter(10, True, False, 1.0, [_t(start=20)])
    with pytest.raises(ValueError):
        mix.build_filter(10, True, True, 1.0, [])  # original only, no music: nothing to mix
    inputs, fc, n = mix.build_filter(10, True, False, 1.0, [_t(trim_in=1, trim_out=3, loop=True, fade_in=0.5, fade_out=0.5, start=2)])
    assert n == 1 and "aloop" in fc and "afade=t=in" in fc and "afade=t=out" in fc and "adelay=2000|2000" in fc
    assert "-stream_loop" not in inputs


def _exe():
    try:
        return ffmpeg_service._exe()
    except Exception:
        pytest.skip("ffmpeg not available")


def _wait(client, job_id, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("completed", "failed", "cancelled"):
            return j
        time.sleep(0.4)
    raise AssertionError("job timeout")


def _vol(path, ss=0.0, t=None):
    cmd = [_exe(), "-hide_banner", "-nostdin", "-ss", str(ss)]
    cmd += ["-t", str(t)] if t else []
    cmd += ["-i", str(path), "-vn", "-af", "volumedetect", "-f", "null", "-"]
    err = subprocess.run(cmd, capture_output=True, text=True).stderr
    m = re.search(r"mean_volume: (-?[\d.]+) dB", err)
    mx = re.search(r"max_volume: (-?[\d.]+) dB", err)
    return (float(m.group(1)) if m else -99.0), (float(mx.group(1)) if mx else -99.0)


def _streams(path, kind):
    out = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-select_streams", kind, "-show_entries",
                          "stream=codec_name,width,height,r_frame_rate", "-of", "json", str(path)],
                         capture_output=True, text=True).stdout
    return json.loads(out)["streams"]


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def media(client, tmp_path_factory):
    exe = _exe()
    gen = config.STORAGE_DIR / "generated_clips"
    gen.mkdir(parents=True, exist_ok=True)
    clip_file = gen / "test_p11_clip.mp4"
    subprocess.run([exe, "-y", "-f", "lavfi", "-i", "testsrc=duration=10:size=320x240:rate=15", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=10", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(clip_file)], check=True, capture_output=True)
    music = tmp_path_factory.mktemp("p11")
    music.mkdir(parents=True, exist_ok=True)
    mfile = music / "p11_music.wav"
    subprocess.run([exe, "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=4", str(mfile)], check=True, capture_output=True)
    with SessionLocal() as db:
        v = Video(original_name="p11.mp4", stored_path="original_videos/p11_dummy.mp4", size_bytes=1, duration_sec=10.0,
                  width=320, height=240, format="mp4", status="uploaded")
        db.add(v)
        db.flush()
        c = Clip(video_id=v.id, title="Fight clip", start_sec=0, end_sec=10, duration_sec=10.0, width=320, height=240,
                 aspect_ratio="4:3", status="ready", file_path="generated_clips/test_p11_clip.mp4")
        db.add(c)
        db.commit()
        clip_id = c.id
    r = client.post("/api/music/upload", files=[("files", ("epic_battle_theme.wav", mfile.read_bytes(), "audio/wav"))],
                    data={"folder": "Fights"})
    assert r.status_code == 200 and len(r.json()["uploaded"]) == 1, r.text
    return {"clip_id": clip_id, "clip_file": clip_file, "track_id": r.json()["uploaded"][0]["id"]}


def _out_path(clip_id):
    with SessionLocal() as db:
        return config.STORAGE_DIR / db.get(Clip, clip_id).file_path


def test_upload_rejects_non_audio(client, media):
    r = client.post("/api/music/upload", files=[("files", ("notes.txt", b"hello", "text/plain"))])
    assert r.status_code == 200 and r.json()["uploaded"] == [] and len(r.json()["errors"]) == 1


def test_mix_both_tracks_loop_trim_fades(client, media):
    before = _sha(media["clip_file"])
    body = {"original_enabled": True, "original_volume": 100, "codec": "aac", "bitrate_kbps": 192,
            "tracks": [{"track_id": media["track_id"], "volume": 60, "start_sec": 2, "trim_in": 0.5, "trim_out": 3.5,
                        "fade_in": 0.5, "fade_out": 0.5, "loop": True}]}
    r = client.post(f"/api/audio-studio/clips/{media['clip_id']}/mix", json=body)
    assert r.status_code == 200, r.text
    assert _wait(client, r.json()["job_id"])["status"] == "completed"
    out = _out_path(r.json()["clip_id"])
    assert out.is_file()
    assert abs(probe(out)["duration_sec"] - 10.0) < 0.6          # same duration
    v = _streams(out, "v:0")[0]
    assert (v["codec_name"], v["width"], v["height"], v["r_frame_rate"]) == ("h264", 320, 240, _streams(media["clip_file"], "v:0")[0]["r_frame_rate"])
    assert _streams(out, "a:0")
    assert _vol(out, 0, 1.5)[0] > -40                              # original audio still heard before the music starts
    assert _vol(out, 4, 4)[0] > -40                                # mixed part audible
    assert _sha(media["clip_file"]) == before                      # source clip untouched


def test_music_only_original_off(client, media):
    body = {"original_enabled": False, "original_volume": 100,
            "tracks": [{"track_id": media["track_id"], "volume": 80, "start_sec": 8, "loop": False}]}
    r = client.post(f"/api/audio-studio/clips/{media['clip_id']}/mix", json=body)
    assert _wait(client, r.json()["job_id"])["status"] == "completed"
    out = _out_path(r.json()["clip_id"])
    assert _vol(out, 0, 5)[1] < -60                                # original OFF: silence before the music
    assert _vol(out, 8.3, 1.5)[0] > -50                            # music heard


def test_validation(client, media):
    cid = media["clip_id"]
    assert client.post(f"/api/audio-studio/clips/{cid}/mix", json={"tracks": []}).status_code == 400
    assert client.post(f"/api/audio-studio/clips/{cid}/mix", json={"tracks": [{"track_id": media["track_id"], "volume": 150}]}).status_code == 422
    assert client.post(f"/api/audio-studio/clips/{cid}/mix", json={"tracks": [{"track_id": media["track_id"], "start_sec": 50}]}).status_code == 400
    assert client.post("/api/audio-studio/clips/99999999/mix", json={"tracks": []}).status_code == 404


def test_preview_file(client, media):
    r = client.post(f"/api/audio-studio/clips/{media['clip_id']}/preview?seconds=5",
                    json={"tracks": [{"track_id": media["track_id"], "volume": 50}]})
    assert r.status_code == 200
    jid = r.json()["job_id"]
    assert _wait(client, jid)["status"] == "completed"
    g = client.get(f"/api/audio-studio/preview/{jid}")
    assert g.status_code == 200 and len(g.content) > 1000


def test_waveform_and_suggestions(client, media, monkeypatch):
    from backend.ai import gemini_client
    monkeypatch.setattr(gemini_client, "is_configured", lambda: False)
    w = client.get(f"/api/music/{media['track_id']}/waveform").json()["peaks"]
    assert len(w) > 10 and all(0 <= p <= 1 for p in w)
    s = client.post("/api/audio-studio/suggest", json={"category": "fighting"}).json()
    assert s["items"] and s["items"][0]["track_id"] == media["track_id"]
    assert client.post("/api/audio-studio/suggest", json={"category": "romantic"}).json()["items"] == []
    assert client.post("/api/audio-studio/suggest", json={}).status_code == 400


def test_library_collections_rename_delete(client, media):
    tid = media["track_id"]
    assert client.patch(f"/api/music/{tid}", json={"name": "Renamed", "tags": "epic, drums"}).json()["name"] == "Renamed"
    assert "Fights" in client.get("/api/music").json()["folders"]
    c = client.post("/api/music-collections", json={"name": "Action pack"}).json()
    assert client.post(f"/api/music-collections/{c['id']}/tracks", json={"track_ids": [tid]}).json()["added"] == 1
    assert len(client.get(f"/api/music?collection_id={c['id']}").json()["items"]) == 1
    assert client.delete(f"/api/music-collections/{c['id']}").status_code == 200
    assert client.get(f"/api/music/{tid}/stream").status_code == 200
    assert client.delete(f"/api/music/{tid}").status_code == 200
    assert client.get(f"/api/music/{tid}/stream").status_code == 404