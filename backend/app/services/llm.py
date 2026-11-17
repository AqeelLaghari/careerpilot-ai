"""Small wrapper around the Gemini API (free tier), built to save quota.

- Two tiers: tier="fast" (Flash-Lite) for simple, frequent tasks and
  tier="smart" (Flash) where quality matters. Free limits apply per model,
  so splitting the work stretches the free quota.
- Automatic fallback: if one model fails (quota/rate limit/outage), try the other.
- Cache: the same prompt is never sent twice while the server runs.
- Never crashes: returns None when Gemini is unavailable, and callers fall
  back to rule-based results.
- hedge_after (live interview): when an answer is late, a second identical request
  is sent and the first answer wins (Gemini sometimes stalls for many seconds on one
  request while a new one answers in about 1.5 s).
"""
import hashlib
import json
import logging
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from concurrent.futures import TimeoutError as FutureTimeout

from pydantic import BaseModel

from app.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_MODEL_FAST

log = logging.getLogger(__name__)
_client = None
_cache: dict[str, str] = {}
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gemini")
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


def _first(futures: list, deadline: float) -> str:
    """The first successful result of futures before deadline (else the last error / FutureTimeout)."""
    pending, error = set(futures), None
    while pending:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        done, pending = wait(pending, timeout=left, return_when=FIRST_COMPLETED)
        for f in done:
            if f.exception() is None:
                return f.result()
            error = f.exception()
    if error is not None and not pending:
        raise error
    raise FutureTimeout()


def _call(prompt: str, tier: str, temperature: float, schema: type[BaseModel] | None,
          timeout: float | None = None, quick: bool = False, hedge_after: float | None = None) -> str | None:
    if not available():
        log.info("Gemini key not set; skipping LLM call.")
        return None
    key = hashlib.sha256(f"{tier}|{temperature}|{schema and schema.__name__}|{quick}|{prompt}".encode()).hexdigest()
    if key in _cache:
        usage["cache_hits"] += 1
        return _cache[key]

    from google.genai import types
    config = types.GenerateContentConfig(temperature=temperature)
    if quick:   # no "thinking" step: much faster replies for simple, time-critical tasks
        config.thinking_config = types.ThinkingConfig(thinking_level="minimal")
    if schema is not None:
        config.response_mime_type = "application/json"
        config.response_schema = schema

    other = "smart" if tier == "fast" else "fast"
    deadline = time.monotonic() + timeout if timeout else None
    for model in (MODELS[tier], MODELS[other]):  # preferred model first, then fallback
        try:
            if deadline is None:
                text = _generate(model, prompt, config)
            else:
                # Time budget: a busy Gemini (503 "high demand") can retry for minutes. Past the
                # budget the caller uses its rule-based fallback; a late answer is still cached.
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("time budget used up")
                def send(model: str = model):
                    fut = _pool.submit(_generate, model, prompt, config)
                    fut.add_done_callback(lambda f, k=key: f.exception() or _cache.__setitem__(k, f.result()))
                    return fut

                futures = [send()]
                if hedge_after and left > hedge_after and not wait(futures, timeout=hedge_after).done:
                    usage["hedged"] += 1
                    log.info("Gemini %s is slow; sending the request again", model)
                    futures.append(send())
                text = _first(futures, deadline)
            usage[model] += 1
            _cache[key] = text
            return text
        except FutureTimeout:
            usage[f"{model}_errors"] += 1
            log.warning("Gemini %s took longer than %.0f s; using the fallback.", model, timeout)
            return None
        except Exception as e:  # quota (429), network, outage…
            usage[f"{model}_errors"] += 1
            log.warning("Gemini %s failed (%s); trying fallback.", model, str(e)[:120])
    return None


def _generate(model: str, prompt: str, config) -> str:
    return _get_client().models.generate_content(model=model, contents=prompt, config=config).text


def generate_json(prompt: str, schema: type[BaseModel], tier: str = "fast", temperature: float = 0.2,
                  timeout: float | None = None, quick: bool = False, hedge_after: float | None = None) -> dict | None:
    """Ask Gemini for JSON matching a Pydantic schema. Returns a dict or None.
    timeout: seconds the caller can wait in total (None = no limit, for background jobs).
    hedge_after: seconds after which a slow request is sent a second time (needs timeout)."""
    text = _call(prompt, tier, temperature, schema, timeout, quick, hedge_after)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        log.warning("Gemini returned invalid JSON.")
        return None


def generate_text(prompt: str, tier: str = "fast", temperature: float = 0.7) -> str | None:
    return _call(prompt, tier, temperature, None)
