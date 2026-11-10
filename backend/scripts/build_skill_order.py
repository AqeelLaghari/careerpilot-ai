"""Build data/skill_order.json: the learning order of skills, with Gemini, offline.

Run once (and again after the market model gains new roles or skills):
    python -m scripts.build_skill_order

What it asks Gemini (fast tier, batched, about 100 calls in total):
  1. A LEVEL for every skill in skills.json:
       1 = basic / foundation   2 = core   3 = advanced / specialised   4 = umbrella field
  2. For every learned role: "learn A before B" pairs among that role's top skills.

Nothing from Gemini is trusted blindly:
  - only skill names that exist in skills.json are kept (case-insensitive);
  - a pair proposed for many roles gets more votes; when A→B and B→A are both proposed,
    the side with more votes wins (a tie is dropped);
  - a pair whose "before" skill is MORE advanced (higher level) than its "after" skill is
    dropped (e.g. "Data Science before Machine Learning": a whole field before one of its parts);
  - roadmap.py adds these pairs after the hand-written graph and skips any pair that
    would create a cycle, so the hand-written rules always win;
  - the pairs only ORDER skills already in a plan; they never add new skills to it, because
    a pair can be true for one role and not another (Patient Care before Monitoring is
    right for a nurse, not for a DevOps engineer).

Progress is saved after every call to data/raw/ (git-ignored), so a rerun after a quota
error continues where it stopped.
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import llm, market_model  # noqa: E402
from app.services.roadmap import DATA_DIR, SOFT, _skill_categories  # noqa: E402

OUT = DATA_DIR / "skill_order.json"
PROGRESS = DATA_DIR / "raw" / "skill_order_progress.json"
LEVEL_BATCH, ROLE_BATCH, SKILLS_PER_ROLE = 70, 6, 15
PAUSE = 4.5                       # seconds between calls: stays under the free per-minute limit


class SkillLevel(BaseModel):
    skill: str
    level: int


class Levels(BaseModel):
    items: list[SkillLevel]


class Pair(BaseModel):
    before: str
    after: str


class RolePairs(BaseModel):
    role: str
    pairs: list[Pair]


class RoleBatch(BaseModel):
    roles: list[RolePairs]


LEVEL_PROMPT = """You are designing learning paths for a career guidance app.
Give each skill below a learning LEVEL:
1 = basic / foundation: learned first, needs nothing else (e.g. Python, SQL, Microsoft Excel,
    Linear Algebra, Probability, HTML, Customer Service, Bookkeeping, Anatomy)
2 = core working skill that builds on basics (e.g. Statistics, Git, Pandas, Docker, Data Analysis)
3 = advanced or specialised, needs several core skills first (e.g. Deep Learning, Kubernetes,
    Natural Language Processing, Financial Modeling)
4 = umbrella field or whole discipline made of many skills (e.g. Data Science, DevOps,
    Artificial Intelligence, Cybersecurity, Software Engineering)
Return every skill exactly as written, each once.

Skills:
{skills}"""

PAIR_PROMPT = """You are designing learning paths for a career guidance app.
For each job role below, look at its skill list and return the prerequisite pairs:
"before" must genuinely be learned before a learner can properly start "after".
Rules:
- Use ONLY skill names from that role's own list, written exactly as given.
- Include real dependencies, e.g. Python before Machine Learning, Statistics before Machine
  Learning, Machine Learning before Deep Learning, Docker before Kubernetes, Bookkeeping before
  Financial Reporting.
- An umbrella field comes AFTER the skills it is made of (e.g. Python before Data Science,
  Statistics before Data Science, Linux before DevOps).
- Do NOT pair skills that can be learned independently.

Roles:
{roles}"""


def _load_progress() -> dict:
    if PROGRESS.exists():
        return json.loads(PROGRESS.read_text(encoding="utf-8"))
    return {"levels": {}, "role_pairs": {}}


def _save_progress(p: dict):
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(p, indent=1), encoding="utf-8")


def _ask(prompt: str, schema):
    for attempt in range(3):
        out = llm.generate_json(prompt, schema, tier="fast", temperature=0.1)
        time.sleep(PAUSE)
        if out is not None:
            return out
        print(f"  Gemini gave nothing (attempt {attempt + 1}); waiting 60 s…")
        time.sleep(60)
    return None


def role_skills(model: dict) -> dict[str, list[str]]:
    out = {}
    for role in model["roles"]:
        prof = market_model.role_profile(role)
        out[role] = [s["name"] for s in prof["skills"] if s.get("category") != SOFT][:SKILLS_PER_ROLE]
    return out


def collect(progress: dict, names: list[str], roles: dict[str, list[str]]):
    todo = [s for s in names if s not in progress["levels"]]
    for i in range(0, len(todo), LEVEL_BATCH):
        batch = todo[i:i + LEVEL_BATCH]
        out = _ask(LEVEL_PROMPT.format(skills="\n".join(batch)), Levels)
        if out is None:
            print("Stopping: Gemini unavailable. Run again later to continue.")
            return False
        for it in out["items"]:
            if it["skill"] in batch and 1 <= it["level"] <= 4:
                progress["levels"][it["skill"]] = it["level"]
        _save_progress(progress)
        print(f"levels: {len(progress['levels'])}/{len(names)}")

    todo = [r for r, sk in roles.items() if r not in progress["role_pairs"] and len(sk) >= 2]
    for i in range(0, len(todo), ROLE_BATCH):
        batch = todo[i:i + ROLE_BATCH]
        text = "\n".join(f"- {r}: {', '.join(roles[r])}" for r in batch)
        out = _ask(PAIR_PROMPT.format(roles=text), RoleBatch)
        if out is None:
            print("Stopping: Gemini unavailable. Run again later to continue.")
            return False
        got = {x["role"]: x["pairs"] for x in out["roles"]}
        for r in batch:
            progress["role_pairs"][r] = [[p["before"], p["after"]] for p in got.get(r, [])]
        _save_progress(progress)
        print(f"roles: {len(progress['role_pairs'])}/{len(roles)}")
    return True


def combine(progress: dict, names: list[str], roles: dict[str, list[str]]) -> dict:
    canon = {n.lower(): n for n in names}
    levels = {canon[s.lower()]: lv for s, lv in progress["levels"].items() if s.lower() in canon}
    votes, dropped = Counter(), Counter()
    for role, pairs in progress["role_pairs"].items():
        allowed = {s.lower() for s in roles.get(role, [])}
        for a, b in pairs:
            a_l, b_l = a.lower(), b.lower()
            if a_l == b_l or a_l not in allowed or b_l not in allowed:
                dropped["not in the role's list"] += 1
                continue
            votes[(canon[a_l], canon[b_l])] += 1
    edges = []
    for (a, b), n in votes.items():
        back = votes.get((b, a), 0)
        if back >= n:                                  # contradicted at least as often
            dropped["contradicted"] += 1
            continue
        if levels.get(a, 2) > levels.get(b, 2):        # e.g. a whole field before one of its parts
            dropped["level makes no sense"] += 1
            continue
        edges.append([a, b, n - back])
    edges.sort(key=lambda e: (-e[2], e[0], e[1]))
    return {"built_at": time.strftime("%Y-%m-%d"), "model": llm.MODELS["fast"],
            "levels_meaning": {"1": "basic", "2": "core", "3": "advanced", "4": "umbrella field"},
            "levels": dict(sorted(levels.items())), "edges": edges,
            "stats": {"skills_levelled": len(levels), "roles": len(progress["role_pairs"]),
                      "edges": len(edges), "dropped": dict(dropped)}}


def main():
    if not llm.available():
        sys.exit("Set GEMINI_API_KEY in backend/.env first.")
    model = market_model.load_model()
    names = sorted(_skill_categories())
    roles = role_skills(model)
    progress = _load_progress()
    done = collect(progress, names, roles)
    result = combine(progress, names, roles)
    OUT.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result["stats"], indent=1))
    if not done:
        print("Partial result saved; run again to finish.")


if __name__ == "__main__":
    main()
