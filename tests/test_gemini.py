import pytest
from backend.ai import gemini_client as g


def test_default_model_name(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert g.get_model() == "gemini-3.1-flash-lite"


def test_missing_key_is_detected(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "your_key_here")
    assert g.is_configured() is False
    with pytest.raises(RuntimeError):
        g.ask("hi")


@pytest.mark.skipif(not g.is_configured(), reason="GEMINI_API_KEY not set")
def test_live_gemini_call():
    try:
        out = g.ask("Reply with only the word OK")
    except Exception as e:  # no internet / DNS problem is not a code bug
        if any(s in str(e) for s in ("getaddrinfo", "PERMISSION_DENIED", "RESOURCE_EXHAUSTED", "429", "403", "503", "UNAVAILABLE")) or "ConnectError" in type(e).__name__ or "Timeout" in type(e).__name__:
            pytest.skip(f"Gemini not available right now (offline / billing / quota): {str(e)[:120]}")
        raise
    assert out.strip() != ""