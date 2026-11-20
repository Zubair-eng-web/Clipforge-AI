import os
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "gemini-3.1-flash-lite"


def get_model() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_MODEL)


def is_configured() -> bool:
    key = os.getenv("GEMINI_API_KEY", "")
    return bool(key) and key != "your_key_here"


def ask(prompt: str) -> str:
    """Send TEXT ONLY to Gemini (transcripts, never video files)."""
    if not is_configured():
        raise RuntimeError("GEMINI_API_KEY is not set in .env")
    from google import genai

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(model=get_model(), contents=prompt)
    return resp.text or ""

def ask_parts(parts: list) -> str:
    """Send text and small JPEG frames (bytes) to Gemini. Used by Scene Detection (vision)."""
    if not is_configured():
        raise RuntimeError("GEMINI_API_KEY is not set in .env")
    from google import genai
    from google.genai import types

    contents = []
    for p in parts:
        if isinstance(p, (bytes, bytearray)):
            contents.append(types.Part.from_bytes(data=bytes(p), mime_type="image/jpeg"))
        else:
            contents.append(str(p))
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(model=get_model(), contents=contents)
    return resp.text or ""
