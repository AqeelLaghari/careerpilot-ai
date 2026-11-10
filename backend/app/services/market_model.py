"""Market model: what skills each job role needs, LEARNED from real job postings.

This is ATS Layer 2. Nothing here is hand-written per role: the role list and
each role's skill weights come from `scripts/build_market_model.py`, which reads
job postings and writes `data/market_model.json`. Re-run it on newer postings
and the model updates, with no code change.

How a skill's weight for a role is calculated (TF-IDF over roles):
    freq(skill, role) = share of the role's postings that mention the skill
                        (newer postings count more, see the build script)
    idf(skill)        = log((1 + #roles) / (1 + #roles where the skill is common)) + 1
    weight            = freq * idf, scaled so the role's top skill = 1.0
A skill most roles ask for (e.g. Communication) gets a lower weight than a skill
that is typical for THIS role (e.g. Kubernetes for DevOps Engineer).
"""
import json
import logging
import re
from functools import lru_cache

from pydantic import BaseModel

from app.config import DATA_DIR

log = logging.getLogger(__name__)

MODEL_PATH = DATA_DIR / "market_model.json"

# Words that describe level, contract or place, not the role itself
_NOISE = {
    "senior", "sr", "junior", "jr", "lead", "principal", "staff", "chief", "head", "mid", "level",
    "entry", "i", "ii", "iii", "iv", "v", "1", "2", "3", "remote", "hybrid", "onsite", "on-site",
    "contract", "contractor", "temporary", "temp", "part-time", "full-time", "part", "full", "time",
    "per", "diem", "prn", "night", "shift", "nights", "days", "weekend", "weekends", "experienced",
    "new", "grad", "graduate", "urgent", "hiring", "immediate", "opening", "w2", "only", "travel", "the", "a",
    "intern", "interns", "internship", "summer", "co-op", "coop",
}


# Written in capitals (or special case) after title-casing
_ACRONYMS = {"ux": "UX", "ui": "UI", "ui/ux": "UI/UX", "ux/ui": "UX/UI", "hr": "HR", "it": "IT", "qa": "QA",
             "ai": "AI", "ml": "ML", "bi": "BI", "seo": "SEO", "sql": "SQL", "aws": "AWS", "rn": "RN",
             "lpn": "LPN", "cna": "CNA", "hvac": "HVAC", "plc": "PLC", "erp": "ERP", "crm": "CRM", "ios": "iOS",
             "and": "and", "of": "of", "for": "for", "in": "in", "devops": "DevOps", "fullstack": "Full Stack", "backend": "Backend", "frontend": "Frontend", "cad": "CAD", "ehs": "EHS", "hse": "HSE", "cdl": "CDL", "sap": "SAP", "net": ".NET", "dotnet": ".NET"}


def normalize_title(title: str) -> str:
    """'Sr. Software Engineer II - Backend (Remote)' → 'Software Engineer'."""
    t = str(title or "").lower()
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)                 # drop (Remote), [Contract]
    t = re.split(r"\s[-–—|:]\s|,|\s/\s", t)[0]             # keep the part before ' - ', ',', ' | '
    # Same word, different spelling: "Back-End" / "Back End" → "backend"
    t = re.sub(r"\bback[\s-]?end\b", "backend", t)
    t = re.sub(r"\bfront[\s-]?end\b", "frontend", t)
    t = re.sub(r"\bfull[\s-]?stack\b", "fullstack", t)
    t = re.sub(r"[^a-z0-9+#/&. -]", " ", t).replace(".", " ")
    words = [w for w in t.split() if w not in _NOISE and not w.isdigit()]
    return " ".join(_ACRONYMS.get(w, w.capitalize()) for w in words).strip()


@lru_cache(maxsize=1)
def load_model() -> dict | None:
    """The learned model, or None if it hasn't been built yet."""
    if not MODEL_PATH.exists():
        return None
    return json.loads(MODEL_PATH.read_text(encoding="utf-8"))


def list_roles(query: str = "", limit: int = 50) -> list[dict]:
    model = load_model()
    if not model:
        return []
    q = query.lower().strip()
    roles = [{"role": name, "postings": r["postings"], "category": r.get("category")}
             for name, r in model["roles"].items() if q in name.lower()]
    return sorted(roles, key=lambda r: -r["postings"])[:limit]


def find_role(title: str) -> str | None:
    """Map any job title (e.g. a user's target role) to the closest learned role."""
    model = load_model()
    if not model or not title:
        return None
    roles = model["roles"]
    norm = normalize_title(title)
    if norm in roles:
        return norm
    lower = {r.lower(): r for r in roles}
    if norm.lower() in lower:
        return lower[norm.lower()]
    words = set(norm.lower().split())
    if not words or not roles:
        return None
    squashed = {_squash(r): r for r in roles}                  # "Cybersecurity" = "Cyber Security"
    if _squash(norm) in squashed:
        return squashed[_squash(norm)]
    try:
        hit = _closest_by_meaning(title, model)
        if hit:
            return hit
    except Exception:                                          # embeddings unavailable: words only
        log.warning("Role lookup by meaning failed; using word overlap", exc_info=True)
    # Best word overlap; ties go to the role with more postings
    best = max(roles, key=lambda r: (len(words & set(r.lower().split())) / len(words | set(r.lower().split())),
                                     roles[r]["postings"]))
    overlap = words & set(best.lower().split())
    return best if overlap else None


def _squash(t: str) -> str:
    return re.sub(r"[^a-z0-9+#]", "", t.lower())


# Short forms people type in job titles, spelled out so the language model understands them
_EXPAND = {"ml": "machine learning", "ai": "artificial intelligence", "soc": "security operations center",
           "sre": "site reliability", "qa": "quality assurance", "bi": "business intelligence",
           "hr": "human resources", "dev": "developer", "devs": "developers", "swe": "software engineer",
           "mle": "machine learning engineer", "dba": "database administrator", "ba": "business analyst",
           "pen": "penetration", "sec": "security", "infosec": "information security", "ux": "user experience",
           "ui": "user interface", "it": "information technology", "nlp": "natural language processing",
           "cv": "computer vision", "seo": "search engine optimization", "ca": "chartered accountant",
           "acca": "chartered accountant", "mbbs": "doctor physician", "ece": "electronics engineering"}
NAME_W, PROFILE_W, WORDS_W, MIN_MEANING = 0.55, 0.30, 0.15, 0.5


def _expand(title: str) -> str:
    return " ".join(_EXPAND.get(w, w) for w in re.sub(r"[^a-z0-9+#/ ]", " ", title.lower()).split())


@lru_cache(maxsize=1)
def _role_name_vectors(stamp: str):
    from app.services.embeddings import embed
    names = list(load_model()["roles"])
    return names, embed([_expand(n) for n in names])


def _closest_by_meaning(title: str, model: dict) -> str | None:
    ranked = _rank_by_meaning(title, model)
    if not ranked:
        return None
    name, score, meaning = ranked[0]
    if meaning >= SURE:
        return name
    picked = _gemini_pick(title, tuple(r[0] for r in ranked[:GEMINI_CANDIDATES]))
    if picked is not None:
        return picked or None                                   # "" = Gemini says none fits
    return name if meaning >= MIN_MEANING else None


SURE, GEMINI_CANDIDATES = 0.8, 12


class _Pick(BaseModel):
    role: str


@lru_cache(maxsize=512)
def _gemini_pick(title: str, candidates: tuple[str, ...]) -> str | None:
    """Unsure cases only: Gemini (fast tier) picks the closest of the candidate roles.
    Returns the role, "" if none fits, or None if Gemini is unavailable (caller decides)."""
    from app.services import llm
    out = llm.generate_json(
        f"A user of a career app typed this job title: \"{title}\".\n"
        "Which ONE of these roles is the same job or the closest job to it? "
        "Answer with the role exactly as written, or \"none\" if none is close.\n- " + "\n- ".join(candidates),
        _Pick, tier="fast", temperature=0.0)
    if not out:
        return None
    role = str(out.get("role", "")).strip()
    exact = {c.lower(): c for c in candidates}
    return exact.get(role.lower(), "")


def _rank_by_meaning(title: str, model: dict) -> list[tuple[str, float, float]]:
    """All roles ranked by how close their NAME and SKILL PROFILE are in meaning to the title
    (SBERT), with a little weight on shared words: (role, score, best meaning similarity).
    Handles other spellings, synonyms and short forms: 'Cybersecurity Analyst' → Cyber
    Security Analyst, 'Doctor' → Physician. Unsure cases go to Gemini (see above)."""
    from app.services import career_matcher
    from app.services.embeddings import embed
    names, name_vecs = _role_name_vectors(model["built_at"])
    q = embed([_expand(title)])[0]
    name_cos = name_vecs @ q
    index, idx_names = career_matcher.role_index()
    profile_cos = {}
    if index is not None:
        sims, ids = index.search(q.reshape(1, -1), len(idx_names))
        profile_cos = {idx_names[i]: float(s) for s, i in zip(sims[0], ids[0]) if i >= 0}
    words = set(_expand(title).split())
    ranked = []
    for name, nc in zip(names, name_cos):
        rw = set(_expand(name).split())
        pc = profile_cos.get(name, 0.0)
        score = NAME_W * float(nc) + PROFILE_W * pc + WORDS_W * len(words & rw) / len(words | rw)
        ranked.append((name, score, max(float(nc), pc)))
    return sorted(ranked, key=lambda r: -r[1])


def role_profile(role: str) -> dict | None:
    model = load_model()
    name = find_role(role)
    return {"role": name, **model["roles"][name]} if name else None


def keyword_coverage(resume_skills: list[str], role: str, top_n: int = 20) -> dict | None:
    """ATS Layer 2 score: how many of the role's most important skills the resume shows,
    weighted by importance. Returns None if the role is unknown or the model is missing."""
    prof = role_profile(role)
    if not prof:
        return None
    have = {s.lower() for s in resume_skills}
    top = prof["skills"][:top_n]
    total = sum(s["weight"] for s in top) or 1
    matched = [s for s in top if s["name"].lower() in have]
    missing = [s for s in top if s["name"].lower() not in have]
    return {
        "role": prof["role"],
        "postings_analysed": prof["postings"],
        "score": round(100 * sum(s["weight"] for s in matched) / total),
        "matched": [s["name"] for s in matched],
        "missing": [{"name": s["name"], "share_of_postings": s["freq"], "weight": s["weight"]} for s in missing],
        "method": "TF-IDF skill importance learned from job postings",
    }
