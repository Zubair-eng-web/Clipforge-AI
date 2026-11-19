from fastapi.testclient import TestClient

from backend.main import app


def test_diagnostics_shape():
    with TestClient(app) as c:
        d = c.get("/api/diagnostics").json()
    for k in ("python", "ram", "disk", "tools", "packages", "warnings", "ok", "gemini_key_set"):
        assert k in d
    assert isinstance(d["warnings"], list)
    assert d["ram"]["used_percent"] >= 0