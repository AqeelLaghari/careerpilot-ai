"""Small wrapper around the Gemini API (free tier).

Every call returns None instead of crashing when Gemini is unavailable
(no key, no internet, rate limit). Callers must handle None.
"""
import json
import logging

from pydantic import BaseModel

from app.config import GEMINI_API_KEY, GEMINI_MODEL

log = logging.getLogger(__name__)
_client = None


def available() -> bool:
    return GEMINI_API_KEY.startswith("AIza")


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def generate_json(prompt: str, schema: type[BaseModel], temperature: float = 0.2) -> dict | None:
    """Ask Gemini for JSON matching a Pydantic schema. Returns a dict or None."""
    if not available():
        log.info("Gemini key not set; skipping LLM call.")
        return None
    try:
        from google.genai import types
        resp = _get_client().models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=temperature,
            ),
        )
        return json.loads(resp.text)
    except Exception as e:  # network, quota, bad JSON…
        log.warning("Gemini call failed: %s", e)
        return None


def generate_text(prompt: str, temperature: float = 0.7) -> str | None:
    if not available():
        return None
    try:
        from google.genai import types
        resp = _get_client().models.generate_content(
            model=GEMINI_MODEL, contents=prompt,
            config=types.GenerateContentConfig(temperature=temperature),
        )
        return resp.text
    except Exception as e:
        log.warning("Gemini call failed: %s", e)
        return None
