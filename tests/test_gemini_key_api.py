from fastapi.testclient import TestClient

from backend.api import gemini_key as gk
from backend.ai import gemini_client
from backend.main import app

KEY = "AIza" + "x" * 35


def test_key_save_test_remove(monkeypatch, tmp_path):
    monkeypatch.setattr(gk, "KEY_FILE", tmp_path / "k.json")
    monkeypatch.setattr(gk, "ENV_FILE", tmp_path / "no.env")
    monkeypatch.setenv("GEMINI_API_KEY", "your_key_here")
    with TestClient(app) as c:
        assert c.get("/api/gemini-key/status").json()["configured"] is False
        assert c.post("/api/gemini-key", json={"key": "short"}).status_code == 400
        r = c.post("/api/gemini-key", json={"key": KEY})
        assert r.status_code == 200 and KEY not in r.text
        d = r.json()
        assert d["configured"] and d["source"] == "saved" and d["masked"].endswith("xxxx")
        assert gk.load_saved_key() is True
        monkeypatch.setattr(gemini_client, "ask", lambda p: "OK")
        assert c.post("/api/gemini-key/test").json()["ok"] is True

        def boom(p):
            raise RuntimeError("bad key " + KEY)
        monkeypatch.setattr(gemini_client, "ask", boom)
        t = c.post("/api/gemini-key/test").json()
        assert t["ok"] is False and KEY not in t["error"]
        d = c.delete("/api/gemini-key").json()
        assert d["configured"] is False and d["source"] == "none"
