"""Live remote-jobs pool + matching (Day 14).

- Pool: every source in job_sources is fetched together at most every REFRESH_SECONDS
  (Remotive asks for at most 4 calls a day, Himalayas refreshes daily). The refresh runs in
  a background thread, so no user request ever waits for it.
- Saved: EVERY fetched posting (open to Pakistan or not) goes to the Firestore collection
  "job_postings" with the skills found in it. That collection is the live training data
  for the self-learning market model (market_learning.py).
- Shown: only jobs open to Pakistan. Matching uses the same two signals as the
  job-description match (career_matcher.jd_match):
      keyword  = share of the job's skills the user has (spaCy skill detector)
      semantic = SBERT cosine between the user's profile and "<title>. Key skills: ..."
- Role search: for the user's target role we also ask Himalayas directly
  (q=<role>, country=PK), cached per role, so niche roles get relevant jobs too.
"""
import json
import logging
import threading
import time

import numpy as np

from app.config import DATA_DIR
from app.services import career_matcher, embeddings, job_sources
from app.services.entity_extractor import find_skills_batch

log = logging.getLogger(__name__)

REFRESH_SECONDS = 6 * 3600
ROLE_CACHE_SECONDS = 6 * 3600
MAX_AGE_DAYS = 45                         # older postings are not shown
POOL_FILE = DATA_DIR / "raw" / "jobs_pool.json"     # quick restart cache (git-ignored)
COLLECTION = "job_postings"

_lock = threading.Lock()
_refreshing = threading.Event()
_pool: dict = {"jobs": {}, "updated_at": 0.0, "report": {}}
_vectors: dict[str, np.ndarray] = {}
_role_cache: dict[str, float] = {}
_saved: set[str] = set()                  # postings already in Firestore (this process)
SOFT = "soft_skills"
MIN_SKILLS = 5                            # keyword % is out of at least this many skills


def _db():
    from app.deps import blackboard
    return blackboard._db


# --------------------------------------------------------------- the pool --
def job_text(job: dict) -> str:
    """Same shape as role_text / jd_match, so cosine scores are comparable."""
    skills = ", ".join(job.get("skills", [])[:15])
    return f"{job['title']}. Key skills: {skills}." if skills else f"{job['title']}. {job['description'][:300]}"


def _add_skills(jobs: list[dict]):
    texts = [f"{j['title']}\n{' , '.join(j.get('tags', []))}\n{j['description']}" for j in jobs]
    for job, found in zip(jobs, find_skills_batch(texts)):
        hard = [s for s, cat in found.items() if cat != SOFT]          # soft skills don't count
        job["skills"] = sorted(hard, key=lambda s: -job["description"].lower().count(s.lower()))


def _embed(jobs: list[dict]):
    todo = [j for j in jobs if j["id"] not in _vectors]
    if todo:
        for j, v in zip(todo, embeddings.embed([job_text(j) for j in todo])):
            _vectors[j["id"]] = v


def _save_all(jobs: list[dict]):
    """Every posting → Firestore (batched: 400 writes per commit). Never breaks the refresh."""
    db = _db()
    jobs = [j for j in jobs if j["dedupe_key"] not in _saved]
    if db is None or not jobs:
        return
    try:
        now = time.time()
        col = db.collection(COLLECTION)
        for i in range(0, len(jobs), 400):
            batch = db.batch()
            for j in jobs[i:i + 400]:
                doc = {k: j.get(k) for k in ("id", "source", "title", "company", "location", "scope",
                                             "open_to_pakistan", "url", "published_at", "expires_at",
                                             "skills", "category", "dedupe_key")}
                doc["description"] = j["description"][:4000]
                doc["fetched_at"] = now
                batch.set(col.document(j["dedupe_key"]), doc, merge=True)
            batch.commit()
            _saved.update(j["dedupe_key"] for j in jobs[i:i + 400])
        log.info("Saved %d postings to Firestore", len(jobs))
    except Exception:
        log.warning("Saving postings to Firestore failed", exc_info=True)


def _fresh(job: dict, now: float) -> bool:
    if job.get("expires_at") and job["expires_at"] < now:
        return False
    return not job.get("published_at") or now - job["published_at"] < MAX_AGE_DAYS * 86400


def _merge(jobs: list[dict]):
    now = time.time()
    shown = [j for j in jobs if j["open_to_pakistan"] and _fresh(j, now)]
    _embed(shown)
    with _lock:
        for j in shown:
            _pool["jobs"][j["dedupe_key"]] = j
        for k in [k for k, j in _pool["jobs"].items() if not _fresh(j, now)]:
            del _pool["jobs"][k]


def refresh() -> dict:
    """Fetch every source, save everything, keep the jobs open to Pakistan."""
    t = time.time()
    jobs, report = job_sources.fetch_all()
    _add_skills(jobs)
    _merge(jobs)                                          # users see the new jobs now…
    with _lock:
        _pool["updated_at"] = time.time()
        _pool["report"] = report | {"fetched": len(jobs), "shown": len(_pool["jobs"]),
                                    "seconds": round(time.time() - t, 1)}
    _write_file()
    log.info("Jobs refreshed: %s", _pool["report"])
    _save_all(jobs)                                       # …while every posting is saved for learning
    try:                                                  # self-learning hook (weekly, lazy)
        from app.services import market_learning
        market_learning.maybe_learn()
    except Exception:
        log.warning("Market learning trigger failed", exc_info=True)
    return _pool["report"]


def _write_file():
    try:
        POOL_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            data = {"updated_at": _pool["updated_at"], "report": _pool["report"], "jobs": list(_pool["jobs"].values())}
        POOL_FILE.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def _load_file():
    if _pool["jobs"] or not POOL_FILE.exists():
        return
    try:
        data = json.loads(POOL_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    _merge(data.get("jobs", []))
    with _lock:
        _pool["updated_at"] = data.get("updated_at", 0.0)
        _pool["report"] = data.get("report", {})


def _background_refresh():
    try:
        refresh()
    except Exception:
        log.exception("Jobs refresh failed")
    finally:
        _refreshing.clear()


def ensure_fresh() -> bool:
    """Start a background refresh if the pool is old. True while one is running."""
    _load_file()
    if time.time() - _pool["updated_at"] > REFRESH_SECONDS and not _refreshing.is_set():
        _refreshing.set()
        threading.Thread(target=_background_refresh, daemon=True).start()
    return _refreshing.is_set()


def add_role_jobs(role: str | None, wait: bool = False):
    """Jobs for the user's role straight from Himalayas (open to Pakistan), cached per role.
    Runs in the background unless wait=True; they show up on the next load."""
    if not role or time.time() - _role_cache.get(role.lower(), 0) < ROLE_CACHE_SECONDS:
        return
    _role_cache[role.lower()] = time.time()
    if not wait:
        threading.Thread(target=_role_jobs, args=(role,), daemon=True).start()
        return
    _role_jobs(role)


def _role_jobs(role: str):
    try:
        jobs = job_sources.himalayas(query=role, pages=2)
    except Exception as e:
        log.warning("Himalayas role search failed for %s: %s", role, str(e)[:100])
        return
    _add_skills(jobs)
    _merge(jobs)
    _save_all(jobs)


def status() -> dict:
    with _lock:
        return {"updated_at": _pool["updated_at"] or None, "jobs_available": len(_pool["jobs"]),
                "refreshing": _refreshing.is_set(), "report": dict(_pool["report"])}


# --------------------------------------------------------------- matching --
def match_jobs(profile: dict, query: str | None = None, limit: int = 30) -> list[dict]:
    """Jobs open to Pakistan, best match first."""
    with _lock:
        jobs = list(_pool["jobs"].values())
    if query:
        q = query.lower()
        jobs = [j for j in jobs if q in j["title"].lower() or q in j["company"].lower()
                or any(q in s.lower() for s in j.get("skills", []))]
    if not jobs:
        return []
    _embed(jobs)
    have = {s["name"].lower() for s in profile.get("skills", [])}
    me = embeddings.embed([career_matcher.resume_text(profile)])[0]
    sims = np.stack([_vectors[j["id"]] for j in jobs]) @ me
    out = []
    for j, cos in zip(jobs, sims):
        skills = j.get("skills", [])[:20]
        matched = [s for s in skills if s.lower() in have]
        missing = [s for s in skills if s.lower() not in have]
        sem = career_matcher.semantic_score(float(cos))
        if skills:
            kw = round(100 * len(matched) / max(len(skills), MIN_SKILLS))
            score = round(career_matcher.JD_W_SEMANTIC * sem + career_matcher.JD_W_KEYWORD * kw)
        else:                                              # no skills detected: meaning only
            kw, score = None, sem
        out.append({k: j.get(k) for k in ("id", "title", "company", "location", "scope", "url", "apply_url",
                                          "job_type", "salary", "published_at", "source")}
                   | {"source_name": job_sources.SOURCES[j["source"]]["name"],
                      "excerpt": j["description"][:280], "match": score, "semantic": sem, "keyword": kw,
                      "matched_skills": matched[:8], "missing_skills": missing[:6]})
    out.sort(key=lambda r: (-r["match"], -(r["published_at"] or 0)))
    return out[:limit]
