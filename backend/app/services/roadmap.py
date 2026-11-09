"""Skill gap + learning roadmap (Career Guide Agent, Day 11).

1. Skill gap = set difference
       role skills (learned from job postings, most important first)
     − skills the user has (resume + skills confirmed in the questionnaire)
     + skills the user rated "beginner" (to improve, at half the effort)
2. Prerequisites: a directed graph (networkx DiGraph) of "learn A before B":
     - hand-checked edges from data/skill_graph.json (like a course syllabus), plus
     - edges LEARNED from job postings by co-occurrence asymmetry (market_model.json),
       added only if they don't create a cycle; hand-checked edges win.
   Missing foundations of each gap skill are added (walking back until a skill the
   user already knows), so the plan never says "Kubernetes" before "Docker".
3. Order: topological sort of the gap subgraph (a DAG). Among skills that are free
   to go next, the most important for the role comes first.
4. Schedule: each skill = Learn → Practise → Build tasks, sized by a per-category
   effort estimate, packed into weeks of the user's weekly hours (questionnaire).
   The total is compared with the user's timeline.

Gemini (fast tier) only adds a mini-project idea + tip per skill, in ONE batched call;
without it a rule-based template is used.
"""
import json
import logging
import math
from functools import lru_cache
from urllib.parse import quote_plus

import networkx as nx
from pydantic import BaseModel

from app.config import DATA_DIR
from app.services import llm, market_model

log = logging.getLogger(__name__)

GRAPH_PATH = DATA_DIR / "skill_graph.json"
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

WEEKLY_HOURS = {"2-5": 4, "5-10": 8, "10-20": 15, "20+": 22}
TIMELINE_WEEKS = {"1m": 4, "3m": 13, "6m": 26, "12m": 52}
DEFAULT_WEEKLY, DEFAULT_WEEKS = 8, 13


# ------------------------------------------------------------------ graph --
@lru_cache(maxsize=1)
def _graph(model_stamp: str | None) -> nx.DiGraph:
    g = nx.DiGraph()
    for a, b in json.loads(GRAPH_PATH.read_text(encoding="utf-8"))["edges"]:
        g.add_edge(a, b, source="curated")
    model = market_model.load_model() or {}
    added = 0
    for e in model.get("prerequisites", []):
        a, b = e["before"], e["after"]
        if g.has_edge(a, b) or g.has_edge(b, a):
            continue
        if a in g and b in g and nx.has_path(g, b, a):      # would create a cycle
            continue
        g.add_edge(a, b, source="learned", confidence=e["p_before_given_after"])
        added += 1
    log.info("Skill graph: %d edges (%d learned from postings)", g.number_of_edges(), added)
    return g


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
    """Add missing prerequisites of gap skills, walking back until a known skill."""
    items = {s["name"]: s for s in gap}
    have_l = {h.lower() for h in have}
    categories = _skill_categories()
    stack = [s["name"] for s in gap]
    while stack:
        skill = stack.pop()
        if skill not in g:
            continue
        for pre in g.predecessors(skill):
            if pre.lower() in have_l:
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


@lru_cache(maxsize=1)
def _skill_categories() -> dict[str, str]:
    data = json.loads((DATA_DIR / "skills.json").read_text(encoding="utf-8"))
    return {e.lstrip("!").split("|")[0]: cat for cat, lst in data.items() if not cat.startswith("_") for e in lst}


def order_skills(items: list[dict], g: nx.DiGraph) -> list[dict]:
    """Topological order of the gap subgraph; ties → more important first, foundations early."""
    by_name = {i["name"]: i for i in items}
    sub = nx.DiGraph()
    sub.add_nodes_from(by_name)
    sub.add_edges_from((a, b) for a, b in g.subgraph(by_name).edges)
    kind_rank = {"foundation": 0, "learn": 1, "improve": 2}
    key = lambda n: (-round(by_name[n]["weight"], 3), kind_rank[by_name[n]["kind"]], n)  # noqa: E731
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
def resources(skill: str, style: str | None) -> list[dict]:
    """Free search links (never break, work for any of the 693 skills, no hand-written URLs)."""
    q = quote_plus
    links = {
        "video": {"type": "video", "title": f"{skill} full course (YouTube)",
                  "url": f"https://www.youtube.com/results?search_query={q(skill + ' full course for beginners')}"},
        "reading": {"type": "reading", "title": f"{skill} tutorials and official docs",
                    "url": f"https://www.google.com/search?q={q(skill + ' tutorial official documentation')}"},
        "course": {"type": "course", "title": f"Free {skill} courses (Coursera, audit for free)",
                   "url": f"https://www.coursera.org/search?query={q(skill)}"},
        "projects": {"type": "projects", "title": f"{skill} beginner project ideas",
                     "url": f"https://www.google.com/search?q={q(skill + ' beginner project ideas')}"},
    }
    first = {"video": "video", "reading": "reading", "projects": "projects"}.get(style or "", None)
    order = [first] if first else []
    order += [k for k in ("video", "reading", "course", "projects") if k not in order]
    return [links[k] for k in order]


# --------------------------------------------------- Gemini project ideas --
class _Idea(BaseModel):
    skill: str
    project: str
    tip: str


class _Ideas(BaseModel):
    ideas: list[_Idea]


def project_ideas(role: str, skills: list[str]) -> dict[str, dict]:
    """ONE batched Gemini call (fast tier) for all skills. {} if Gemini is unavailable."""
    if not skills:
        return {}
    prompt = (f"A learner is preparing for a '{role}' job. For each skill below, suggest ONE small, concrete "
              f"portfolio mini-project (max 14 words, starts with a verb) that a {role} would do, and ONE "
              f"practical learning tip (max 20 words). Skills: {', '.join(skills)}")
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

    ideas = project_ideas(role_name, [i["name"] for i in items])     # one Gemini call for the plan
    for i in items:
        idea = ideas.get(i["name"]) or {}
        i["project"] = (idea.get("project") or _fallback_project(i["name"], role_name)).rstrip(".")
        i["tip"] = idea.get("tip")
        i["resources"] = resources(i["name"], style)

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
