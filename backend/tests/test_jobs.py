"""Live remote jobs: eligibility for Pakistan, normalising, de-duplication, matching, endpoint.
No network: the sources are never called; postings are built by hand."""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import job_sources as js
from app.services import live_jobs


@pytest.mark.parametrize("location, scope", [
    ("Worldwide", "Worldwide"), ("Anywhere in the World", "Worldwide"), ("APAC", "Asia"),
    ("Asia, Europe", "Asia"), ("Pakistan, India", "Pakistan"), ("", "Not stated"), ("Remote", "Not stated"),
    ("USA", None), ("Europe, USA, Canada", None), ("EMEA", None), ("UTC+3 to UTC+6", "Time zone fits Pakistan"),
    ("UTC-8 to UTC-5", None),
])
def test_pakistan_scope(location, scope):
    assert js.pakistan_scope(location) == scope


def test_himalayas_structured_restrictions():
    assert js._himalayas_scope({"locationRestrictions": [], "timezoneRestrictions": []}) == "Worldwide"
    assert js._himalayas_scope({"locationRestrictions": ["Pakistan", "India"], "timezoneRestrictions": [5]}) == "Pakistan"
    assert js._himalayas_scope({"locationRestrictions": ["Egypt"], "timezoneRestrictions": [2]}) is None
    assert js._himalayas_scope({"locationRestrictions": [], "timezoneRestrictions": [-5, -8]}) is None


def _job(title, company="Acme", desc="", source="remotive", scope="Worldwide", **kw):
    return js._posting(source, title + company, title, company, scope or "USA", scope, "https://x.test/j",
                       None, desc, time.time() - 3600, **kw)


def test_posting_shape_html_and_dedupe():
    p = _job("Data Analyst", desc="<p>Use <b>SQL</b> &amp; Python</p><ul><li>Dashboards</li></ul>")
    assert p["description"] == "Use SQL & Python\nDashboards" and p["apply_url"] == p["url"]
    a = _job("Data Analyst", "Acme Inc", desc="short")
    b = _job("data analyst ", "ACME inc", desc="a much longer description", source="jobicy")
    c = _job("Data Analyst", "Acme Inc", scope=None, desc="the longest description of all of them")
    kept = js.dedupe([a, b, c])
    assert len(kept) == 1 and kept[0]["source"] == "jobicy"   # open to Pakistan beats longer text
    assert js._salary(114000000, 140000000) is None and js._salary(50000, 70000, "USD", "year") == "USD 50,000–70,000 / year"


@pytest.fixture
def pool(monkeypatch):
    jobs = [_job("DevOps Engineer", desc="Docker, Kubernetes, Terraform, AWS and Linux. CI/CD with Jenkins."),
            _job("Registered Nurse", "Clinic", desc="Patient Care, CPR, Vital Signs, Infection Control."),
            _job("Cloud Engineer", "Sky", desc="AWS, Terraform, Docker.", scope=None)]     # not open to PK
    monkeypatch.setattr(live_jobs, "_pool", {"jobs": {}, "updated_at": time.time(), "report": {}})
    monkeypatch.setattr(live_jobs, "_vectors", {})
    monkeypatch.setattr(live_jobs, "_save_all", lambda jobs: None)
    live_jobs._add_skills(jobs)
    live_jobs._merge(jobs)
    return jobs


def test_only_jobs_open_to_pakistan_are_shown_and_ranked(pool):
    cv = {"headline": "DevOps Engineer", "skills": [{"name": n, "mentions": 2, "sections": ["skills"]}
                                                    for n in ["Docker", "Kubernetes", "AWS", "Linux"]]}
    res = live_jobs.match_jobs(cv)
    assert [j["title"] for j in res] == ["DevOps Engineer", "Registered Nurse"]   # Cloud Engineer: US-only
    top = res[0]
    assert top["match"] > res[1]["match"] and "Docker" in top["matched_skills"]
    assert "Terraform" in top["missing_skills"] and top["source_name"] == "Remotive"
    assert live_jobs.match_jobs(cv, query="nurse")[0]["title"] == "Registered Nurse"


def test_few_skills_cannot_give_full_keyword_score(pool):
    one = _job("Helper", desc="Docker.")
    live_jobs._add_skills([one])
    live_jobs._merge([one])
    cv = {"skills": [{"name": "Docker", "mentions": 1}]}
    helper = next(j for j in live_jobs.match_jobs(cv) if j["title"] == "Helper")
    assert helper["keyword"] == 100 // live_jobs.MIN_SKILLS


def test_expired_and_old_jobs_are_dropped(pool):
    old = _job("Old Job")
    old["published_at"] = time.time() - 90 * 86400
    gone = _job("Expired Job")
    gone["expires_at"] = time.time() - 10
    live_jobs._merge([old, gone])
    titles = {j["title"] for j in live_jobs._pool["jobs"].values()}
    assert "Old Job" not in titles and "Expired Job" not in titles


def test_jobs_endpoint(pool, monkeypatch):
    from app.auth import current_uid
    from app.orchestrator.blackboard import Blackboard
    from app.routers import career
    bb = Blackboard(db=None)
    monkeypatch.setattr(career.agent, "bb", bb)
    monkeypatch.setattr(live_jobs, "ensure_fresh", lambda: False)
    monkeypatch.setattr(live_jobs, "add_role_jobs", lambda role, wait=False: None)
    app.dependency_overrides[current_uid] = lambda: "u1"
    try:
        client = TestClient(app)
        assert client.get("/jobs").status_code == 404                          # no resume yet
        bb.write("u1", "resume", {"entities": {"skills": [{"name": "Docker", "mentions": 2}]}}, agent="resume_agent")
        r = client.get("/jobs").json()
        assert r["jobs"][0]["title"] == "DevOps Engineer" and {"name": "Himalayas", "url": "https://himalayas.app"} in r["sources"]
        assert bb.read_section("u1", "jobs")["top"][0]["title"] == "DevOps Engineer"
        assert client.get("/jobs?q=nurse").json()["jobs"][0]["title"] == "Registered Nurse"
        assert client.get("/jobs/status").json()["jobs_available"] == 2
    finally:
        app.dependency_overrides.clear()
