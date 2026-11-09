"""Career matching = ATS Layer 2 (learned keywords) + Layer 3 (SBERT meaning).

    Layer 3 (semantic): the resume and every learned role are turned into SBERT
        vectors; FAISS finds the roles whose meaning is closest (cosine similarity).
    Layer 2 (keywords): of the role's top-20 skills learned from job postings,
        how much (by importance weight) the resume shows. See market_model.py.

    match score = 0.6 * semantic + 0.4 * keyword     (both on a 0-100 scale)

Semantic cosine is rescaled linearly from the band [0.40, 0.85] to 0-100. The band
was measured, not guessed: across 10 real CVs x 521 roles the MEDIAN cosine (a typical
unrelated role) was 0.39 and the best matches reached 0.82 (Day 9).
The band and the 0.6/0.4 weights are re-checked against human ratings on Day 23.
"""
import json
import logging
import re
from functools import lru_cache

import numpy as np

from app.config import DATA_DIR
from app.services import embeddings, market_model
from app.services.entity_extractor import find_skills

log = logging.getLogger(__name__)

INDEX_PATH = DATA_DIR / "role_index.index"
META_PATH = DATA_DIR / "role_index.json"
COS_LOW, COS_HIGH = 0.40, 0.85
W_SEMANTIC, W_KEYWORD = 0.6, 0.4
# A pasted job description lists the employer's skills explicitly, so keywords weigh more there
JD_W_SEMANTIC, JD_W_KEYWORD = 0.4, 0.6
# Roles in a field the user said they're interested in (questionnaire) get a small boost
INTEREST_BONUS = 10
# Two roles whose vectors are this similar are the same career for the user. Measured (Day 12):
# BI Developer~BI Analyst 0.93, Marketing Director~Manager 0.90 (same); Data Scientist~ML
# Engineer 0.78, DevOps~SRE 0.69 (different careers, both kept).
DUP_COS = 0.88


def _family(role: str) -> frozenset:
    """'Full Stack Developer' and 'Full Stack Engineer' are the same career for the user."""
    t = role.lower().replace("developer", "engineer").replace("user experience", "ux")
    return frozenset(t.replace("/", " ").split())


def semantic_score(cos: float) -> int:
    return round(100 * min(1.0, max(0.0, (cos - COS_LOW) / (COS_HIGH - COS_LOW))))


def combine(semantic: int, keyword: int) -> int:
    return round(W_SEMANTIC * semantic + W_KEYWORD * keyword)


# ----------------------------------------------------------------- texts --
def role_text(name: str, profile: dict) -> str:
    skills = ", ".join(s["name"] for s in profile["skills"][:15])
    return f"{name}. Key skills: {skills}."


EVIDENCE_SECTIONS = {"skills", "projects", "experience", "questionnaire", "roadmap"}


def resume_text(entities: dict) -> str:
    """A short 'profile sentence' in the same shape as role_text, so the two compare fairly.
    Skills are ranked by EVIDENCE first (listed / used in projects / used in jobs), then by
    mentions, so a word that only appears in a degree name ("BS Software Engineering") or the
    summary doesn't steer the match. 15 skills, like role_text: more blurs the meaning (Day 12 test)."""
    titles = [j["title"] for j in entities.get("experience", []) if j.get("title")][:4]
    ranked = sorted(entities.get("skills", []),
                    key=lambda s: (-len(EVIDENCE_SECTIONS & set(s.get("sections", []))), -s.get("mentions", 1)))
    skills = [s["name"] for s in ranked][:15]
    parts = [entities.get("headline") or ""]
    if titles:
        parts.append("Job titles: " + ", ".join(titles) + ".")
    parts.append("Key skills: " + ", ".join(skills) + ".")
    projects = [p["title"] for p in entities.get("projects", [])][:3]
    if projects:
        parts.append("Projects: " + "; ".join(projects) + ".")
    return " ".join(p for p in parts if p).strip()


# ------------------------------------------------------------ role index --
@lru_cache(maxsize=1)
def _role_index(model_stamp: str):
    """FAISS index over all learned roles. Saved to disk and reused; rebuilt
    automatically whenever the market model is rebuilt (its built_at changes)."""
    import faiss
    model = market_model.load_model()
    names = list(model["roles"])
    if INDEX_PATH.exists() and META_PATH.exists():
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        if meta.get("stamp") == model_stamp and meta.get("embedding_model") == embeddings.MODEL_NAME:
            return faiss.read_index(str(INDEX_PATH)), meta["roles"]
    log.info("Building role index for %d roles", len(names))
    vecs = embeddings.embed([role_text(n, model["roles"][n]) for n in names])
    index = embeddings.build_index(vecs)
    try:
        faiss.write_index(index, str(INDEX_PATH))
        META_PATH.write_text(json.dumps({"stamp": model_stamp, "embedding_model": embeddings.MODEL_NAME,
                                         "roles": names}), encoding="utf-8")
    except OSError:
        log.warning("Could not save role index (read-only disk?); keeping it in memory")
    return index, names


def role_index():
    model = market_model.load_model()
    if not model:
        return None, []
    return _role_index(model["built_at"])


# --------------------------------------------------------------- matching --
def _skills_of(entities: dict) -> list[str]:
    return [s["name"] for s in entities.get("skills", [])]


def match_careers(entities: dict, top_k: int = 5, candidates: int = 30,
                  interests: set[str] | None = None) -> list[dict] | None:
    """Best-fit careers for a resume. None if the market model isn't built.
    interests = role categories the user picked in the questionnaire: those roles get
    INTEREST_BONUS points, and all roles are scored so roles in those fields can appear
    even when the CV is too short to point to them."""
    index, names = role_index()
    if index is None:
        return None
    query = embeddings.embed([resume_text(entities)])[0]
    skills = _skills_of(entities)
    roles = market_model.load_model()["roles"]
    results = []
    for row, cos in embeddings.search(index, query, len(names) if interests else candidates):
        name = names[row]
        kw = market_model.keyword_coverage(skills, name)
        sem = semantic_score(cos)
        bonus = INTEREST_BONUS if interests and roles[name].get("category") in interests else 0
        results.append({
            "role": name,
            "score": min(100, combine(sem, kw["score"]) + bonus),
            "interest_match": bool(bonus),
            "semantic": sem,
            "keyword": kw["score"],
            "cosine": round(cos, 3),
            "category": roles[name].get("category"),
            "postings_analysed": kw["postings_analysed"],
            "matched_skills": kw["matched"],
            "missing_skills": [m["name"] for m in kw["missing"]][:8],
        })
    results.sort(key=lambda r: -r["score"])
    # Show DIFFERENT careers: skip a role that is a near-copy of a better-ranked one, by name
    # ("Full Stack Developer" / "Engineer") or by meaning (role vectors with cosine >= DUP_COS)
    pos = {n: i for i, n in enumerate(names)}
    unique, seen, picked = [], set(), []
    for r in results:
        fam = _family(r["role"])
        vec = index.reconstruct(pos[r["role"]])
        if fam in seen or any(float(np.dot(vec, p)) >= DUP_COS for p in picked):
            continue
        seen.add(fam)
        picked.append(vec)
        unique.append(r)
        if len(unique) == top_k:
            break
    return unique


def role_match(entities: dict, role: str) -> dict | None:
    """Layer 2 + Layer 3 against ONE chosen role (e.g. the user's target role)."""
    kw = market_model.keyword_coverage(_skills_of(entities), role)
    if kw is None:
        return None
    prof = market_model.load_model()["roles"][kw["role"]]
    a, b = embeddings.embed([resume_text(entities), role_text(kw["role"], prof)])
    sem = semantic_score(float(np.dot(a, b)))
    return {"role": kw["role"], "score": combine(sem, kw["score"]), "semantic": sem, "keyword": kw["score"],
            "matched_skills": kw["matched"], "missing_skills": [m["name"] for m in kw["missing"]][:8],
            "postings_analysed": kw["postings_analysed"]}


def jd_match(entities: dict, job_description: str) -> dict:
    """Match the resume against a job description the user pastes in."""
    jd_skills = find_skills(job_description)
    have = {s.lower() for s in _skills_of(entities)}
    total = sum(v["mentions"] for v in jd_skills.values()) or 1
    matched = [s for s in jd_skills if s.lower() in have]
    missing = sorted((s for s in jd_skills if s.lower() not in have), key=lambda s: -jd_skills[s]["mentions"])
    keyword = round(100 * sum(jd_skills[s]["mentions"] for s in matched) / total) if jd_skills else 0
    # Compare like with like: the JD becomes "<first sentence>. Key skills: ..." (same shape as role_text)
    first = re.split(r"(?<=[.!?])\s|\n", job_description.strip(), maxsplit=1)[0][:200]
    by_mentions = sorted(jd_skills, key=lambda s: -jd_skills[s]["mentions"])
    jd_text = f"{first}. Key skills: {', '.join(by_mentions[:15])}." if jd_skills else job_description[:2000]
    a, b = embeddings.embed([resume_text(entities), jd_text])
    sem = semantic_score(float(np.dot(a, b)))
    return {"score": round(JD_W_SEMANTIC * sem + JD_W_KEYWORD * keyword), "semantic": sem, "keyword": keyword,
            "skills_in_job": len(jd_skills), "matched_skills": matched, "missing_skills": missing[:10]}
