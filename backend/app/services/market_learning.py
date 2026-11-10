"""Self-learning market model (Day 14, part 3).

Job-market data goes stale, so once a week the app learns from the live postings it has
saved (Firestore "job_postings", see live_jobs.py), with no code change or redeploy:

1. NEW SKILLS. Terms that many recent postings use (tags, and items in skill lists such
   as "Experience with Snowflake, dbt, Airflow") but that the skill detector does not know
   become candidates (MIN_POSTINGS+ postings, minus a blocklist of words like "Urgent").
   Gemini (fast tier) checks ALL candidates in ONE batched call: is it a real skill, its
   proper name, its category. A new spelling of a known skill becomes an alias.
   Rule-based fallback: if Gemini is unavailable nothing is added automatically; the
   candidates wait as "pending" for an admin (and Gemini is asked again next week).
2. HOT RELOAD. Approved skills are stored (Firestore doc market_learning/state + a local
   file) and swapped into the skill detector while the server runs.
3. TRENDS. Demand share of every skill in recent postings, newer postings weighted more
   (half-life TREND_HALF_LIFE days); rising / falling = last RECENT_DAYS vs the weeks before.
4. RE-WEIGHT. For each learned role, the skill shares in live postings are blended into
   the role's keyword weights (market_model.set_live_roles), so ATS Layer 2, career
   matching and roadmaps follow the current market.
Oversight: an admin can list learned skills, approve pending ones and remove wrong ones
(removed terms are never learned again).

Trigger: lazy. After a jobs refresh (or at start-up) the learner runs in the background
if the last run is more than LEARN_EVERY_DAYS old, so it works on free hosting that sleeps.
"""
import json
import logging
import re
import threading
import time
from collections import Counter, defaultdict

from pydantic import BaseModel

from app.config import DATA_DIR
from app.services import entity_extractor, llm, market_model

log = logging.getLogger(__name__)

LEARN_EVERY_DAYS = 7
MIN_POSTINGS = 15            # a term must appear in at least this many postings
MAX_CANDIDATES = 120         # sent to Gemini in one call
WINDOW_DAYS = 60             # postings used for learning and trends
RECENT_DAYS = 14             # "now" window for rising / falling
TREND_HALF_LIFE = 14         # a posting this many days old counts half
MIN_HISTORY = 30             # postings needed in the older window before rising/falling is shown
LIVE_ROLE_MIN = 10           # live postings a role needs before its weights are re-weighted
MAX_POSTINGS_READ = 8000     # Firestore reads per run (free tier: 50k reads a day)
STATE_FILE = DATA_DIR / "raw" / "market_learning.json"     # quick restart cache (git-ignored)
COLLECTION, STATE_DOC = "market_learning", "state"

# Words that are frequent in postings but are never skills
BLOCKLIST = {
    "urgent", "hybrid", "remote", "onsite", "on-site", "full time", "full-time", "part time", "part-time",
    "contract", "freelance", "internship", "intern", "senior", "junior", "lead", "manager", "engineer",
    "developer", "experience", "years", "team", "teams", "benefits", "salary", "bonus", "equity", "pto",
    "health insurance", "401k", "401(k)", "dental", "vision", "visa", "relocation", "worldwide", "anywhere",
    "usa", "us", "uk", "eu", "europe", "emea", "apac", "latam", "asia", "canada", "india", "pakistan",
    "germany", "remote first", "work from home", "wfh", "flexible hours", "startup", "saas", "b2b", "b2c",
    "english", "degree", "bachelor", "master", "phd", "etc", "e.g", "i.e", "other", "others", "more",
    "software", "development", "engineering", "design", "marketing", "sales", "support", "operations",
    "finance", "product", "data", "business", "customer", "technology", "tech", "it", "dev", "digital",
    "non-tech", "exec", "management", "admin", "general", "all others", "and more", "jobs", "job", "web",
    # equal-opportunity statements ("race, color, religion, age, ...") are lists too
    "race", "color", "colour", "religion", "creed", "sex", "gender", "gender identity", "age", "disability",
    "veteran", "veteran status", "national origin", "ancestry", "sexual orientation", "pregnancy",
    "marital status", "genetic information", "citizenship", "ethnicity",
}
MIN_NAME_CASE = 0.5          # a term from text must be written like a name in MORE than half its uses
_STOP = None

_state: dict = {"last_run": 0.0, "skills": [], "rejected": [], "trends": {}, "role_live": {}, "report": {}}
_lock = threading.Lock()
_running = threading.Event()
_loaded = False


def _db():
    from app.deps import blackboard
    return blackboard._db


# ------------------------------------------------------------- state I/O --
def _stopwords() -> set[str]:
    global _STOP
    if _STOP is None:
        from spacy.lang.en.stop_words import STOP_WORDS
        _STOP = set(STOP_WORDS)
    return _STOP


def load_state():
    """At start-up: local file first (fast), then Firestore (shared by every server)."""
    global _loaded
    data = None
    try:
        db = _db()
        if db is not None:
            doc = db.collection(COLLECTION).document(STATE_DOC).get()
            data = doc.to_dict() if doc.exists else None
    except Exception:
        log.warning("Reading learned skills from Firestore failed; using the local copy", exc_info=True)
    if data is None and STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
    if data:
        with _lock:
            _state.update(data)
    _loaded = True
    apply()


def _save():
    with _lock:
        data = json.loads(json.dumps(_state))
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass
    try:
        db = _db()
        if db is not None:
            db.collection(COLLECTION).document(STATE_DOC).set(data)
    except Exception:
        log.warning("Saving learned skills to Firestore failed", exc_info=True)


def apply():
    """Put the approved skills into the skill detector and the live role weights into
    the market model (both swap in while the server runs)."""
    with _lock:
        approved = [{"name": s["name"], "category": s["category"], "aliases": s.get("aliases", [])}
                    for s in _state["skills"] if s.get("status") == "approved"]
        role_live = dict(_state.get("role_live") or {})
    entity_extractor.set_learned_skills(approved)
    market_model.set_live_roles(role_live)


# -------------------------------------------------------------- trigger --
def maybe_learn(force: bool = False) -> bool:
    """Start a learning run in the background if the last one is older than a week.
    True if a run is (now) going on."""
    if not _loaded:
        load_state()
    due = time.time() - _state.get("last_run", 0) > LEARN_EVERY_DAYS * 86400
    if (force or due) and not _running.is_set():
        _running.set()
        threading.Thread(target=_background, daemon=True).start()
    return _running.is_set()


def _background():
    try:
        learn()
    except Exception:
        log.exception("Market learning run failed")
    finally:
        _running.clear()


# ------------------------------------------------------------- postings --
def _load_postings() -> list[dict]:
    """Recent saved postings (any location: US-only jobs still teach skills)."""
    cutoff = time.time() - WINDOW_DAYS * 86400
    db = _db()
    if db is not None:
        try:
            docs = (db.collection("job_postings").where("fetched_at", ">=", cutoff)
                    .limit(MAX_POSTINGS_READ).stream())
            return [d.to_dict() for d in docs]
        except Exception:
            log.warning("Reading postings from Firestore failed; using the jobs in memory", exc_info=True)
    from app.services import live_jobs                     # no database: the jobs we have
    with live_jobs._lock:
        return list(live_jobs._pool["jobs"].values())


def _when(p: dict) -> float:
    return p.get("published_at") or p.get("fetched_at") or time.time()


# ------------------------------------------------------- 1. new skills --
_ITEM_SPLIT = re.compile(r"\s*(?:,|;|/|\||\band\b|\bor\b|•|·|\(|\))\s*")
_LEAD = re.compile(r"^(?:experience (?:with|in)|knowledge of|familiarity with|proficiency (?:with|in)|"
                   r"skills? in|e\.g\.?|such as|including|like|using|with|in|of|tools?:?|frameworks?:?)\s+", re.I)
_TERM_OK = re.compile(r"^[A-Za-z][A-Za-z0-9.+#\- ]{0,28}[A-Za-z0-9+#]$|^[A-Za-z]$")


def _list_items(text: str) -> set[str]:
    """Items of skill-like lists in a description: lines/sentences with 2+ commas."""
    out = set()
    for line in re.split(r"[\n.](?=\s|$)", text):
        if line.count(",") < 2:
            continue
        for item in _ITEM_SPLIT.split(line):
            item = re.sub(r"^[A-Za-z ]{1,25}:\s*", "", item.strip(" -*'\""))   # "Stack: React" → "React"
            item = _LEAD.sub("", item.strip(" -:")).strip()
            words = item.split()
            if not 1 <= len(words) <= 3 or not _TERM_OK.match(item):
                continue
            # skill names are written like names: capital letter, or code-like (k8s, .js, C#)
            if not (item[0].isupper() or re.search(r"[0-9.+#]", item)):
                continue
            out.add(item)
    return out


def _known_terms() -> set[str]:
    known = set()
    for entries in entity_extractor.skill_vocab().values():
        for e in entries:
            known.update(a.lower() for a in e.lstrip("!").split("|"))
    return known


def find_candidates(postings: list[dict], min_postings: int = MIN_POSTINGS) -> list[dict]:
    """Terms in at least `min_postings` postings that the detector doesn't know yet."""
    with _lock:
        seen = ({s["name"].lower() for s in _state["skills"]}
                | {a.lower() for s in _state["skills"] for a in s.get("aliases", [])}
                | set(_state.get("rejected", [])))
    known = _known_terms() | seen
    companies = {str(p.get("company") or "").lower().strip() for p in postings}
    stop = _stopwords()
    count, spelling, from_tag = Counter(), defaultdict(Counter), set()
    for p in postings:
        keys = set()
        tags = {str(t).strip() for t in p.get("tags") or []}
        from_tag.update(re.sub(r"\s+", " ", t.lower()).strip() for t in tags)
        for t in tags | _list_items(p.get("description") or ""):
            key = re.sub(r"\s+", " ", t.lower()).strip()
            if (len(key) < 2 or key in known or key in BLOCKLIST or key in companies or key.isdigit()
                    or all(w in stop for w in key.split())):
                continue
            spelling[key][t] += 1
            keys.add(key)
        count.update(keys)                            # once per posting
    frequent = [k for k, n in count.most_common() if n >= min_postings]
    text = "\n".join(p.get("description") or "" for p in postings)
    cands = []
    for k in frequent:
        # Ordinary words ("build", "security") are mostly written in lower case in the text;
        # tool names ("Snowflake", "Next.js") keep their spelling. Tags are already curated.
        if k not in from_tag and not re.search(r"[0-9.+#]", k):
            uses = re.findall(rf"(?<![\w.+#-]){re.escape(k)}(?![\w+#-])", text, re.I)
            if uses and sum(u == u.lower() for u in uses) / len(uses) >= 1 - MIN_NAME_CASE:
                continue
        # most used spelling; on a tie the one written with capitals ("Zorblex", not the tag "zorblex")
        term = max(spelling[k].items(), key=lambda x: (x[1], sum(ch.isupper() for ch in x[0])))[0]
        cands.append({"term": term, "postings": count[k], "tag": k in from_tag})
    return cands[:MAX_CANDIDATES]


def looks_like_spelling_of(term: str, name: str) -> bool:
    """Only accept 'term is another spelling of skill X' when it looks like X's name:
    'ReactJS' → React, 'Postgres' → PostgreSQL, 'k8s'-style short forms need capitals or digits.
    A general word ('security', 'testing') is never a spelling of a specific skill."""
    from difflib import SequenceMatcher
    a, b = re.sub(r"[^a-z0-9+#]", "", term.lower()), re.sub(r"[^a-z0-9+#]", "", name.lower())
    if not a or not b:
        return False
    if term.isalpha() and term.islower() and len(term) > 3 and a not in b[:len(a) + 1]:
        return False                                  # plain lower-case word
    if term.isalpha() and term[:1].isupper() and term[1:].islower() and b.endswith(a) and a != b:
        return False                                  # "Security" is not "Cybersecurity"
    return a in b or b in a or SequenceMatcher(None, a, b).ratio() >= 0.75


class _Verdict(BaseModel):
    term: str
    is_skill: bool
    name: str
    category: str


class _Review(BaseModel):
    items: list[_Verdict]


def review(cands: list[dict]) -> list[dict] | None:
    """ONE Gemini call for every candidate. None if Gemini is unavailable."""
    if not cands:
        return []
    categories = sorted(entity_extractor.skill_vocab())
    known = sorted({e.lstrip("!").split("|")[0] for lst in entity_extractor.skill_vocab().values() for e in lst})
    prompt = (
        "These terms appear in many recent job postings. For EACH term decide if it is a real, "
        "learnable professional skill, tool, technology, method or certification that would belong "
        "in a resume's skills section. NOT skills: job titles, company or product brand names that are "
        "not tools, places, benefits, contract types, seniority, industries, generic words.\n"
        "General words are NOT skills even if they sound technical: 'security', 'testing', 'deployment', "
        "'content', 'APIs', 'automation' are too general on their own (is_skill = false).\n"
        "For skills give `name` = the standard spelling (e.g. 'dbt', 'Next.js', 'Power BI'). If the term is "
        "just another way of writing a skill in KNOWN SKILLS (e.g. 'ReactJS' = React, 'k8s' = Kubernetes), "
        "give that known skill's exact name. Never map a general word to a more specific skill.\n"
        f"`category` must be one of: {', '.join(categories)}.\n"
        f"KNOWN SKILLS (short list): {', '.join(known[:400])}\n"
        "TERMS (with number of postings):\n" + "\n".join(f"- {c['term']} ({c['postings']})" for c in cands))
    out = llm.generate_json(prompt, _Review, tier="fast", temperature=0.0)
    if not out:
        return None
    by_term = {c["term"].lower(): c for c in cands}
    verdicts = []
    for v in out.get("items", []):
        c = by_term.get(str(v.get("term", "")).lower())
        if c:
            verdicts.append(v | {"postings": c["postings"], "term": c["term"]})
    return verdicts


def _merge_verdicts(cands: list[dict], verdicts: list[dict] | None) -> dict:
    """Store Gemini's answers. Returns {added, aliases, rejected, pending}."""
    categories = set(entity_extractor.skill_vocab())
    known = {e.lstrip("!").split("|")[0].lower(): e.lstrip("!").split("|")[0]
             for lst in entity_extractor.skill_vocab().values() for e in lst}
    now = time.time()
    rep = {"added": [], "aliases": [], "rejected": 0, "pending": 0}
    with _lock:
        skills = {s["name"].lower(): s for s in _state["skills"]}
        rejected = set(_state.get("rejected", []))
        removed = {k for k, s in skills.items() if s.get("status") == "removed"}
        if verdicts is None:                                  # fallback: wait for an admin
            for c in cands:
                if c["term"].lower() not in skills:
                    skills[c["term"].lower()] = {"name": c["term"], "category": None, "aliases": [],
                                                 "postings": c["postings"], "status": "pending",
                                                 "added_at": now, "by": "rules (Gemini unavailable)"}
                    rep["pending"] += 1
        else:
            answered = set()
            for v in verdicts:
                term, name = v["term"], str(v.get("name") or v["term"]).strip()
                answered.add(term.lower())
                if skills.get(term.lower(), {}).get("status") == "pending":
                    del skills[term.lower()]          # Gemini has now decided
                if not v.get("is_skill") or not name or "|" in name or term.lower() in removed:
                    rejected.add(term.lower())
                    rep["rejected"] += 1
                    continue
                if name.lower() in known:                     # new spelling of a known skill
                    name = known[name.lower()]
                    if term.lower() != name.lower() and not looks_like_spelling_of(term, name):
                        rejected.add(term.lower())            # e.g. "security" → Cybersecurity: no
                        rep["rejected"] += 1
                        continue
                    cat = next(c for c, lst in entity_extractor.skill_vocab().items()
                               if any(e.lstrip("!").split("|")[0] == name for e in lst))
                    kind = "aliases"
                elif v.get("category") in categories:
                    cat, kind = v["category"], "added"
                else:
                    rejected.add(term.lower())
                    rep["rejected"] += 1
                    continue
                s = skills.setdefault(name.lower(), {"name": name, "category": cat, "aliases": [],
                                                     "postings": 0, "status": "approved", "added_at": now,
                                                     "by": "Gemini"})
                if s.get("status") == "removed":
                    continue
                if term.lower() != name.lower() and term not in s["aliases"]:
                    s["aliases"].append(term)
                s["postings"] = max(s["postings"], v["postings"])
                rep[kind].append(name if kind == "added" else f"{term} → {name}")
        _state["skills"] = sorted(skills.values(), key=lambda s: -s.get("postings", 0))
        _state["rejected"] = sorted(rejected)[-3000:]
    return rep


# -------------------------------------------- 3. trends + 4. re-weight --
def compute_trends(postings: list[dict], now: float | None = None) -> dict:
    """Demand share of each skill (newer postings weigh more) and what is rising/falling."""
    now = now or time.time()
    found = list(entity_extractor.find_skills_batch(
        f"{p.get('title', '')}\n{' , '.join(p.get('tags') or [])}\n{p.get('description') or ''}" for p in postings))
    weight_sum, demand, recent, older = 0.0, Counter(), Counter(), Counter()
    n_recent = n_older = 0
    cats = {}
    for p, skills in zip(postings, found):
        age = max(0.0, (now - _when(p)) / 86400)
        w = 0.5 ** (age / TREND_HALF_LIFE)
        weight_sum += w
        is_recent = age <= RECENT_DAYS
        n_recent += is_recent
        n_older += not is_recent
        for s, cat in skills.items():
            if cat == "soft_skills":
                continue
            cats[s] = cat
            demand[s] += w
            (recent if is_recent else older)[s] += 1
    total = weight_sum or 1
    top = [{"name": s, "category": cats[s], "share": round(100 * v / total, 1),
            "postings": recent[s] + older[s]} for s, v in demand.most_common(25)]
    rising, falling = [], []
    history = n_older >= MIN_HISTORY and n_recent >= MIN_HISTORY
    if history:
        for s in set(recent) | set(older):
            if recent[s] + older[s] < 8:
                continue
            a, b = 100 * recent[s] / n_recent, 100 * older[s] / n_older
            change = round(a - b, 1)
            item = {"name": s, "category": cats[s], "share_now": round(a, 1), "share_before": round(b, 1),
                    "change": change}
            if change >= 1 and a >= 1.5 * b:
                rising.append(item)
            elif change <= -1 and b >= 1.5 * a:
                falling.append(item)
    rising.sort(key=lambda r: -r["change"])
    falling.sort(key=lambda r: r["change"])
    return {"top": top, "rising": rising[:15], "falling": falling[:15], "postings": len(postings),
            "recent_postings": n_recent, "history_ready": history, "window_days": WINDOW_DAYS,
            "computed_at": now}, found


def live_role_shares(postings: list[dict], found: list[dict]) -> dict:
    """{role: {"postings": n, "freq": {skill: share}}} for learned roles with enough live postings.
    Titles are matched to roles by name only (cheap, no Gemini)."""
    model = market_model.load_model()
    if not model:
        return {}
    lower = {r.lower(): r for r in model["roles"]}
    per_role: dict[str, list[dict]] = defaultdict(list)
    for p, skills in zip(postings, found):
        role = lower.get(market_model.normalize_title(p.get("title", "")).lower())
        if role:
            per_role[role].append(skills)
    out = {}
    for role, lst in per_role.items():
        if len(lst) < LIVE_ROLE_MIN:
            continue
        c = Counter(s for skills in lst for s in skills)
        out[role] = {"postings": len(lst), "freq": {s: round(n / len(lst), 3) for s, n in c.items()
                                                     if n / len(lst) >= 0.05}}
    return out


# ------------------------------------------------------------------ run --
def learn(postings: list[dict] | None = None) -> dict:
    """One learning run: new skills → reload → trends → role re-weighting → save."""
    t = time.time()
    if not _loaded:
        load_state()
    postings = _load_postings() if postings is None else postings
    cands = find_candidates(postings)
    with _lock:                                       # pending ones get another chance with Gemini
        pending = [{"term": s["name"], "postings": s.get("postings", 0)} for s in _state["skills"]
                   if s.get("status") == "pending" and s.get("by", "").startswith("rules")]
    todo = (cands + [p for p in pending if p["term"].lower() not in {c["term"].lower() for c in cands}])
    verdicts = review(todo[:MAX_CANDIDATES]) if todo else []
    rep = _merge_verdicts(todo[:MAX_CANDIDATES], verdicts)
    apply()                                           # new skills count from now on
    trends, found = compute_trends(postings)
    role_live = live_role_shares(postings, found)
    with _lock:
        _state["trends"] = trends | {"new_skills": rep["added"]}
        _state["role_live"] = role_live
        _state["last_run"] = time.time()
        _state["report"] = {"postings": len(postings), "candidates": len(todo), **{k: (v if isinstance(v, int)
                            else len(v)) for k, v in rep.items()}, "roles_reweighted": len(role_live),
                            "gemini": verdicts is not None, "seconds": round(time.time() - t, 1)}
    market_model.set_live_roles(role_live)
    _save()
    log.info("Market learning done: %s; new skills: %s", _state["report"], rep["added"][:20])
    return dict(_state["report"]) | {"added": rep["added"], "aliases": rep["aliases"]}


# ---------------------------------------------------------------- admin --
def learned_skills() -> dict:
    if not _loaded:
        load_state()
    with _lock:
        return {"skills": [dict(s) for s in _state["skills"]], "last_run": _state.get("last_run") or None,
                "running": _running.is_set(), "report": dict(_state.get("report") or {})}


def set_status(name: str, status: str, category: str | None = None) -> dict | None:
    """Admin: 'approved' (needs a category for pending ones) or 'removed' (never learned again)."""
    if not _loaded:
        load_state()
    with _lock:
        s = next((s for s in _state["skills"] if s["name"].lower() == name.lower()), None)
        if s is None:
            return None
        if status == "approved":
            cat = category or s.get("category")
            if cat not in entity_extractor.skill_vocab():
                raise ValueError(f"category must be one of: {', '.join(sorted(entity_extractor.skill_vocab()))}")
            s["category"] = cat
        s["status"] = status
        s["by"] = f"admin ({status})"
        if status == "removed":
            _state["rejected"] = sorted(set(_state.get("rejected", [])) | {s["name"].lower()}
                                        | {a.lower() for a in s.get("aliases", [])})
        result = dict(s)
    apply()
    _save()
    return result


def trends() -> dict:
    if not _loaded:
        load_state()
    with _lock:
        return dict(_state.get("trends") or {}) | {"last_run": _state.get("last_run") or None,
                                                    "running": _running.is_set()}

