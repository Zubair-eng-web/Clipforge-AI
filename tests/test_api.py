from backend.database.db import SessionLocal
from backend.database.models import Clip, Job, Video


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_dashboard_starts_empty(client):
    data = client.get("/api/dashboard").json()
    assert data["total_videos"] == 0
    assert data["total_clips"] == 0
    assert data["failed_jobs"] == 0


def test_dashboard_counts_records(client):
    with SessionLocal() as db:
        v = Video(original_name="demo.mp4", stored_path="storage/original_videos/demo.mp4", size_bytes=1000)
        db.add(v)
        db.flush()
        db.add(Clip(video_id=v.id, title="Clip 1", start_sec=0, end_sec=60, duration_sec=60))
        db.add(Job(type="auto_clip", video_id=v.id, status="failed", error="test"))
        db.add(Job(type="auto_clip", video_id=v.id, status="completed"))
        db.commit()
    data = client.get("/api/dashboard").json()
    assert data["total_videos"] == 1
    assert data["total_clips"] == 1
    assert data["failed_jobs"] == 1
    assert data["completed_jobs"] == 1
    assert data["recent_videos"][0]["name"] == "demo.mp4"