"""Skill gap + prerequisite DAG + weekly roadmap."""
import json

import networkx as nx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import llm, market_model
from app.services import roadmap as rm
from tests.test_market_model import built_model  # noqa: F401  (fixture)

CV = {"skills": [{"name": n, "mentions": 2, "sections": ["skills"]} for n in ["AWS", "Linux", "Python"]]}


@pytest.fixture(autouse=True)
def _no_gemini(monkeypatch):
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: None)
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
