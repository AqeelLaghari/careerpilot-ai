"""Day 24: ATS score history, dashboard synthesis, app settings and the bullet rewriter."""
import pytest
from fastapi.testclient import TestClient

from app.agents.resume_agent import HISTORY_LIMIT, score_history
from app.auth import current_uid
from app.main import app
from app.orchestrator import dashboard as dash
from app.orchestrator.blackboard import Blackboard
from app.routers import dashboard as dashboard_router
from app.routers import resume as resume_router
from app.services import account_profile as ap
from app.services import bullet_rewriter as br
from app.services import privacy

NOW = 1_800_000_000.0


def _resume(*scores):
    history = [{"at": NOW - 1000 * (len(scores) - i), "score": s, "filename": "cv.pdf"} for i, s in enumerate(scores)]
    return {"ats": {"readability_score": scores[-1], "grade": "Good",
                    "top_fixes": [{"fix": "Add numbers to your bullets."}]}, "history": history}


def _plan(done=0, total=3, started=NOW):
    tasks = [{"id": f"t{i}", "skill": "SQL", "title": f"SQL part {i + 1}", "hours": 2, "done": i < done,
              "done_at": NOW - 50 if i < done else None} for i in range(total)]
    return {"role": "Data Analyst", "generated_at": started, "started_at": started, "skills": [{"name": "SQL"}],
            "weeks": [{"week": i + 1, "hours": 2, "tasks": [task]} for i, task in enumerate(tasks)]}


def _interviews(*scores):
    return {"sessions": [{"id": f"s{i}", "created_at": NOW - 100 + i, "role": "Data Analyst", "mode": "live",
                          "report": {"overall": s}} for i, s in enumerate(scores)]}


# ------------------------------------------------------------- ATS history --
def test_history_grows_and_keeps_the_old_score_of_pre_day24_cvs():
    old = {"ats": {"readability_score": 55}, "uploaded_at": 1.0, "filename": "old.pdf"}
    h = score_history(old, {"readability_score": 72}, "new.pdf", 2.0)
    assert [x["score"] for x in h] == [55, 72]
    h = score_history({"history": h}, {"readability_score": 80}, "v3.pdf", 3.0)
    assert [x["score"] for x in h] == [55, 72, 80]


def test_history_is_capped():
    h = []
    for i in range(HISTORY_LIMIT + 5):
        h = score_history({"history": h}, {"readability_score": i}, "cv.pdf", float(i))
    assert len(h) == HISTORY_LIMIT and h[-1]["score"] == HISTORY_LIMIT + 4


# --------------------------------------------------------------- next step --
@pytest.mark.parametrize("state, title, tab", [
    ({}, "Upload your CV", "resume"),
    ({"resume": _resume(52)}, "Improve your CV", "resume"),
    ({"resume": _resume(80)}, "Find your best-fit careers", "career"),
    ({"resume": _resume(80), "career": {"matches": [{"role": "Data Analyst", "score": 70}]}},
     "Choose a target role", "career"),
    ({"resume": _resume(80), "career": {"matches": [{}], "target_role": "Data Analyst"}},
     "Build your learning roadmap", "career"),
    ({"resume": _resume(80), "career": {"matches": [{}], "target_role": "Data Analyst"}, "roadmap": _plan()},
     "Practise a mock interview", "interview"),
    ({"resume": _resume(80), "career": {"matches": [{}], "target_role": "Data Analyst"},
      "roadmap": _plan(started=NOW - 3 * 7 * 86400), "interviews": _interviews(60)}, "Catch up on your roadmap", "career"),
    ({"resume": _resume(80), "career": {"matches": [{}], "target_role": "Data Analyst"}, "roadmap": _plan(),
      "interviews": _interviews(60)}, "Look at matching jobs", "jobs"),
    ({"resume": _resume(80), "career": {"matches": [{}], "target_role": "Data Analyst"}, "roadmap": _plan(),
      "interviews": _interviews(60), "jobs": {"top": [{"id": "j"}]}}, "Keep learning", "career"),
    ({"resume": _resume(80), "career": {"matches": [{}], "target_role": "Data Analyst"}, "roadmap": _plan(done=3),
      "interviews": _interviews(60), "jobs": {"top": [{"id": "j"}]}}, "Practise another interview", "interview"),
])
def test_next_step_follows_the_journey(state, title, tab):
    step = dash.next_step(state, NOW)
    assert (step["title"], step["tab"]) == (title, tab)


def test_low_ats_step_names_the_top_fix():
    assert "Add numbers to your bullets." in dash.next_step({"resume": _resume(40)}, NOW)["text"]


# ----------------------------------------------------------------- summary --
def test_summary_tiles_chart_and_activity():
    state = {"resume": _resume(55, 72),
             "career": {"target_role": "Data Analyst", "target_match": {"score": 64}, "target_set_at": NOW - 500},
             "roadmap": _plan(done=1), "interviews": _interviews(58, 71)}
    s = dash.summary(state, NOW)
    assert s["tiles"]["ats"] == {"score": 72, "grade": "Good", "change": 17, "top_fix": "Add numbers to your bullets."}
    assert s["tiles"]["match"] == {"role": "Data Analyst", "score": 64, "basis": "target"}
    assert s["tiles"]["roadmap"]["percent"] == 33 and s["tiles"]["roadmap"]["next_task"]["title"] == "SQL part 2"
    assert s["tiles"]["interviews"] == {"count": 2, "last": 71, "best": 71, "last_role": "Data Analyst"}
    assert [p["score"] for p in s["ats_history"]] == [55, 72]
    times = [a["at"] for a in s["activity"]]
    assert times == sorted(times, reverse=True) and len(s["activity"]) <= dash.ACTIVITY_LIMIT
    assert {a["kind"] for a in s["activity"]} == {"resume", "career", "roadmap", "interview"}


def test_empty_summary_does_not_crash():
    s = dash.summary({}, NOW)
    assert s["tiles"]["ats"] is None and s["tiles"]["match"] is None and s["tiles"]["roadmap"] is None
    assert s["tiles"]["interviews"]["count"] == 0 and s["ats_history"] == [] and s["activity"] == []


def test_best_fit_used_when_no_target():
    assert dash._match_tile({"matches": [{"role": "QA Engineer", "score": 61}]})["basis"] == "best fit"


# ---------------------------------------------------------------- settings --
def test_settings_are_validated_and_merged():
    p = ap.clean({"settings": {"theme": "dark"}}, {})
    assert p["settings"] == ap.DEFAULT_SETTINGS | {"theme": "dark"}
    p = ap.clean({"settings": {"voice": "male"}}, p)
    assert p["settings"]["theme"] == "dark" and p["settings"]["voice"] == "male"
    with pytest.raises(ap.ProfileError) as e:
        ap.clean({"settings": {"theme": "purple", "font": "big"}}, {})
    assert set(e.value.errors) == {"settings.theme", "settings.font"}
    with pytest.raises(ap.ProfileError):
        ap.clean({"settings": "dark"}, {})


# ---------------------------------------------------------- bullet rewriter --
@pytest.mark.parametrize("bullet, expected", [
    ("Responsible for managing the company website", "Managed the company website"),
    ("Worked on a chatbot using Python", "Developed a chatbot using Python"),
    ("I was developing REST APIs for my team", "Developed REST APIs for the team"),
    ("Building dashboards in Power BI", "Built dashboards in Power BI"),
    ("Helped with organizing events", "Organized events"),
])
def test_rule_rewrite(bullet, expected):
    out = br.rule_rewrite(bullet)
    assert out["versions"] == [expected] and out["source"] == "rules" and "number" in out["tip"]


def test_review_marks_weak_bullets():
    ents = {"experience": [{"bullets": ["Responsible for the website of the shop", "Cut load time by 40% with caching"]}]}
    weak, strong = br.review(ents)
    assert weak["weak"] and "Doesn't start with an action verb" in weak["issues"]
    assert not strong["weak"] and strong["issues"] == []


def test_ai_rewrite_is_scrubbed_and_restored(monkeypatch):
    private = privacy.terms({"experience": [{"company": "Acme Labs"}]}, {"full_name": "Sara Khan"})
    seen = {}

    def fake(prompt, schema, **kw):
        seen["prompt"] = prompt
        return {"versions": ["Built an inventory app at [company] for X users",
                             "Worked on inventory app at Acme Labs",       # same as the original: dropped
                             "Built an inventory app at [company] for X users"], "tip": "Add the user count"}

    monkeypatch.setattr(br.llm, "generate_json", fake)
    out = br.rewrite("Worked on inventory app at Acme Labs", "Software Engineer", private)
    assert "Acme" not in seen["prompt"] and "[company]" in seen["prompt"] and "Software Engineer" in seen["prompt"]
    assert out == {"versions": ["Built an inventory app at Acme Labs for X users"], "tip": "Add the user count",
                   "source": "ai"}


def test_rewrite_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(br.llm, "generate_json", lambda *a, **k: None)
    assert br.rewrite("Worked on a weather app")["source"] == "rules"
    with pytest.raises(ValueError):
        br.rewrite("hello")


# --------------------------------------------------------------------- API --
@pytest.fixture
def client(monkeypatch):
    bb = Blackboard()
    monkeypatch.setattr(dashboard_router, "blackboard", bb)
    monkeypatch.setattr(resume_router, "blackboard", bb)
    monkeypatch.setattr(br.llm, "generate_json", lambda *a, **k: None)
    app.dependency_overrides[current_uid] = lambda: "u1"
    yield TestClient(app), bb
    app.dependency_overrides.clear()


def test_dashboard_and_bullet_endpoints(client):
    c, bb = client
    assert c.get("/dashboard").json()["next_step"]["tab"] == "resume"
    assert c.get("/resume/bullets").status_code == 404
    bb.write("u1", "resume", _resume(80) | {"entities": {"experience": [{"bullets": ["Worked on the shop website"]}]}},
             agent="test")
    assert c.get("/dashboard").json()["tiles"]["ats"]["score"] == 80
    assert c.get("/resume/bullets").json()["bullets"][0]["weak"] is True
    r = c.post("/resume/rewrite", json={"bullet": "Worked on the shop website"})
    assert r.status_code == 200 and r.json()["versions"] == ["Developed the shop website"]
    assert c.post("/resume/rewrite", json={"bullet": "hi"}).status_code == 422
