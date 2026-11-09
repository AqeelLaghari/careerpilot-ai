"""Career matching (Layer 2 + Layer 3) on the tiny 3-role model from test_market_model."""
from fastapi.testclient import TestClient

from app.main import app
from app.services import career_matcher
from tests.test_market_model import built_model  # noqa: F401  (fixture)

DEVOPS_CV = {
    "headline": "DevOps Engineer",
    "experience": [{"title": "DevOps Engineer"}],
    "skills": [{"name": n, "mentions": 2} for n in ["Docker", "Kubernetes", "Terraform", "AWS", "Linux"]],
    "projects": [{"title": "CI/CD pipeline with Jenkins"}],
}
NURSE_CV = {
    "headline": "Registered Nurse",
    "experience": [{"title": "Staff Nurse"}],
    "skills": [{"name": n, "mentions": 1} for n in ["Patient Care", "CPR", "Vital Signs", "Infection Control"]],
    "projects": [],
}


def test_score_helpers():
    assert career_matcher.semantic_score(0.40) == 0 and career_matcher.semantic_score(0.85) == 100
    assert career_matcher.semantic_score(0.625) == 50 and career_matcher.semantic_score(0.1) == 0
    assert career_matcher._family("Full Stack Developer") == career_matcher._family("Full Stack Engineer")
    assert career_matcher.combine(100, 0) == 60 and career_matcher.combine(0, 100) == 40


def test_resume_text_shape():
    t = career_matcher.resume_text(DEVOPS_CV)
    assert t.startswith("DevOps Engineer") and "Key skills: Docker" in t and "Projects:" in t


def test_match_careers_ranks_right_role_first(built_model):  # noqa: F811
    top = career_matcher.match_careers(DEVOPS_CV, top_k=3)
    assert top[0]["role"] == "DevOps Engineer"
    assert top[0]["score"] > top[-1]["score"]
    assert "Docker" in top[0]["matched_skills"] and "Jenkins" in top[0]["missing_skills"]
    assert career_matcher.match_careers(NURSE_CV, top_k=1)[0]["role"] == "Registered Nurse"


def test_role_match_and_jd_match(built_model):  # noqa: F811
    rm = career_matcher.role_match(NURSE_CV, "registered nurse")
    assert rm["role"] == "Registered Nurse" and rm["keyword"] > 0
    jd = career_matcher.jd_match(DEVOPS_CV, "We are hiring a DevOps engineer with Docker, Kubernetes, "
                                            "Terraform and Ansible experience on AWS.")
    assert "Ansible" in jd["missing_skills"] and "Docker" in jd["matched_skills"]
    assert 0 < jd["score"] <= 100


def test_career_endpoints(built_model, monkeypatch):  # noqa: F811
    from app.auth import current_uid
    from app.orchestrator.blackboard import Blackboard
    from app.routers import career
    bb = Blackboard(db=None)
    bb.write("u1", "resume", {"entities": DEVOPS_CV}, agent="resume_agent")
    monkeypatch.setattr(career.agent, "bb", bb)
    app.dependency_overrides[current_uid] = lambda: "u1"
    try:
        client = TestClient(app)
        r = client.post("/career/match")
        assert r.status_code == 200 and r.json()["matches"][0]["role"] == "DevOps Engineer"
        r = client.post("/career/target", json={"role": "devops engineer"})
        assert r.json()["target_role"] == "DevOps Engineer"
        assert bb.read("u1")["_meta"]["career"]["updated_by"] == "career_agent"
        assert client.post("/career/jd-match", json={"job_description": "short"}).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_resume_text_prefers_skills_with_evidence():
    cv = {"headline": None, "experience": [], "projects": [], "skills": [
        {"name": "Software Engineering", "mentions": 5, "sections": ["header", "education"]},   # degree name only
        {"name": "PyTorch", "mentions": 2, "sections": ["skills", "projects"]},
    ]}
    t = career_matcher.resume_text(cv)
    assert t.index("PyTorch") < t.index("Software Engineering")


def test_near_duplicate_roles_are_merged(built_model, monkeypatch):  # noqa: F811
    monkeypatch.setattr(career_matcher, "DUP_COS", -1.0)   # everything counts as a duplicate
    assert len(career_matcher.match_careers(DEVOPS_CV, top_k=3)) == 1
