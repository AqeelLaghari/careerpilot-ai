"""Specific learning links for roadmap skills (Day 13).

- YouTube: the top tutorial videos for a skill, from the YouTube Data API v3
  (free key; a search costs 100 of the 10,000 free daily units, about 100 searches a day).
  Each skill is searched ONCE and cached in Firestore for 30 days, shared by all users,
  so the quota goes a long way.
- Official docs: Gemini suggests the URL (in the same batched roadmap call); we only keep
  it if the page really opens (HTTP status < 400), so invented links never reach the user.
Without a key, or when the quota is used up, roadmap.py falls back to search links.
"""
import json
import logging
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from app.config import YOUTUBE_API_KEY

log = logging.getLogger(__name__)

CACHE_COLLECTION = "resource_cache"
CACHE_TTL = 30 * 24 * 3600
_memory: dict[str, dict] = {}
_quota_hit_at = 0.0           # after a quota error, don't call again for a while


def _db():
    from app.deps import blackboard
    return blackboard._db


def _key(skill: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in skill.lower())[:100]


def _cache_get(skill: str) -> dict | None:
    k = _key(skill)
    hit = _memory.get(k)
    if hit is None and _db() is not None:
        try:
            snap = _db().collection(CACHE_COLLECTION).document(k).get()
            hit = snap.to_dict() if snap.exists else None
        except Exception:
            log.warning("Resource cache read failed", exc_info=True)
    if hit and time.time() - hit.get("fetched_at", 0) < CACHE_TTL:
        _memory[k] = hit
        return hit
    return None


def _cache_put(skill: str, videos: list[dict]):
    k = _key(skill)
    entry = {"skill": skill, "videos": videos, "fetched_at": time.time()}
    _memory[k] = entry
    if _db() is not None:
        try:
            _db().collection(CACHE_COLLECTION).document(k).set(entry)
        except Exception:
            log.warning("Resource cache write failed", exc_info=True)


def youtube_search(skill: str, max_results: int = 3) -> list[dict] | None:
    """Top tutorial videos for a skill, or None if unavailable (no key / quota / network)."""
    global _quota_hit_at
    if not YOUTUBE_API_KEY or time.time() - _quota_hit_at < 3600:
        return None
    params = urllib.parse.urlencode({
        "part": "snippet", "type": "video", "maxResults": max_results, "order": "relevance",
        "q": f"{skill} tutorial for beginners", "relevanceLanguage": "en", "safeSearch": "strict",
        "videoEmbeddable": "true", "key": YOUTUBE_API_KEY,
    })
    try:
        with urllib.request.urlopen(f"https://www.googleapis.com/youtube/v3/search?{params}", timeout=8) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 403:                                   # daily quota used up (or key not allowed)
            _quota_hit_at = time.time()
        log.warning("YouTube search failed for %s: HTTP %s", skill, e.code)
        return None
    except Exception as e:
        log.warning("YouTube search failed for %s: %s", skill, str(e)[:100])
        return None
    out = []
    for item in data.get("items", []):
        vid = item.get("id", {}).get("videoId")
        sn = item.get("snippet", {})
        if vid:
            out.append({"type": "video", "title": _unescape(sn.get("title", skill)),
                        "channel": sn.get("channelTitle"), "url": f"https://www.youtube.com/watch?v={vid}"})
    return out


def _unescape(s: str) -> str:
    import html
    return html.unescape(s)


def videos_for(skills: list[str]) -> dict[str, list[dict]]:
    """{skill: [videos]} using the cache first; missing skills are fetched in parallel."""
    result, missing = {}, []
    for s in skills:
        hit = _cache_get(s)
        if hit is not None:
            result[s] = hit["videos"]
        else:
            missing.append(s)
    if missing and YOUTUBE_API_KEY:
        with ThreadPoolExecutor(max_workers=6) as pool:
            for s, vids in zip(missing, pool.map(youtube_search, missing), strict=False):
                if vids:                                    # cache only real results
                    _cache_put(s, vids)
                    result[s] = vids
    return result


def url_works(url: str | None) -> bool:
    """True if the page opens (so a suggested link isn't invented)."""
    if not url or not url.startswith("https://"):
        return False
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0 CareerPilot link check"})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.status < 400
    except Exception:
        return False


def check_urls(urls: list[str | None]) -> list[bool]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(url_works, urls))
