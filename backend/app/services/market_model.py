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
import re
from functools import lru_cache

from app.config import DATA_DIR

MODEL_PATH = DATA_DIR / "market_model.json"

# Words that describe level, contract or place, not the role itself
_NOISE = {
    "senior", "sr", "junior", "jr", "lead", "principal", "staff", "chief", "head", "mid", "level",
    "entry", "i", "ii", "iii", "iv", "v", "1", "2", "3", "remote", "hybrid", "onsite", "on-site",
    "contract", "contractor", "temporary", "temp", "part-time", "full-time", "part", "full", "time",
    "per", "diem", "prn", "night", "shift", "nights", "days", "weekend", "weekends", "experienced",
    "new", "grad", "graduate", "urgent", "hiring", "immediate", "opening", "w2", "only", "travel", "the", "a",
}


def normalize_title(title: str) -> str:
    """'Sr. Software Engineer II - Backend (Remote)' → 'Software Engineer'."""
    t = str(title or "").lower()
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)                 # drop (Remote), [Contract]
    t = re.split(r"\s[-–—|:]\s|,|\s/\s", t)[0]             # keep the part before ' - ', ',', ' | '
    t = re.sub(r"[^a-z0-9+#/&. -]", " ", t).replace(".", " ")
    words = [w for w in t.split() if w not in _NOISE and not w.isdigit()]
    return " ".join(words).title().replace("Ui/Ux", "UI/UX").replace("Hr ", "HR ").strip()


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
    # Best word overlap; ties go to the role with more postings
    best = max(roles, key=lambda r: (len(words & set(r.lower().split())) / len(words | set(r.lower().split())),
                                     roles[r]["postings"]))
    overlap = words & set(best.lower().split())
    return best if overlap else None


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
