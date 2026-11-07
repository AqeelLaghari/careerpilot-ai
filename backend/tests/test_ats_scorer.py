from app.services.ats_scorer import _starts_with_action_verb, score_resume


def _layout(**kw):
    base = {"pages": 1, "columns": 1, "images": 0, "tables": 0, "font_families": ["Calibri"],
            "body_font_size": 11, "word_count": 520, "is_scanned": False}
    return {**base, **kw}


GOOD_SKILLS = [{"name": n, "category": "web_backend", "mentions": 2, "sections": ["skills", "experience"]}
               for n in ["Python", "FastAPI", "Docker", "SQL", "Git", "AWS", "Redis", "Linux", "React", "Kubernetes"]]


def _good():
    parsed = {
        "layout": _layout(),
        "sections": {s: "x" for s in ["summary", "experience", "education", "skills", "projects"]},
        "contact": {"email": "a@b.com", "phone": "+92 300 1234567", "linkedin": "linkedin.com/in/a"},
    }
    entities = {
        "location": "Karachi, Pakistan",
        "skills": GOOD_SKILLS,
        "experience": [{"title": "Backend Intern", "company": "TechCorp", "bullets": [
            "Built 12 REST APIs with FastAPI serving 5,000 daily users",
            "Reduced query time by 40% by adding Redis caching",
            "Automated deployments with Docker and GitHub Actions",
        ]}],
        "projects": [{"title": "Chat app", "description": [
            "Developed a real-time chat app used by 200 students",
            "Deployed on AWS with Kubernetes and Linux servers",
        ]}],
    }
    return parsed, entities


def test_strong_resume_scores_high():
    r = score_resume(*_good())
    assert r["readability_score"] >= 90, r["top_fixes"]
    assert r["grade"] == "Excellent"
    assert sum(c["max"] for c in r["categories"]) == 100
    assert r["role_match"] is None  # filled on Day 9


def test_weak_resume_scores_low_with_fixes():
    parsed = {"layout": _layout(columns=2, tables=2, images=3, body_font_size=8, word_count=150),
              "sections": {"experience": "x"}, "contact": {}}
    entities = {"location": None, "skills": [], "projects": [], "experience": [
        {"title": "Intern", "company": None, "bullets": [
            "Responsible for making the website of the company",
            "I worked on many tasks given by my manager"]}]}
    r = score_resume(parsed, entities)
    assert r["readability_score"] < 40
    assert r["grade"] == "Poor"
    fixes = " ".join(f["fix"] for f in r["top_fixes"])
    assert "table" in fixes.lower() or "Education" in fixes


def test_scanned_is_capped():
    parsed, entities = _good()
    parsed["layout"]["is_scanned"] = True
    assert score_resume(parsed, entities)["readability_score"] <= 15


def test_each_check_explains_itself():
    parsed, entities = _good()
    parsed["contact"]["linkedin"] = None
    r = score_resume(parsed, entities)
    li = next(c for cat in r["categories"] for c in cat["checks"] if c["id"] == "linkedin")
    assert li["passed"] is False and "linkedin.com/in" in li["fix"]


def test_action_verb_detection():
    assert _starts_with_action_verb("Built a CI/CD pipeline")
    assert _starts_with_action_verb("Successfully led a team of 5")
    assert not _starts_with_action_verb("Responsible for the database")
    assert not _starts_with_action_verb("I worked on APIs")


def test_ing_forms_of_action_verbs():
    assert _starts_with_action_verb("Supporting learners in bridging the gap")
    assert _starts_with_action_verb("Managing a team of 4 engineers")
    assert _starts_with_action_verb("Designing weekly sessions on CI/CD")
    assert not _starts_with_action_verb("Everything about the cloud")
