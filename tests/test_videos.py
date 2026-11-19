import shutil
import subprocess

import pytest

from backend.config import STORAGE_DIR

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)


@pytest.fixture(scope="session")
def sample_mp4(tmp_path_factory):
    out = tmp_path_factory.mktemp("media") / "sample.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)],
        check=True, capture_output=True,
    )
    return out.read_bytes()


@pytest.fixture(scope="session")
def sample_wav(tmp_path_factory):
    out = tmp_path_factory.mktemp("media") / "sample.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(out)],
        check=True, capture_output=True,
    )
    return out.read_bytes()


def upload(client, name, data, ctype="application/octet-stream"):
    return client.post("/api/videos/upload", files=[("files", (name, data, ctype))])


def stored_files():
    d = STORAGE_DIR / "original_videos"
    return {p.name for p in d.iterdir() if p.is_file() and p.name != ".gitkeep"}


def no_temp_leftovers():
    return list((STORAGE_DIR / "temporary").glob("*.part")) == []


def test_upload_valid_video(client, sample_mp4):
    before = stored_files()
    r = upload(client, "My Clip.mp4", sample_mp4, "video/mp4")
    assert r.status_code == 200
    v = r.json()["uploaded"][0]
    assert v["name"] == "My Clip.mp4"
    assert v["width"] == 320 and v["height"] == 240
    assert 1.5 < v["duration_sec"] < 3
    assert v["has_video"] is True
    assert len(stored_files()) == len(before) + 1
    assert no_temp_leftovers()


def test_upload_audio_file(client, sample_wav):
    r = upload(client, "voice.wav", sample_wav, "audio/wav")
    assert r.status_code == 200
    v = r.json()["uploaded"][0]
    assert v["width"] is None
    assert v["has_video"] is False
    assert 0.5 < v["duration_sec"] < 2


def test_reject_bad_extension(client):
    before = stored_files()
    r = upload(client, "virus.exe", b"MZ" + b"\x00" * 200)
    assert r.status_code == 400
    assert r.json()["errors"][0]["code"] == "bad_type"
    assert stored_files() == before


def test_reject_fake_video(client):
    before = stored_files()
    r = upload(client, "fake.mp4", b"this is not a video " * 100)
    assert r.status_code == 400
    assert r.json()["errors"][0]["code"] == "invalid_media"
    assert stored_files() == before
    assert no_temp_leftovers()


def test_path_traversal_is_neutralised(client, sample_mp4):
    before = stored_files()
    r = upload(client, "../../evil.mp4", sample_mp4, "video/mp4")
    assert r.status_code == 200
    v = r.json()["uploaded"][0]
    assert v["name"] == "evil.mp4"
    assert len(stored_files()) == len(before) + 1
    assert not (STORAGE_DIR / "evil.mp4").exists()
    assert not (STORAGE_DIR.parent / "evil.mp4").exists()


def test_size_limit(client, sample_mp4, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_GB", "0.000001")  # about 1 KB
    before = stored_files()
    r = upload(client, "big.mp4", sample_mp4, "video/mp4")
    assert r.status_code == 413
    assert r.json()["errors"][0]["code"] == "too_large"
    assert stored_files() == before
    assert no_temp_leftovers()


def test_multi_upload_partial_success(client, sample_mp4):
    r = client.post("/api/videos/upload", files=[
        ("files", ("good.mp4", sample_mp4, "video/mp4")),
        ("files", ("notes.txt", b"hello", "text/plain")),
    ])
    assert r.status_code == 200
    body = r.json()
    assert len(body["uploaded"]) == 1
    assert len(body["errors"]) == 1


def test_list_and_search(client, sample_mp4):
    upload(client, "searchable_unique_name.mp4", sample_mp4, "video/mp4")
    hit = client.get("/api/videos", params={"q": "searchable_unique"}).json()
    assert hit["total"] == 1
    assert hit["items"][0]["name"] == "searchable_unique_name.mp4"
    miss = client.get("/api/videos", params={"q": "zzz_no_such_video"}).json()
    assert miss["total"] == 0


def test_stream_and_range(client, sample_mp4):
    vid = upload(client, "stream_me.mp4", sample_mp4, "video/mp4").json()["uploaded"][0]
    full = client.get(f"/api/videos/{vid['id']}/stream")
    assert full.status_code == 200
    assert full.content == sample_mp4
    part = client.get(f"/api/videos/{vid['id']}/stream", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206
    assert len(part.content) == 100


def test_delete_removes_file_and_record(client, sample_mp4):
    before = stored_files()
    vid = upload(client, "delete_me.mp4", sample_mp4, "video/mp4").json()["uploaded"][0]
    assert len(stored_files()) == len(before) + 1
    r = client.delete(f"/api/videos/{vid['id']}")
    assert r.status_code == 200
    assert stored_files() == before
    assert client.get(f"/api/videos/{vid['id']}").status_code == 404
    assert client.delete(f"/api/videos/{vid['id']}").status_code == 404