from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import Boolean, DateTime, Float, Integer

import backend.database.db as dbmod
from backend.database.models import Clip, Video
from backend.main import app
from backend.social import generator as g


def _make_video(db) -> int:
    vals = {}
    for col in Video.__table__.columns:
        if col.primary_key or col.nullable or col.default is not None or col.server_default is not None:
            continue
        t = col.type
        if isinstance(t, Boolean):
            vals[col.name] = False
        elif isinstance(t, Integer):
            vals[col.name] = 1
        elif isinstance(t, Float):
            vals[col.name] = 1.0
        elif isinstance(t, DateTime):
            vals[col.name] = datetime.now(timezone.utc)
        else:
            vals[col.name] = "test"
    v = Video(**vals)
    db.add(v)
    db.commit()
    return v.id


def _clip() -> int:
    with dbmod.SessionLocal() as db:
        vid = _make_video(db)
        c = Clip(video_id=vid, title="Police chase on the bridge", status="ready",
                 start_sec=0, end_sec=10, duration_sec=10)
        db.add(c)
        db.commit()
        return c.id


def test_social_full_flow(monkeypatch):
    monkeypatch.setattr(g, "is_configured", lambda: False)
    with TestClient(app) as c:
        cid = _clip()
        o = c.get("/api/social/options").json()
        assert "viral" in o["tones"] and "general" in o["platforms"]
        r = c.post("/api/social/generate", json={"clip_id": cid, "tone": "viral", "platform": "general"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["source"] == "local" and d["title"] and d["approved"] is False
        tid = d["id"]
        r = c.put(f"/api/social/{tid}", json={"title": "My title", "approved": True})
        assert r.status_code == 200 and r.json()["title"] == "My title" and r.json()["approved"] is True
        lst = c.get(f"/api/social?clip_id={cid}").json()["items"]
        assert any(i["id"] == tid for i in lst)
        assert c.post("/api/social/generate", json={"clip_id": cid, "tone": "nope"}).status_code == 400
        assert c.post("/api/social/generate", json={"clip_id": 999999, "tone": "viral"}).status_code == 404
        assert c.delete(f"/api/social/{tid}").status_code == 200
        assert c.delete(f"/api/social/{tid}").status_code == 404

