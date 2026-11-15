"""Live remote jobs from free public job APIs (Day 14).

Sources (all free, no key needed; each one's terms are followed):
  - Himalayas  himalayas.app/jobs/api   show only in our own app, visible link to the job on
                                        Himalayas, Apply = their applicationLink unchanged,
                                        drop expired jobs, data refreshes daily
  - Remotive   remotive.com/api         link back + name Remotive as the source, at most 4 calls a day
  - Jobicy     jobicy.com/api/v2        credit Jobicy with a link, Apply goes to the original URL
  - RemoteOK   remoteok.com/api         link back to Remote OK + name it; no logo
We never scrape job sites (LinkedIn, Indeed, Rozee); these are official public APIs.

Every source is turned into the same posting shape (see _posting). `pakistan_scope`
decides if a Pakistani can apply: Worldwide / Asia / Pakistan, or a time-zone range
that includes Pakistan (UTC+5). Jobs limited to other countries are NOT shown to users,
but they are still saved: they teach the market model new skills.
"""
import hashlib
import html
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime

from app.config import HIMALAYAS_API_KEY

log = logging.getLogger(__name__)

UA = "CareerPilot-AI/1.0 (remote jobs for Pakistani students)"
TIMEOUT = 25
PK_UTC = 5
SOURCES = {
    "himalayas": {"name": "Himalayas", "site": "https://himalayas.app"},
    "remotive": {"name": "Remotive", "site": "https://remotive.com"},
    "jobicy": {"name": "Jobicy", "site": "https://jobicy.com"},
    "remoteok": {"name": "Remote OK", "site": "https://remoteok.com"},
}


# ------------------------------------------------------------- eligibility --
_OPEN = re.compile(r"\b(worldwide|anywhere|global(ly)?|international|all countries|any ?where in the world)\b", re.I)
_ASIA = re.compile(r"\b(asia|apac|asia[- ]pacific|south asia|pakistan|middle east and asia)\b", re.I)
_PK = re.compile(r"\bpakistan\b", re.I)
_TZ = re.compile(r"(?:utc|gmt)\s*([+-]\s*\d{1,2})(?::\d\d)?\s*(?:to|-|–)\s*(?:utc|gmt)?\s*([+-]\s*\d{1,2})", re.I)


def pakistan_scope(location: str | None) -> str | None:
    """Who can apply, from a free-text location: 'Pakistan', 'Asia', 'Worldwide',
    'Not stated' (no restriction given), or None (limited to places that exclude Pakistan)."""
    text = (location or "").strip()
    if not text or text.lower() in {"remote", "remote job", "100% remote", "fully remote"}:
        return "Not stated"
    if _PK.search(text):
        return "Pakistan"
    if _ASIA.search(text):
        return "Asia"
    if _OPEN.search(text):
        return "Worldwide"
    m = _TZ.search(text)
    if m:
        lo, hi = sorted(int(x.replace(" ", "")) for x in m.groups())
        if lo <= PK_UTC <= hi:
            return "Time zone fits Pakistan"
    return None


def _himalayas_scope(job: dict) -> str | None:
    """Himalayas gives structured lists: countries and UTC offsets (empty = no limit)."""
    countries = job.get("locationRestrictions") or []
    zones = job.get("timezoneRestrictions") or []
    names = [c if isinstance(c, str) else (c.get("name") or "") for c in countries]
    if names and not any(_PK.search(n) for n in names):
        return None
    if zones and not any(abs(float(z) - PK_UTC) < 1 for z in zones):
        return None
    return "Pakistan" if names else "Worldwide"


# ----------------------------------------------------------------- helpers --
def _get(url: str, headers: dict | None = None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.load(r)


_TAG = re.compile(r"<[^>]+>")


def clean_text(s: str | None, limit: int = 6000) -> str:
    """HTML description → plain text (keeps line breaks for lists)."""
    s = re.sub(r"(?i)<\s*(br|/p|/li|/h\d|li)[^>]*>", "\n", s or "")
    s = html.unescape(_TAG.sub(" ", s))
    s = re.sub(r"[ \t\xa0]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()[:limit]


def _epoch(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _posting(source: str, native_id, title, company, location, scope, url, apply_url, description,
             published, tags=None, job_type=None, salary=None, expires=None, category=None) -> dict:
    title = html.unescape(str(title or "")).strip()
    company = html.unescape(str(company or "")).strip()
    return {
        "id": f"{source}:{native_id}",
        "source": source,
        "title": title,
        "company": company,
        "location": (location or "").strip() or "Not stated",
        "scope": scope,                                   # None = not open to Pakistan
        "open_to_pakistan": scope is not None,
        "url": url,                                       # the job on the source site (attribution)
        "apply_url": apply_url or url,                    # unchanged, as the terms require
        "description": clean_text(description),
        "tags": [str(t) for t in _as_list(tags)][:12],
        "job_type": ", ".join(str(t) for t in _as_list(job_type)) or None,
        "salary": salary or None,
        "category": ", ".join(str(c) for c in _as_list(category)) or None,
        "published_at": _epoch(published),
        "expires_at": _epoch(expires),
        "dedupe_key": dedupe_key(title, company),
    }


def dedupe_key(title: str, company: str) -> str:
    norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())  # noqa: E731
    return hashlib.sha1(f"{norm(title)}|{norm(company)}".encode()).hexdigest()[:16]


def _salary(lo, hi, cur=None, period=None) -> str | None:
    try:
        lo, hi = (int(float(x)) if x not in (None, "", 0, "0") else None for x in (lo, hi))
    except (TypeError, ValueError):
        return None
    if not lo and not hi:
        return None
    if (hi or lo) > 2_000_000:                      # obviously wrong numbers in some feeds
        return None
    rng = f"{lo:,}–{hi:,}" if lo and hi and lo != hi else f"{(lo or hi):,}"
    return " ".join(x for x in [cur or "USD", rng, f"/ {period}" if period else ""] if x)


# ----------------------------------------------------------------- sources --
def himalayas(query: str | None = None, pages: int = 5, open_to_pakistan: bool = True) -> list[dict]:
    """Himalayas search. With open_to_pakistan, only jobs a Pakistani can apply to
    (their own country filter: no location limit or Pakistan listed, time zone fits)."""
    headers = {"Authorization": f"Bearer {HIMALAYAS_API_KEY}"} if HIMALAYAS_API_KEY else {}
    out = []
    for page in range(1, pages + 1):
        params = {"sort": "recent", "page": page}
        if query:
            params["q"] = query
        if open_to_pakistan:
            params["country"] = "PK"
        data = _get(f"https://himalayas.app/jobs/api/search?{urllib.parse.urlencode(params)}", headers)
        jobs = data.get("jobs") or []
        for j in jobs:
            expires = _epoch(j.get("expiryDate"))
            if expires and expires < time.time():
                continue                                  # terms: remove expired jobs
            out.append(_posting(
                "himalayas", j.get("guid") or j.get("applicationLink"), j.get("title"), j.get("companyName"),
                ", ".join(c if isinstance(c, str) else c.get("name", "") for c in j.get("locationRestrictions") or [])
                or "Worldwide",
                # their own Pakistan filter already said yes: trust it if our check is unsure
                _himalayas_scope(j) or ("Pakistan" if open_to_pakistan else None),
                j.get("guid"), j.get("applicationLink"),
                j.get("description") or j.get("excerpt"), j.get("pubDate"),
                tags=[str(c).replace("-", " ") for c in j.get("categories") or []],
                job_type=j.get("employmentType"), expires=expires, category=j.get("parentCategories"),
                salary=_salary(j.get("minSalary"), j.get("maxSalary"), j.get("currency"), j.get("salaryPeriod"))))
        if len(jobs) < 20:
            break
    return out


def remotive() -> list[dict]:
    data = _get("https://remotive.com/api/remote-jobs")
    return [_posting("remotive", j["id"], j.get("title"), j.get("company_name"), j.get("candidate_required_location"),
                     pakistan_scope(j.get("candidate_required_location")), j.get("url"), j.get("url"),
                     j.get("description"), j.get("publication_date"), tags=j.get("tags"),
                     job_type=(j.get("job_type") or "").replace("_", " ").title(), salary=j.get("salary") or None,
                     category=j.get("category"))
            for j in data.get("jobs", [])]


def jobicy(count: int = 100) -> list[dict]:
    data = _get(f"https://jobicy.com/api/v2/remote-jobs?count={count}")
    return [_posting("jobicy", j["id"], j.get("jobTitle"), j.get("companyName"), j.get("jobGeo"),
                     pakistan_scope(j.get("jobGeo")), j.get("url"), j.get("url"), j.get("jobDescription"),
                     j.get("pubDate"), tags=j.get("jobIndustry"), job_type=j.get("jobType"),
                     salary=_salary(j.get("salaryMin") or j.get("annualSalaryMin"),
                                    j.get("salaryMax") or j.get("annualSalaryMax"), j.get("salaryCurrency"),
                                    j.get("salaryPeriod")),
                     category=j.get("jobIndustry"))
            for j in data.get("jobs", [])]


def remoteok() -> list[dict]:
    data = _get("https://remoteok.com/api")
    return [_posting("remoteok", j["id"], j.get("position"), j.get("company"), j.get("location"),
                     pakistan_scope(j.get("location")), j.get("url"), j.get("apply_url") or j.get("url"),
                     j.get("description"), j.get("epoch") or j.get("date"), tags=j.get("tags"),
                     salary=_salary(j.get("salary_min"), j.get("salary_max"), "USD", "year"))
            for j in data if isinstance(j, dict) and j.get("id")]      # item 0 is the legal notice


FETCHERS = {"himalayas": himalayas, "remotive": remotive, "jobicy": jobicy, "remoteok": remoteok}


def fetch_all(himalayas_pages: int = 10) -> tuple[list[dict], dict]:
    """Every source once. A source that fails is skipped (logged), never breaks the rest.
    Returns (postings, {source: count or error})."""
    from concurrent.futures import ThreadPoolExecutor
    calls = {
        "himalayas": lambda: himalayas(pages=himalayas_pages),                       # open to Pakistan
        "himalayas_all": lambda: himalayas(pages=3, open_to_pakistan=False),         # any location: learning
        "remotive": remotive, "jobicy": jobicy, "remoteok": remoteok,
    }
    postings, report = [], {}
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = {name: pool.submit(fn) for name, fn in calls.items()}
        for name, f in futures.items():
            try:
                got = f.result()
                postings += got
                report[name] = len(got)
            except Exception as e:
                log.warning("Job source %s failed: %s", name, str(e)[:150])
                report[name] = f"error: {str(e)[:80]}"
    return dedupe(postings), report


def dedupe(postings: list[dict]) -> list[dict]:
    """Same job (title + company) from several sources or pages → keep one; prefer the
    one that is open to Pakistan, then the one with the longer description."""
    best: dict[str, dict] = {}
    for p in postings:
        k = p["dedupe_key"]
        cur = best.get(k)
        if cur is None or (p["open_to_pakistan"], len(p["description"])) > (cur["open_to_pakistan"],
                                                                            len(cur["description"])):
            best[k] = p
    return list(best.values())
