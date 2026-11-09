"""Skill gap + prerequisite DAG + weekly roadmap."""
import json

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import learning_resources, llm, market_model
from app.services import roadmap as rm
from tests.test_market_model import built_model  # noqa: F401  (fixture)

CV = {"skills": [{"name": n, "mentions": 2, "sections": ["skills"]} for n in ["AWS", "Linux", "Python"]]}


@pytest.fixture(autouse=True)
def _no_gemini(monkeypatch):
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: None)
    monkeypatch.setattr(learning_resources, "videos_for", lambda skills: {})     # no network in tests
    monkeypatch.setattr(learning_resources, "check_urls", lambda urls: [False] * len(urls))
    rm._graph.cache_clear()
    yield
    rm._graph.cache_clear()


def test_curated_graph_is_valid_dag():
    edges = json.loads(rm.GRAPH_PATH.read_text(encoding="utf-8"))["edges"]
    names = set(rm._skill_categories())
    assert not {n for e in edges for n in e if n not in names}, "every graph skill must exist in skills.json"
    assert nx.is_directed_acyclic_graph(nx.DiGraph(edges))


def test_learned_edges_never_create_cycles(monkeypatch):
    fake = {"built_at": "x", "roles": {}, "prerequisites": [
        {"before": "Docker", "after": "Linux", "p_before_given_after": 0.9},     # contradicts Linux → Docker
        {"before": "Kubernetes", "after": "Helm", "p_before_given_after": 0.9},  # duplicate of curated
        {"before": "Python", "after": "Airflow Thing", "p_before_given_after": 0.8},
    ]}
    monkeypatch.setattr(market_model, "load_model", lambda: fake)
    g = rm.skill_graph()
    assert nx.is_directed_acyclic_graph(g)
    assert not g.has_edge("Docker", "Linux")
    assert g.edges["Kubernetes", "Helm"]["source"] == "curated"
    assert g.edges["Python", "Airflow Thing"]["source"] == "learned"


def test_gap_foundations_and_order(built_model):  # noqa: F811
    gap = rm.skill_gap(CV, "DevOps Engineer", {"Python": "beginner"})
    names = [s["name"] for s in gap]
    assert "Kubernetes" in names and "Docker" in names and "AWS" not in names   # set difference
    g = rm.skill_graph()
    items = rm.order_skills(rm.add_foundations(gap, {"AWS", "Linux", "Python"}, g), g)
    order = [i["name"] for i in items]
    assert order.index("Docker") < order.index("Kubernetes")                    # prerequisite first
    assert "Cloud Computing" in order or "Infrastructure as Code" in order       # foundation added
    assert "Linux" not in order                                                 # already known
    for i in items:
        for pre in i["prerequisites"]:
            assert order.index(pre) < order.index(i["name"])


def test_schedule_respects_weekly_hours():
    items = [{"name": "Docker", "hours": 20, "project": "containerise an app"},
             {"name": "Kubernetes", "hours": 10, "project": "deploy it"}]
    weeks = rm.schedule(items, hours_per_week=8)
    assert all(w["hours"] <= 8 for w in weeks)
    assert sum(w["hours"] for w in weeks) == pytest.approx(30, abs=1)
    tasks = [t for w in weeks for t in w["tasks"]]
    assert tasks[0]["skill"] == "Docker" and tasks[-1]["skill"] == "Kubernetes"
    assert len({t["id"] for t in tasks}) == len(tasks)


def test_build_roadmap_uses_answers(built_model):  # noqa: F811
    answers = {"weekly_hours": {"value": "2-5"}, "timeline": {"value": "1m"}, "learning_style": {"value": "video"}}
    plan = rm.build_roadmap(CV, "devops engineer", answers)
    s = plan["summary"]
    assert plan["role"] == "DevOps Engineer" and s["hours_per_week"] == 4 and s["goal_weeks"] == 4
    assert not s["fits_timeline"] and s["hours_per_week_needed"] > 4 and "h/week" in s["message"]
    assert plan["skills"][0]["resources"][0]["type"] == "video"
    assert plan["ideas_by"] == "template"
    assert rm.build_roadmap(CV, "zzzz qqqq", answers) is None


def test_roadmap_endpoints(built_model, monkeypatch):  # noqa: F811
    from app.auth import current_uid
    from app.orchestrator.blackboard import Blackboard
    from app.routers import career
    bb = Blackboard(db=None)
    bb.write("u1", "resume", {"entities": CV}, agent="resume_agent")
    monkeypatch.setattr(career.agent, "bb", bb)
    app.dependency_overrides[current_uid] = lambda: "u1"
    try:
        client = TestClient(app)
        assert client.get("/roadmap").status_code == 404
        r = client.post("/roadmap", json={"role": "data analyst"})
        assert r.status_code == 200 and r.json()["role"] == "Data Analyst"
        assert client.get("/roadmap").json()["role"] == "Data Analyst"
        assert bb.read("u1")["_meta"]["roadmap"]["updated_by"] == "career_agent"
        assert client.post("/roadmap").status_code == 200          # no role: best-fit role
    finally:
        app.dependency_overrides.clear()


# ------------------------------------------------------------- Day 13 --
def _plan():
    items = [{"name": "Docker", "hours": 10, "project": "x"}, {"name": "Kubernetes", "hours": 10, "project": "y"}]
    return {"role": "DevOps Engineer", "skills": items, "weeks": rm.schedule(items, 8), "started_at": 1_000_000}


def test_ticking_completes_a_skill_and_unticking_reopens_it():
    plan = _plan()
    docker = [t["id"] for w in plan["weeks"] for t in w["tasks"] if t["skill"] == "Docker"]
    for tid in docker[:-1]:
        assert rm.set_task(plan, tid, True) is None
    assert rm.set_task(plan, docker[-1], True) == "Docker"
    assert [c["name"] for c in plan["completed_skills"]] == ["Docker"]
    rm.set_task(plan, docker[0], False)
    assert plan["completed_skills"] == []
    with pytest.raises(KeyError):
        rm.set_task(plan, "nope", True)


def test_progress_status():
    plan = _plan()
    week = 7 * 24 * 3600
    assert rm.progress(plan, now=plan["started_at"] + 10)["status"] == "on_track"
    late = rm.progress(plan, now=plan["started_at"] + 2 * week + 10)       # week 3, nothing done
    assert late["status"] == "behind" and late["expected_week"] == 3 and late["percent"] == 0
    for w in plan["weeks"]:
        for t in w["tasks"]:
            t["done"] = True
    done = rm.progress(plan, now=plan["started_at"] + 10)
    assert done["status"] == "done" and done["percent"] == 100 and done["current_week"] is None


def test_carry_over_keeps_ticks():
    old = _plan()
    first = old["weeks"][0]["tasks"][0]["id"]
    rm.set_task(old, first, True)
    old["completed_skills"] = [{"name": "Git", "completed_at": 1}]
    new = rm.carry_over(old, _plan() | {"started_at": 2_000_000})
    assert new["weeks"][0]["tasks"][0]["done"] and new["started_at"] == 1_000_000
    assert new["completed_skills"][0]["name"] == "Git"


def test_completed_skill_improves_match(built_model, monkeypatch):  # noqa: F811
    from app.auth import current_uid
    from app.orchestrator.blackboard import Blackboard
    from app.routers import career
    bb = Blackboard(db=None)
    bb.write("u1", "resume", {"entities": CV}, agent="resume_agent")
    monkeypatch.setattr(career.agent, "bb", bb)
    app.dependency_overrides[current_uid] = lambda: "u1"
    try:
        client = TestClient(app)
        client.post("/career/target", json={"role": "devops engineer"})
        plan = client.post("/roadmap").json()
        assert "progress" in plan
        skill = plan["skills"][0]["name"]
        ids = [t["id"] for w in plan["weeks"] for t in w["tasks"] if t["skill"] == skill]
        for tid in ids:
            r = client.post(f"/roadmap/tasks/{tid}", json={"done": True}).json()
        assert r["skill_completed"] == skill
        assert r["progress"]["skills_completed"] == 1
        assert client.post("/roadmap/tasks/zzz", json={"done": True}).status_code == 404
        rebuilt = client.post("/roadmap").json()                 # learned skill isn't planned again
        assert skill not in [s["name"] for s in rebuilt["skills"]]
        assert rebuilt["completed_skills"][0]["name"] == skill
    finally:
        app.dependency_overrides.clear()


def test_specific_links_replace_search_links():
    vids = [{"type": "video", "title": "Docker in 1 hour", "channel": "X", "url": "https://www.youtube.com/watch?v=abc"}]
    links = rm.resources("Docker", "video", vids, "https://docs.docker.com/")
    assert links[0]["url"].endswith("watch?v=abc")
    assert {"type": "reading", "title": "Docker official documentation", "url": "https://docs.docker.com/"} in links
    fallback = rm.resources("Docker", "reading")
    assert fallback[0]["type"] == "reading" and "google.com/search" in fallback[0]["url"]


def test_gemini_docs_link_used_only_if_it_opens(built_model, monkeypatch):  # noqa: F811
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: {"ideas": [
        {"skill": "Docker", "project": "Containerise an app", "tip": "t", "docs_url": "https://docs.docker.com/"},
        {"skill": "Kubernetes", "project": "Deploy it", "tip": "t", "docs_url": "https://made-up.example/k8s"}]})
    monkeypatch.setattr(learning_resources, "check_urls", lambda urls: [u == "https://docs.docker.com/" for u in urls])
    plan = rm.build_roadmap(CV, "devops engineer", {})
    by = {s["name"]: s for s in plan["skills"]}
    assert any(r["url"] == "https://docs.docker.com/" for r in by["Docker"]["resources"])
    assert not any("made-up" in r["url"] for r in by["Kubernetes"]["resources"])
