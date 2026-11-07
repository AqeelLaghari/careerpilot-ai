"""Small wrapper around the Gemini API (free tier), built to save quota.

- Two tiers: tier="fast" (Flash-Lite) for simple, frequent tasks and
  tier="smart" (Flash) where quality matters. Free limits apply per model,
  so splitting the work stretches the free quota.
- Automatic fallback: if one model fails (quota/rate limit/outage), try the other.
- Cache: the same prompt is never sent twice while the server runs.
- Never crashes: returns None when Gemini is unavailable, and callers fall
  back to rule-based results.
"""
import hashlib
import json
import logging
from collections import Counter

from pydantic import BaseModel

from app.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_MODEL_FAST

log = logging.getLogger(__name__)
_client = None
_cache: dict[str, str] = {}
usage = Counter()  # calls per model (shown on /health)

MODELS = {"smart": GEMINI_MODEL, "fast": GEMINI_MODEL_FAST}


def available() -> bool:
    return bool(GEMINI_API_KEY) and "paste" not in GEMINI_API_KEY.lower()


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def _call(prompt: str, tier: str, temperature: float, schema: type[BaseModel] | None) -> str | None:
    if not available():
        log.info("Gemini key not set; skipping LLM call.")
        return None
    key = hashlib.sha256(f"{tier}|{temperature}|{schema and schema.__name__}|{prompt}".encode()).hexdigest()
    if key in _cache:
        usage["cache_hits"] += 1
        return _cache[key]

    from google.genai import types
    config = types.GenerateContentConfig(temperature=temperature)
    if schema is not None:
        config.response_mime_type = "application/json"
        config.response_schema = schema

    other = "smart" if tier == "fast" else "fast"
    for model in (MODELS[tier], MODELS[other]):  # preferred model first, then fallback
        try:
            resp = _get_client().models.generate_content(model=model, contents=prompt, config=config)
            usage[model] += 1
            _cache[key] = resp.text
            return resp.text
        except Exception as e:  # quota (429), network, outage…
            usage[f"{model}_errors"] += 1
            log.warning("Gemini %s failed (%s); trying fallback.", model, str(e)[:120])
    return None


def generate_json(prompt: str, schema: type[BaseModel], tier: str = "fast",
                  temperature: float = 0.2) -> dict | None:
    """Ask Gemini for JSON matching a Pydantic schema. Returns a dict or None."""
    text = _call(prompt, tier, temperature, schema)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.warning("Gemini returned invalid JSON.")
        return None


def generate_text(prompt: str, tier: str = "fast", temperature: float = 0.7) -> str | None:
    return _call(prompt, tier, temperature, None)
