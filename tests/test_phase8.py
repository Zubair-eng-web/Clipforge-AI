import time

import pytest
from fastapi.testclient import TestClient

from backend.database.db import SessionLocal
from backend.database.models import Job
from backend.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_queue_summary(client):
    d = client.get("/api/queue/summary").json()
    assert set(d["counts"]) == {"queued", "processing", "completed", "failed", "cancelled"}


def test_retry_failed_job(client):
    with SessionLocal() as db:
        j = Job(type="noop_test", status="failed", error="x")
        db.add(j)
        db.commit()
        old_id = j.id
    r = client.post(f"/api/queue/{old_id}/retry")
    assert r.status_code == 200
    new_id = r.json()["id"]
    assert new_id != old_id
    assert client.post(f"/api/queue/{new_id}/retry").status_code in (404, 409)
    time.sleep(1.5)
    with SessionLocal() as db:
        for i in (old_id, new_id):
            row = db.get(Job, i)
            if row:
                db.delete(row)
        db.commit()


def test_retry_rejects_unfinished_job(client):
    with SessionLocal() as db:
        j = Job(type="noop_test", status="completed")
        db.add(j)
        db.commit()
        jid = j.id
    assert client.post(f"/api/queue/{jid}/retry").status_code == 409
    with SessionLocal() as db:
        db.delete(db.get(Job, jid))
        db.commit()


def test_projects_crud(client):
    p = client.post("/api/projects", json={"name": "Test project", "description": "d"}).json()
    pid = p["id"]
    assert client.get(f"/api/projects/{pid}").json()["name"] == "Test project"
    assert client.patch(f"/api/projects/{pid}", json={"name": "Renamed"}).json()["name"] == "Renamed"
    assert client.post("/api/projects", json={"name": "x", "video_id": 99999999}).status_code == 404
    assert client.post("/api/projects", json={"name": ""}).status_code == 422
    assert client.delete(f"/api/projects/{pid}").status_code == 200
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_collections_crud(client):
    c = client.post("/api/collections", json={"name": "Test collection"}).json()
    cid = c["id"]
    r = client.post(f"/api/collections/{cid}/clips", json={"clip_ids": [99999999]})
    assert r.json()["added"] == 0
    assert client.get(f"/api/collections/{cid}").json()["clips"] == []
    assert client.delete(f"/api/collections/{cid}/clips/99999999").status_code == 404
    assert client.delete(f"/api/collections/{cid}").status_code == 200


def test_history(client):
    d = client.get("/api/history?limit=10").json()
    assert isinstance(d["items"], list) and len(d["items"]) <= 10


def test_storage_overview_and_cleanup(client):
    d = client.get("/api/storage-manager/overview").json()
    for k in ("folders", "total_bytes", "orphan_files", "disk"):
        assert k in d
    assert client.post("/api/storage-manager/cleanup", json={"target": "everything"}).status_code == 400
    assert client.post("/api/storage-manager/cleanup", json={"target": "temporary"}).status_code == 200


def test_analytics_keys(client):
    d = client.get("/api/analytics").json()
    for k in ("videos", "clips", "jobs", "highlights", "clips_per_day"):
        assert k in d
    assert len(d["clips_per_day"]) == 14