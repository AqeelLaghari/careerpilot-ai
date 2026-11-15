"""Self-learning market model: new skills from postings, hot reload, trends, re-weighting, admin.
No network: Gemini is faked and Firestore is switched off."""
import time

import pytest

from app.services import entity_extractor as ee
from app.services import market_learning as ml
from app.services import market_model


def _p(title, desc, tags=(), days=1, company="Acme"):
    return {"title": title, "company": company, "description": desc, "tags": list(tags),
            "published_at": time.time() - days * 86400}


@pytest.fixture
def learner(monkeypatch, tmp_path):
    monkeypatch.setattr(ml, "_db", lambda: None)
    monkeypatch.setattr(ml, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(ml, "_state", {"last_run": 0.0, "skills": [], "rejected": [], "trends": {},
                                       "role_live": {}, "report": {}})
    monkeypatch.setattr(ml, "_loaded", True)
    yield ml
    ee.set_learned_skills([])                 # leave the detector as it was
    market_model.set_live_roles({})


def _postings(n=20):
    # "Zorblex" (a made-up tool) and "Urgent" are in every posting; "Docker" is already known.
    return [_p("Data Engineer", "You will use Python, Zorblex, Docker and SQL daily, plus Urgent, Hybrid, Kafka.",
               tags=["zorblex", "Remote"], company=f"Co{i}") for i in range(n)]


def test_candidates_skip_known_skills_blocklist_and_rare_terms(learner):
    cands = {c["term"].lower(): c["postings"] for c in ml.find_candidates(_postings(20) + [
        _p("X", "Tools: Rarething, Python, Docker, SQL.")])}
    assert cands.get("zorblex") == 20
    assert "docker" not in cands and "python" not in cands      # known already
    assert "urgent" not in cands and "hybrid" not in cands and "remote" not in cands   # blocklist
    assert "rarething" not in cands                              # fewer than MIN_POSTINGS


def test_gemini_confirms_then_detector_knows_it_without_restart(learner, monkeypatch):
    assert "Zorblex" not in ee.find_skills("We use Zorblex.")
    asked = []

    def fake_review(cands):
        asked.append(len(cands))
        return [{"term": c["term"], "postings": c["postings"], "is_skill": c["term"].lower() == "zorblex",
                 "name": "Zorblex", "category": "data_science_ml"} for c in cands]
    monkeypatch.setattr(ml, "review", fake_review)
    rep = ml.learn(_postings(20))
    assert asked == [len(ml.find_candidates(_postings(20))) or asked[0]]   # ONE batched call
    assert "Zorblex" in rep["added"]
    assert ee.find_skills("We use Zorblex.")["Zorblex"]["category"] == "data_science_ml"
    assert "Zorblex" in next(ee.find_skills_batch(["zorblex pipelines"]))
    assert ml.learned_skills()["skills"][0]["status"] == "approved"
    assert ml.STATE_FILE.exists()                                # saved


def test_new_spelling_of_known_skill_becomes_an_alias(learner, monkeypatch):
    posts = [_p("Dev", "Stack: Reactjsx, Node, AWS, more.", company=f"C{i}") for i in range(16)]
    monkeypatch.setattr(ml, "review", lambda c: [{"term": x["term"], "postings": x["postings"], "is_skill": True,
                                                  "name": "React", "category": "web_frontend"} for x in c])
    rep = ml.learn(posts)
    assert rep["aliases"] and "React" in ee.find_skills("Built apps in Reactjsx.")


def test_without_gemini_candidates_wait_for_an_admin(learner, monkeypatch):
    monkeypatch.setattr(ml, "review", lambda c: None)
    ml.learn(_postings(20))
    s = next(s for s in ml.learned_skills()["skills"] if s["name"].lower() == "zorblex")
    assert s["status"] == "pending" and "Zorblex" not in ee.find_skills("We use Zorblex.")
    with pytest.raises(ValueError):
        ml.set_status("Zorblex", "approved", "not_a_category")
    ml.set_status("Zorblex", "approved", "data_science_ml")
    assert "Zorblex" in ee.find_skills("We use Zorblex.")


def test_removed_skill_is_dropped_and_never_learned_again(learner, monkeypatch):
    monkeypatch.setattr(ml, "review", lambda c: [{"term": x["term"], "postings": x["postings"], "is_skill": True,
                                                  "name": x["term"].title(), "category": "data_science_ml"}
                                                 for x in c])
    ml.learn(_postings(20))
    ml.set_status("Zorblex", "removed")
    assert "Zorblex" not in ee.find_skills("We use Zorblex.")
    assert all(c["term"].lower() != "zorblex" for c in ml.find_candidates(_postings(20)))


def test_trends_weight_new_postings_and_find_rising_skills(learner):
    old = [_p("Dev", "Python, Java, SQL.", days=40, company=f"o{i}") for i in range(40)]
    new = [_p("Dev", "Python, Kubernetes, SQL.", days=2, company=f"n{i}") for i in range(40)]
    t, _ = ml.compute_trends(old + new)
    assert t["history_ready"]
    rising, falling = {r["name"] for r in t["rising"]}, {r["name"] for r in t["falling"]}
    assert "Kubernetes" in rising and "Java" in falling and "Python" not in rising | falling
    share = {s["name"]: s["share"] for s in t["top"]}
    assert share["Kubernetes"] > share["Java"]                    # newer postings count more


def test_live_postings_reweight_role_keywords(learner):
    model = market_model.load_model()
    role = "DevOps Engineer"
    base = market_model.role_profile(role)
    posts = [_p("DevOps Engineer", "Zig, Docker, Kubernetes.", company=f"c{i}") for i in range(12)]
    ee.set_learned_skills([{"name": "Zig", "category": "programming_languages", "aliases": []}])
    _, found = ml.compute_trends(posts)
    live = ml.live_role_shares(posts, found)
    assert live[role]["postings"] == 12 and live[role]["freq"]["Zig"] == 1.0
    market_model.set_live_roles(live)
    blended = market_model.role_profile(role)
    assert "Zig" in [s["name"] for s in blended["skills"]] and blended["live_postings"] == 12
    assert 0 < blended["live_share"] <= market_model.LIVE_MAX_SHARE
    assert "Zig" not in [s["name"] for s in base["skills"]]
    assert market_model.live_share(100, 10, model, now=time.time()) > market_model.live_share(
        100, 10, model, now=time.mktime((2024, 5, 1, 0, 0, 0, 0, 0, 0)))   # older base data → live counts more


def test_admin_endpoints_need_admin(learner, monkeypatch):
    from fastapi.testclient import TestClient

    from app import config
    from app.auth import current_uid
    from app.main import app
    monkeypatch.setattr(ml, "review", lambda c: None)
    ml.learn(_postings(20))
    app.dependency_overrides[current_uid] = lambda: "u1"
    try:
        c = TestClient(app)
        monkeypatch.setattr(config, "ADMIN_UIDS", set())
        assert c.get("/market/learned").status_code == 403
        assert c.get("/market/admin/me").json() == {"is_admin": False}
        assert "top" in c.get("/market/trending").json()
        monkeypatch.setattr(config, "ADMIN_UIDS", {"u1"})
        assert any(s["name"] == "zorblex" or s["name"] == "Zorblex" for s in c.get("/market/learned").json()["skills"])
        r = c.post("/market/learned/Zorblex", json={"status": "approved", "category": "data_science_ml"})
        assert r.status_code == 200 and r.json()["status"] == "approved"
        assert c.post("/market/learned/Nope", json={"status": "removed"}).status_code == 404
        assert c.post("/market/learned/Zorblex", json={"status": "maybe"}).status_code == 400
    finally:
        app.dependency_overrides.clear()


def test_general_words_never_become_skills_or_aliases(learner, monkeypatch):
    posts = [_p("Dev", "We build things. Focus areas: Build, Security, Testing, Zorblex. Our security and "
                       "testing are strong; we build fast. We do not discriminate by race, color, religion, age.",
                company=f"C{i}") for i in range(20)]
    terms = {c["term"].lower() for c in ml.find_candidates(posts)}
    assert "zorblex" in terms
    assert not terms & {"build", "security", "testing", "color", "religion", "age"}
    assert ml.looks_like_spelling_of("ReactJS", "React") and ml.looks_like_spelling_of("Postgres", "PostgreSQL")
    assert not ml.looks_like_spelling_of("security", "Cybersecurity")
    assert not ml.looks_like_spelling_of("Security", "Cybersecurity")
    assert not ml.looks_like_spelling_of("deployment", "Model Deployment")
    assert not ml.looks_like_spelling_of("APIs", "API Design")
    monkeypatch.setattr(ml, "review", lambda c: [{"term": "deployment", "postings": 20, "is_skill": True,
                                                  "name": "Model Deployment", "category": "devops"}])
    monkeypatch.setattr(ml, "find_candidates", lambda p: [{"term": "deployment", "postings": 20}])
    rep = ml.learn(posts)
    assert rep["aliases"] == [] and "Model Deployment" not in ee.find_skills("Fast deployment.")


def test_start_up_recheck_drops_wrong_spellings_learned_by_older_rules(learner):
    ml._state["skills"] = [
        {"name": "Cybersecurity", "category": "security", "aliases": ["security"], "status": "approved", "by": "Gemini"},
        {"name": "CI/CD", "category": "devops", "aliases": ["CI"], "status": "approved", "by": "Gemini"},
        {"name": "Zorblex", "category": "data_science_ml", "aliases": [], "status": "approved", "by": "Gemini"}]
    ml._state["last_run"] = time.time()
    assert ml._recheck() == 1
    names = {s["name"]: s["aliases"] for s in ml._state["skills"]}
    assert "Cybersecurity" not in names and names["CI/CD"] == ["CI"] and "Zorblex" in names
    assert "security" in ml._state["rejected"] and ml._state["last_run"] == 0.0
    assert ml._recheck() == 0
