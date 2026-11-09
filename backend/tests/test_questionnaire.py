"""Adaptive questionnaire: asks only what the resume is missing; answers improve matching."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import questionnaire as qn
from tests.test_market_model import built_model  # noqa: F401  (fixture)

FULL_CV = {   # experienced professional: CV already answers most things
    "headline": "DevOps Engineer", "location": "Karachi, Pakistan",
    "experience": [{"title": "DevOps Engineer", "company": "X"}], "total_experience_months": 48,
    "education": [{"degree": "BS Computer Science", "end_year": 2020}],
    "skills": [{"name": n, "mentions": 3, "sections": ["skills", "experience"]}
               for n in ["Docker", "Kubernetes", "Terraform", "AWS", "Linux", "Python", "Git", "Bash"]],
    "projects": [],
}
THIN_CV = {   # student with a short CV: no experience, education, or location
    "headline": None, "location": None, "experience": [], "total_experience_months": 0, "education": [],
    "skills": [{"name": n, "mentions": 1, "sections": ["skills"]} for n in ["SQL", "Python", "Excel"]],
    "projects": [],
}


def ids(qs):
    return [q["id"] for q in qs]


def test_full_cv_gets_few_questions():
    career = {"matches": [{"role": "DevOps Engineer", "score": 80}], "target_role": "DevOps Engineer"}
    asked = ids(qn.pending_questions(FULL_CV, career, {}))
    for not_needed in ["target_role", "career_stage", "education_level", "location", "interests",
                       "experience_years"]:
        assert not_needed not in asked
    assert {"weekly_hours", "timeline", "learning_style"} <= set(asked)


def test_thin_cv_gets_more_questions_and_follow_ups():
    asked = ids(qn.pending_questions(THIN_CV, {"matches": []}, {}))
    assert {"career_stage", "education_level", "interests", "location"} <= set(asked)
    assert "graduation_year" not in asked and "education_field" not in asked
    answers = {"career_stage": {"value": "student"}, "education_level": {"value": "bachelor"}}
    asked = ids(qn.pending_questions(THIN_CV, {"matches": []}, answers))
    assert "graduation_year" in asked and "education_field" in asked     # unlocked by the answers
    assert "career_stage" not in asked


def test_validation():
    q = qn.q_weekly_hours(qn.Ctx({}, {}, {}))
    assert qn.validate(q, "5-10") == "5-10"
    with pytest.raises(qn.AnswerError):
        qn.validate(q, "a lot")
    yq = {"id": "graduation_year", "type": "number", "min": 2024, "max": 2035}
    assert qn.validate(yq, "2027") == 2027
    with pytest.raises(qn.AnswerError):
        qn.validate(yq, 1999)
    iq = qn.q_interests(qn.Ctx(THIN_CV, {}, {}))
    with pytest.raises(qn.AnswerError):
        qn.validate(iq, ["software", "data_ai", "qa", "design"])          # max 3


def test_extra_skills_from_learned_role(built_model):  # noqa: F811
    career = {"matches": [{"role": "Data Analyst", "score": 50}]}
    q = qn.q_extra_skills(qn.Ctx(THIN_CV, career, {}))
    opts = [o["value"] for o in q["options"]]
    assert "Tableau" in opts and "SQL" not in opts        # only what the CV is missing
    clean = qn.validate(q, ["Tableau", "power bi", "Quantum Juggling"])
    assert clean["skills"] == ["Tableau", "Power BI"] and clean["unrecognised"] == ["Quantum Juggling"]
    prof = qn.profile_entities(THIN_CV, {"extra_skills": {"value": clean}})
    assert {"Tableau", "Power BI"} <= {s["name"] for s in prof["skills"]}
    assert THIN_CV["skills"][-1]["name"] == "Excel" and len(THIN_CV["skills"]) == 3   # original untouched


def test_questionnaire_endpoints(built_model, monkeypatch):  # noqa: F811
    from app.auth import current_uid
    from app.orchestrator.blackboard import Blackboard
    from app.routers import career
    bb = Blackboard(db=None)
    bb.write("u1", "resume", {"entities": THIN_CV}, agent="resume_agent")
    monkeypatch.setattr(career.agent, "bb", bb)
    app.dependency_overrides[current_uid] = lambda: "u1"
    try:
        client = TestClient(app)
        r = client.get("/questionnaire").json()
        assert "target_role" in ids(r["questions"]) and not r["completed"]

        before = bb.read_section("u1", "career")
        r = client.post("/questionnaire/answers", json={"answers": {
            "target_role": "data analyst", "career_stage": "student", "graduation_year": 2027,
            "weekly_hours": "lots"}}).json()
        assert r["accepted"] == ["target_role", "career_stage", "graduation_year"]   # follow-up in same call
        assert "weekly_hours" in r["errors"]
        assert r["career"]["target_role"] == "Data Analyst"
        assert "extra_skills" in ids(r["questions"])

        kw_before = r["career"]["target_match"]["keyword"]
        r = client.post("/questionnaire/answers", json={"answers": {"extra_skills": ["Tableau", "Power BI"]}}).json()
        assert r["career"]["target_match"]["keyword"] > kw_before             # answers improve the match
        assert bb.read("u1")["_meta"]["questionnaire"]["updated_by"] == "career_agent"
        assert before is not None

        r = client.delete("/questionnaire").json()
        assert r["answered"] == {}
    finally:
        app.dependency_overrides.clear()


def test_no_resume_404(monkeypatch):
    from app.auth import current_uid
    from app.orchestrator.blackboard import Blackboard
    from app.routers import career
    monkeypatch.setattr(career.agent, "bb", Blackboard(db=None))
    app.dependency_overrides[current_uid] = lambda: "nobody"
    try:
        assert TestClient(app).get("/questionnaire").status_code == 404
    finally:
        app.dependency_overrides.clear()
