"""Interview questions (Day 15): plan from the profile, Gemini writes them in one call,
templates fill anything missing, no repeats. Gemini is faked; no network."""
import pytest
from fastapi.testclient import TestClient

from app.services import interview_questions as iq

PROFILE = {
    "skills": [{"name": n, "category": "devops", "mentions": m} for n, m in
               [("Docker", 5), ("Kubernetes", 3), ("AWS", 3), ("Linux", 2), ("Python", 1)]]
              + [{"name": "Communication", "category": "soft_skills", "mentions": 4}],
    "projects": [{"title": "CI pipeline for a shop", "description": ["Built GitHub Actions"], "skills": ["Docker"]}],
    "experience": [], "total_experience_months": 30,
}
COVERAGE = {"matched": ["Kubernetes", "Docker"], "missing": [{"name": "Terraform"}, {"name": "Ansible"}]}


def test_plan_mix_skills_and_level():
    plan = iq.plan_session(PROFILE, "DevOps Engineer", COVERAGE, count=8)
    types = [s["type"] for s in plan["slots"]]
    assert len(types) == 8 and types[0] == "intro" and "project" in types and "gap" in types
    assert {"technical", "behavioural", "situational"} <= set(types)
    tech = [s["skill"] for s in plan["slots"] if s["type"] == "technical"]
    assert tech[0] == "Kubernetes" and "Communication" not in tech          # role skills first, no soft skills
    assert [s["skill"] for s in plan["slots"] if s["type"] == "gap"][0] == "Terraform"
    assert plan["level"] == "mid" and plan["difficulty"] == "medium"
    assert iq.level_of({"total_experience_months": 100}, {"career_stage": {"value": "student"}}) == "entry"
    assert iq.level_of({"total_experience_months": 100}) == "senior"


def test_recently_asked_skills_go_to_the_back():
    plan = iq.plan_session(PROFILE, "DevOps Engineer", COVERAGE, count=8, recent_skills={"kubernetes": 2})
    assert [s["skill"] for s in plan["slots"] if s["type"] == "technical"][0] == "Docker"


@pytest.mark.parametrize("count", [3, 5, 8, 12])
def test_any_count_and_no_cv_projects_or_skills(count):
    bare = {"skills": [], "projects": [], "experience": []}
    plan = iq.plan_session(bare, "Teacher", None, count=count)
    assert len(plan["slots"]) == count and "technical" not in {s["type"] for s in plan["slots"]}
    s = iq.write_questions(plan, bare)                    # Gemini is offline in tests: templates
    assert len(s["questions"]) == count and s["source"] == "template"
    assert all(q["question"] and len(q["key_points"]) >= 3 for q in s["questions"])


def test_gemini_writes_all_in_one_call_and_bad_answers_are_replaced(monkeypatch):
    plan = iq.plan_session(PROFILE, "DevOps Engineer", COVERAGE, count=5)
    calls = []

    def fake(prompt, schema, tier, temperature, timeout=None):
        calls.append(tier)
        assert "Kubernetes" in prompt and "@" not in prompt
        return {"questions": [{"slot": i, "question": f"Question number {i} about the role, please explain?",
                               "key_points": ["a", "b", "c"]} for i in range(len(plan["slots"]))]
                + [{"slot": 1, "question": "too short", "key_points": ["a"]}]}
    monkeypatch.setattr(iq.llm, "generate_json", fake)
    s = iq.write_questions(plan, PROFILE)
    assert calls == ["fast"] and s["source"] == "gemini"
    assert [q["id"] for q in s["questions"]] == [f"q{i}" for i in range(1, 6)]
    assert s["questions"][0]["time_limit_sec"] == iq.TIME_LIMIT["intro"]

    monkeypatch.setattr(iq.llm, "generate_json", lambda *a, **k: {"questions": [
        {"slot": 0, "question": "Tell me about yourself for this DevOps role please?", "key_points": ["a", "b"]}]})
    s = iq.write_questions(plan, PROFILE)
    assert s["source"] == "mixed" and all(q["question"] for q in s["questions"])


def test_no_repeats_across_sessions():
    plan = iq.plan_session({"skills": [], "projects": [], "experience": []}, "Teacher", None, count=3)
    used = set()
    for _ in range(3):
        s = iq.write_questions(plan, {}, used_hashes=used)
        hashes = [iq.qhash(q["question"]) for q in s["questions"]]
        assert not set(hashes) & used
        used |= set(hashes)


def test_interview_endpoints():
    from app.auth import current_uid
    from app.main import app
    from app.orchestrator.blackboard import Blackboard
    from app.routers import interview
    bb = Blackboard(db=None)
    interview.agent.bb = bb
    app.dependency_overrides[current_uid] = lambda: "u1"
    try:
        c = TestClient(app)
        assert c.post("/interview/sessions", json={}).status_code == 404            # no resume yet
        bb.write("u1", "resume", {"entities": PROFILE}, agent="resume_agent")
        bb.write("u1", "career", {"target_role": "DevOps Engineer"}, agent="career_agent")
        s = c.post("/interview/sessions", json={"count": 5}).json()
        assert s["role"] == "DevOps Engineer" and len(s["questions"]) == 5
        s2 = c.post("/interview/sessions", json={"count": 5}).json()
        assert not {q["question"] for q in s["questions"]} & {q["question"] for q in s2["questions"]}
        assert [x["id"] for x in c.get("/interview/sessions").json()] == [s2["id"], s["id"]]
        assert c.get(f"/interview/sessions/{s['id']}").json()["questions"][0]["type"] == "intro"
        assert c.get("/interview/sessions/nope").status_code == 404
        assert c.post("/interview/sessions", json={"count": 50}).status_code == 422
        assert len(bb.read_section("u1", "interviews")["asked"]) == 10
    finally:
        app.dependency_overrides.clear()


def test_slow_gemini_falls_back_to_templates_within_the_budget(monkeypatch):
    import time

    from app.services import llm
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "_generate", lambda model, prompt, config: time.sleep(3) or "{}")
    monkeypatch.setattr(iq, "GEMINI_BUDGET", 0.5)
    plan = iq.plan_session(PROFILE, "DevOps Engineer", COVERAGE, count=5)
    t = time.time()
    s = iq.write_questions(plan, PROFILE)
    assert time.time() - t < 2.5 and s["source"] == "template" and len(s["questions"]) == 5
