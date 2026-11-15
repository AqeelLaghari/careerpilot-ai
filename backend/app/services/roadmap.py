"""Skill gap + learning roadmap (Career Guide Agent, Day 11).

1. Skill gap = set difference
       role skills (learned from job postings, most important first)
     − skills the user has (resume + skills confirmed in the questionnaire)
     + skills the user rated "beginner" (to improve, at half the effort)
2. Prerequisites: a directed graph (networkx DiGraph) of "learn A before B":
     - hand-checked edges from data/skill_graph.json (like a course syllabus), plus
     - edges built OFFLINE with Gemini for every role's skill list (data/skill_order.json,
       scripts/build_skill_order.py): validated names, voted across roles, and
     - edges LEARNED from job postings by co-occurrence asymmetry (market_model.json).
       Each extra edge is added only if it doesn't create a cycle; hand-checked edges win,
       then Gemini edges (most votes first), then learned ones.
   Missing foundations of each gap skill are added (walking back until a skill the
   user already knows), so the plan never says "Kubernetes" before "Docker".
3. Order: topological sort of the gap subgraph (a DAG). Among skills that are free
   to go next: the most BASIC first (skill level 1 basic … 4 umbrella field, from
   skill_order.json), then the one that unlocks the most other planned skills, then the
   most important for the role.
4. Schedule: each skill = Learn → Practise → Build tasks, sized by a per-category
   effort estimate, packed into weeks of the user's weekly hours (questionnaire).
   The total is compared with the user's timeline.

Gemini (fast tier) only adds a mini-project idea + tip per skill, in ONE batched call;
without it a rule-based template is used.
"""
import json
import logging
import math
import time
from functools import lru_cache
from urllib.parse import quote_plus

import networkx as nx
from pydantic import BaseModel

from app.config import DATA_DIR
from app.services import learning_resources, llm, market_model

log = logging.getLogger(__name__)

GRAPH_PATH = DATA_DIR / "skill_graph.json"
ORDER_PATH = DATA_DIR / "skill_order.json"
DEFAULT_LEVEL = 2
SOFT = "soft_skills"

# Rough hours to become job-ready in one skill, by kind of skill (estimates; tuned on Day 23)
EFFORT_HOURS = {
    "programming_languages": 40, "web_frontend": 25, "web_backend": 25, "mobile": 35, "databases": 20,
    "cloud": 25, "devops": 20, "data_science_ml": 35, "ai_llm": 20, "data_analytics_bi": 20,
    "testing_qa": 15, "security": 30, "networking_systems": 30, "embedded_iot": 30, "blockchain_gamedev": 30,
    "design_ux": 20, "project_management": 12, "business_office": 15, "marketing_sales": 15,
    "finance_accounting": 25, "human_resources": 15, "healthcare": 25, "engineering_core": 30,
    "education_teaching": 15, "legal_admin": 15,
}
DEFAULT_HOURS = 20
IMPROVE_FACTOR = 0.5   # "beginner" skills (to improve) and foundations (intro level only) need about half
STEPS = [("learn", "Learn the basics of {s}", 0.4),
         ("practise", "Practise {s} with exercises", 0.35),
         ("build", "Build: {project}", 0.25)]
# An umbrella field (level 4) comes last, after its parts, so its first step is a capstone
UMBRELLA_STEPS = {"learn": "Put it all together: how {s} works end to end",
                  "practise": "Practise a complete {s} workflow on a small real project"}

WEEKLY_HOURS = {"2-5": 4, "5-10": 8, "10-20": 15, "20+": 22}
TIMELINE_WEEKS = {"1m": 4, "3m": 13, "6m": 26, "12m": 52}
DEFAULT_WEEKLY, DEFAULT_WEEKS = 8, 13


# ------------------------------------------------------------------ graph --
@lru_cache(maxsize=1)
def _graph(model_stamp: str | None) -> nx.DiGraph:
    g = nx.DiGraph()
    for a, b in json.loads(GRAPH_PATH.read_text(encoding="utf-8"))["edges"]:
        g.add_edge(a, b, source="curated")

    def add(a, b, **attrs) -> bool:
        if a == b or g.has_edge(a, b) or g.has_edge(b, a):
            return False
        if a in g and b in g and nx.has_path(g, b, a):      # would create a cycle
            return False
        g.add_edge(a, b, **attrs)
        return True

    gemini = sum(add(a, b, source="gemini", votes=n) for a, b, n in _skill_order().get("edges", []))
    model = market_model.load_model() or {}
    # statistics can't tell a field from its parts, so a learned pair must also make sense by level
    learned = sum(add(e["before"], e["after"], source="learned", confidence=e["p_before_given_after"])
                  for e in model.get("prerequisites", [])
                  if skill_level(e["before"]) <= skill_level(e["after"]))
    log.info("Skill graph: %d edges (%d from Gemini, %d learned from postings)",
             g.number_of_edges(), gemini, learned)
    return g


@lru_cache(maxsize=1)
def _skill_order() -> dict:
    """Skill levels + prerequisite pairs built offline with Gemini ({} if not built)."""
    try:
        return json.loads(ORDER_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def skill_level(name: str) -> int:
    """1 basic, 2 core, 3 advanced, 4 umbrella field."""
    return _skill_order().get("levels", {}).get(name, DEFAULT_LEVEL)


def skill_graph() -> nx.DiGraph:
    model = market_model.load_model()
    return _graph(model["built_at"] if model else None)


# -------------------------------------------------------------------- gap --
def skill_gap(profile: dict, role: str, levels: dict | None = None, top_n: int = 12) -> list[dict]:
    """The role's most important hard skills the user lacks (+ 'beginner' skills to improve)."""
    prof = market_model.role_profile(role)
    if not prof:
        return []
    have = {s["name"].lower() for s in profile.get("skills", [])}
    beginner = {k.lower() for k, v in (levels or {}).items() if v == "beginner"}
    gap = []
    for s in prof["skills"]:
        if s.get("category") == SOFT:
            continue
        name = s["name"]
        if name.lower() not in have:
            kind = "learn"
        elif name.lower() in beginner:
            kind = "improve"
        else:
            continue
        gap.append({"name": name, "kind": kind, "category": s.get("category"), "weight": s["weight"],
                    "share_of_postings": s["freq"]})
        if len(gap) >= top_n:
            break
    return gap


def add_foundations(gap: list[dict], have: set[str], g: nx.DiGraph) -> list[dict]:
    """Add missing prerequisites of gap skills, walking back until a known skill.
    Only general rules add skills (hand-checked + learned from postings). Gemini's pairs are
    role-specific, so they only order skills that are already in the plan."""
    items = {s["name"]: s for s in gap}
    have_l = {h.lower() for h in have}
    categories = _skill_categories()
    stack = [s["name"] for s in gap]
    while stack:
        skill = stack.pop()
        if skill not in g:
            continue
        for pre in g.predecessors(skill):
            if pre.lower() in have_l or g.edges[pre, skill].get("source") == "gemini":
                continue
            if pre not in items:
                items[pre] = {"name": pre, "kind": "foundation", "category": categories.get(pre),
                              "weight": 0.0, "share_of_postings": None}
                stack.append(pre)
            # a foundation is as urgent as the most important skill that needs it
            items[pre]["weight"] = max(items[pre]["weight"], items[skill]["weight"])
    for name, item in items.items():
        item["prerequisites"] = [p for p in (g.predecessors(name) if name in g else []) if p in items]
        item["needed_for"] = [n for n in (g.successors(name) if name in g else []) if n in items]
    return list(items.values())


def _skill_categories() -> dict[str, str]:
    from app.services import entity_extractor as ee
    return _categories(ee.vocab_version())


@lru_cache(maxsize=4)
def _categories(_version: int) -> dict[str, str]:     # includes skills learned from live postings
    from app.services.entity_extractor import skill_vocab
    return {e.lstrip("!").split("|")[0]: cat for cat, lst in skill_vocab().items() for e in lst}


def order_skills(items: list[dict], g: nx.DiGraph) -> list[dict]:
    """Topological order of the gap subgraph (prerequisites always first). Among skills
    that are free to go next: most basic level first, then the one that unlocks the most
    other planned skills, then the most important for the role."""
    by_name = {i["name"]: i for i in items}
    sub = nx.DiGraph()
    sub.add_nodes_from(by_name)
    sub.add_edges_from((a, b) for a, b in g.subgraph(by_name).edges)
    unlocks = {n: len(nx.descendants(sub, n)) for n in sub}
    kind_rank = {"foundation": 0, "learn": 1, "improve": 2}
    for n, i in by_name.items():
        i["level"] = skill_level(n)
    key = lambda n: (by_name[n]["level"], -unlocks[n], -round(by_name[n]["weight"], 3),  # noqa: E731
                     kind_rank[by_name[n]["kind"]], n)
    return [by_name[n] for n in nx.lexicographical_topological_sort(sub, key=key)]


# --------------------------------------------------------------- schedule --
def _hours(item: dict) -> int:
    h = EFFORT_HOURS.get(item.get("category"), DEFAULT_HOURS)
    return max(4, round(h * (IMPROVE_FACTOR if item["kind"] in ("improve", "foundation") else 1)))


def schedule(items: list[dict], hours_per_week: float) -> list[dict]:
    """Pack each skill's Learn/Practise/Build tasks into weeks, in order. A task that
    doesn't fit in what's left of a week continues the next week, so weeks are full."""
    weeks, current, used = [], [], 0.0
    for item in items:
        for step, title, share in STEPS:
            remaining = max(1, round(item["hours"] * share))
            pieces = []
            while remaining > 1e-9:
                take = min(remaining, hours_per_week - used)
                piece = {"skill": item["name"], "step": step, "hours": round(take, 1), "done": False}
                current.append(piece)
                pieces.append(piece)
                used += take
                remaining -= take
                if used >= hours_per_week - 1e-9:
                    weeks.append(current)
                    current, used = [], 0.0
            if item.get("level") == 4 and not item.get("needed_for"):   # last in its chain: a capstone
                title = UMBRELLA_STEPS.get(step, title)
            label = title.format(s=item["name"], project=item["project"])
            for n, piece in enumerate(pieces, 1):
                piece["id"] = f"{_slug(item['name'])}-{step}-{n}"
                piece["title"] = label + (f" (part {n}/{len(pieces)})" if len(pieces) > 1 else "")
    if current:
        weeks.append(current)
    key_order = ("id", "skill", "step", "title", "hours", "done")
    return [{"week": i + 1, "hours": round(sum(t["hours"] for t in w), 1),
             "tasks": [{k: t[k] for k in key_order} for t in w]} for i, w in enumerate(weeks)]


def fit_to_budget(gap: list[dict], items: list[dict], g: nx.DiGraph, budget_hours: float,
                  min_skills: int = 3) -> tuple[list[dict], list[dict]]:
    """Keep the most important gap skills (with their foundations) that fit the user's
    timeline × weekly hours; the rest become 'later'. At least `min_skills` are kept."""
    by_name = {i["name"]: i for i in items}
    sub = g.subgraph(by_name)
    chosen, later, hours, kept = set(), [], 0, 0
    for s in sorted(gap, key=lambda s: -s["weight"]):
        closure = ({s["name"]} | (nx.ancestors(sub, s["name"]) if s["name"] in sub else set())) - chosen
        extra = sum(by_name[n]["hours"] for n in closure)
        if kept >= min_skills and hours + extra > budget_hours:
            later.append(by_name[s["name"]])
            continue
        chosen |= closure
        hours += extra
        kept += 1
    return [i for i in items if i["name"] in chosen], later


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")


# -------------------------------------------------------------- resources --
def resources(skill: str, style: str | None, videos: list[dict] | None = None,
              docs_url: str | None = None) -> list[dict]:
    """Learning links for a skill, preferred learning style first.
    Specific links when we have them (real YouTube videos, checked official docs);
    otherwise free search links, which never break and work for any skill."""
    q = quote_plus
    video_links = videos or [{"type": "video", "title": f"{skill} full course (YouTube search)",
                              "url": f"https://www.youtube.com/results?search_query={q(skill + ' full course for beginners')}"}]
    reading = ({"type": "reading", "title": f"{skill} official documentation", "url": docs_url} if docs_url else
               {"type": "reading", "title": f"{skill} tutorials and official docs (search)",
                "url": f"https://www.google.com/search?q={q(skill + ' tutorial official documentation')}"})
    links = {
        "video": video_links,
        "reading": [reading],
        "course": [{"type": "course", "title": f"Free {skill} courses (Coursera, audit for free)",
                    "url": f"https://www.coursera.org/search?query={q(skill)}"}],
        "projects": [{"type": "projects", "title": f"{skill} beginner project ideas",
                      "url": f"https://www.google.com/search?q={q(skill + ' beginner project ideas')}"}],
    }
    first = {"video": "video", "reading": "reading", "projects": "projects"}.get(style or "", None)
    order = [first] if first else []
    order += [k for k in ("video", "reading", "course", "projects") if k not in order]
    return [link for k in order for link in links[k]]


# --------------------------------------------------- Gemini project ideas --
class _Idea(BaseModel):
    skill: str
    project: str
    tip: str
    docs_url: str      # official documentation / learning page; verified before use


class _Ideas(BaseModel):
    ideas: list[_Idea]


def project_ideas(role: str, skills: list[str]) -> dict[str, dict]:
    """ONE batched Gemini call (fast tier) for all skills. {} if Gemini is unavailable."""
    if not skills:
        return {}
    prompt = (f"A learner is preparing for a '{role}' job. For each skill below, suggest ONE small, concrete "
              f"portfolio mini-project (max 14 words, starts with a verb) that a {role} would do, and ONE "
              f"practical learning tip (max 20 words), and docs_url: the URL of the OFFICIAL documentation "
              f"only if the skill is a specific tool, language, framework, product or certification "
              f"(e.g. Tableau, Python, Docker, PMP). For general concepts or activities (e.g. Statistics, "
              f"Reporting, Data Analysis, Recruitment) docs_url must be an empty string. https only. "
              f"Skills: {', '.join(skills)}")
    out = llm.generate_json(prompt, _Ideas, tier="fast")
    if not out:
        return {}
    wanted = {s.lower(): s for s in skills}
    return {wanted[i["skill"].lower()]: i for i in out.get("ideas", []) if i.get("skill", "").lower() in wanted}


def _fallback_project(skill: str, role: str) -> str:
    return f"a small {role}-style project that uses {skill}"


# ------------------------------------------------------------------- main --
def build_roadmap(profile: dict, role: str, answers: dict | None = None, top_n: int = 12) -> dict | None:
    """Full roadmap for `role`. None if the role is unknown / model missing."""
    answers = answers or {}
    val = lambda k: (answers.get(k) or {}).get("value")  # noqa: E731
    role_name = market_model.find_role(role)
    if not role_name:
        return None
    hours_pw = WEEKLY_HOURS.get(val("weekly_hours"), DEFAULT_WEEKLY)
    goal_weeks = TIMELINE_WEEKS.get(val("timeline"), DEFAULT_WEEKS)
    style = val("learning_style")
    levels = val("skill_levels") or {}

    g = skill_graph()
    have = {s["name"] for s in profile.get("skills", [])}
    gap = skill_gap(profile, role_name, levels, top_n)
    all_items = order_skills(add_foundations(gap, have, g), g)
    for i in all_items:
        i["hours"] = _hours(i)
        i["weight"] = round(i["weight"], 3)
    items, later = fit_to_budget(gap, all_items, g, budget_hours=goal_weeks * hours_pw)

    names = [i["name"] for i in items]
    ideas = project_ideas(role_name, names)                          # one Gemini call for the plan
    videos = learning_resources.videos_for(names)                     # cached YouTube searches
    docs = [(ideas.get(n) or {}).get("docs_url") or None for n in names]
    docs_ok = learning_resources.check_urls(docs)                     # drop links that don't open
    for i, doc, ok in zip(items, docs, docs_ok, strict=False):
        idea = ideas.get(i["name"]) or {}
        i["project"] = (idea.get("project") or _fallback_project(i["name"], role_name)).rstrip(".")
        i["tip"] = idea.get("tip")
        i["resources"] = resources(i["name"], style, videos.get(i["name"]), doc if ok else None)

    weeks = schedule(items, hours_pw)
    total = sum(i["hours"] for i in items)
    all_hours = total + sum(i["hours"] for i in later)
    needed_pw = math.ceil(total / goal_weeks)                 # to finish THIS plan on time
    needed_all_pw = math.ceil(all_hours / goal_weeks)         # to also cover the 'later' skills
    fits = len(weeks) <= goal_weeks
    if not items:
        message = f"Your profile already covers the key {role_name} skills. Focus on projects and interviews."
    elif not fits:
        message = (f"Even the {len(items)} most important skills need {len(weeks)} weeks at {hours_pw} h/week, "
                   f"longer than your {goal_weeks}-week goal. Study about {needed_pw} h/week to finish on time.")
    elif later:
        message = (f"Your {goal_weeks}-week goal at {hours_pw} h/week fits the {len(items)} most important skills "
                   f"({len(weeks)} weeks). {len(later)} more are listed for after; about {needed_all_pw} h/week "
                   f"would cover them all.")
    else:
        message = f"{len(items)} skills in {len(weeks)} weeks at {hours_pw} h/week, within your {goal_weeks}-week goal."
    used_edges = [{"before": a, "after": b, "source": g.edges[a, b]["source"]}
                  for a, b in g.subgraph({i["name"] for i in items}).edges]
    return {
        "role": role_name,
        "summary": {"skills_to_learn": sum(i["kind"] != "improve" for i in items),
                    "skills_to_improve": sum(i["kind"] == "improve" for i in items),
                    "skills_later": len(later), "total_hours": total, "weeks_needed": len(weeks),
                    "goal_weeks": goal_weeks, "hours_per_week": hours_pw, "hours_per_week_needed": needed_pw,
                    "hours_per_week_for_all": needed_all_pw, "fits_timeline": fits, "message": message},
        "inputs": {"weekly_hours": val("weekly_hours"), "timeline": val("timeline"), "learning_style": style},
        "skills": items,
        "later": [{"name": i["name"], "kind": i["kind"], "hours": i["hours"],
                   "share_of_postings": i["share_of_postings"]} for i in later],
        "weeks": weeks,
        "prerequisite_edges": used_edges,
        "ideas_by": "gemini" if ideas else "template",
    }


# ------------------------------------------------------ progress (Day 13) --
WEEK_SECONDS = 7 * 24 * 3600


def _tasks(plan: dict):
    for w in plan.get("weeks", []):
        yield from w["tasks"]


def set_task(plan: dict, task_id: str, done: bool) -> str | None:
    """Tick/untick one task. Returns the skill name if this tick COMPLETED a skill
    (all its tasks done). Raises KeyError for an unknown task id."""
    task = next((t for t in _tasks(plan) if t["id"] == task_id), None)
    if task is None:
        raise KeyError(task_id)
    task["done"] = bool(done)
    task["done_at"] = time.time() if done else None
    skill = task["skill"]
    completed = plan.setdefault("completed_skills", [])
    names = [c["name"] for c in completed]
    all_done = all(t["done"] for t in _tasks(plan) if t["skill"] == skill)
    if all_done and skill not in names:
        completed.append({"name": skill, "completed_at": time.time()})
        return skill
    if not all_done and skill in names:                 # unticked: no longer complete
        plan["completed_skills"] = [c for c in completed if c["name"] != skill]
    return None


def progress(plan: dict, now: float | None = None) -> dict:
    """How far along the user is, and whether they're on schedule.
    expected week = weeks since the plan started; current week = first week with open tasks."""
    now = now or time.time()
    tasks = list(_tasks(plan))
    hours = sum(t["hours"] for t in tasks) or 1
    hours_done = sum(t["hours"] for t in tasks if t["done"])
    weeks = plan.get("weeks", [])
    current = next((w["week"] for w in weeks if not all(t["done"] for t in w["tasks"])), None)
    started = plan.get("started_at") or plan.get("generated_at") or now
    expected = min(len(weeks), int((now - started) // WEEK_SECONDS) + 1) if weeks else 0
    # hours that should be done by now = all weeks before the expected one
    hours_due = sum(w["hours"] for w in weeks if w["week"] < expected)
    if current is None:
        status, message = "done", "Plan complete. Great work! Rebuild it to get your next skills."
    elif hours_done + 1e-9 >= hours_due + (weeks[expected - 1]["hours"] if expected else 0):
        status, message = "ahead", "You're ahead of schedule."
    elif hours_done + 1e-9 >= hours_due:
        status, message = "on_track", f"On track: you're in week {expected}."
    else:
        behind = hours_due - hours_done
        status, message = "behind", (f"About {round(behind)} h behind schedule. Catch up this week, "
                                     f"or re-plan to spread the rest over the remaining time.")
    skills_total = len(plan.get("skills", []))
    return {"tasks_total": len(tasks), "tasks_done": sum(t["done"] for t in tasks),
            "hours_total": round(hours, 1), "hours_done": round(hours_done, 1),
            "percent": round(100 * hours_done / hours), "current_week": current, "expected_week": expected,
            "skills_total": skills_total, "skills_completed": len(plan.get("completed_skills", [])),
            "status": status, "message": message}


def carry_over(old: dict | None, new: dict) -> dict:
    """When a plan is rebuilt, keep ticks on tasks that still exist, the history of
    completed skills and (same role) the start date."""
    if not old:
        return new
    done = {t["id"]: t for t in _tasks(old) if t["done"]}
    for t in _tasks(new):
        if t["id"] in done:
            t["done"], t["done_at"] = True, done[t["id"]].get("done_at")
    new["completed_skills"] = list(old.get("completed_skills", []))
    if old.get("role") == new.get("role") and old.get("started_at"):
        new["started_at"] = old["started_at"]
    return new
