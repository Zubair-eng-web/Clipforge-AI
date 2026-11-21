"""Change the Gemini API key live (no .env editing). The key is never returned in full."""
import json
import os
from pathlib import Path

from dotenv import dotenv_values
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend import config
from backend.ai import gemini_client

router = APIRouter(prefix="/api/gemini-key", tags=["gemini-key"])
KEY_FILE = config.STORAGE_DIR / "settings" / "gemini_key.json"
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def _read() -> str:
    try:
        return str(json.loads(KEY_FILE.read_text(encoding="utf-8-sig")).get("key", "")).strip()
    except Exception:
        return ""


def load_saved_key() -> bool:
    k = _read()
    if k:
        os.environ["GEMINI_API_KEY"] = k
    return bool(k)


load_saved_key()  # runs when the app starts: a saved key wins over .env


def _mask(k: str) -> str:
    return ("*" * 8 + k[-4:]) if len(k) >= 8 else ""


def _status() -> dict:
    cur = os.environ.get("GEMINI_API_KEY", "")
    configured = bool(cur) and cur != "your_key_here"
    saved = bool(_read())
    return {"configured": configured, "source": "saved" if saved else ("env" if configured else "none"),
            "masked": _mask(cur) if configured else "", "model": gemini_client.get_model()}


class KeyIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=300)


@router.get("/status")
def status():
    return _status()


@router.post("")
def save_key(body: KeyIn):
    k = body.key.strip()
    if len(k) < 20 or any(ch.isspace() for ch in k):
        raise HTTPException(400, "This does not look like a valid Gemini API key")
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(json.dumps({"key": k}), encoding="utf-8")
    os.environ["GEMINI_API_KEY"] = k
    return _status()


@router.delete("")
def remove_key():
    KEY_FILE.unlink(missing_ok=True)
    v = ""
    try:
        v = str(dotenv_values(ENV_FILE).get("GEMINI_API_KEY") or "")
    except Exception:
        pass
    if v:
        os.environ["GEMINI_API_KEY"] = v
    else:
        os.environ.pop("GEMINI_API_KEY", None)
    return _status()


@router.post("/test")
def test_key():
    if not gemini_client.is_configured():
        return {"ok": False, "error": "No Gemini key is set"}
    try:
        gemini_client.ask("Reply with the single word OK")
        return {"ok": True, "error": None}
    except Exception as e:
        msg = str(e).replace(os.environ.get("GEMINI_API_KEY", "\0"), "***")
        return {"ok": False, "error": msg[:300]}
