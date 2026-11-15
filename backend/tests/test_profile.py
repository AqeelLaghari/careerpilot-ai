"""Account profile, photo and email verification (Day 23). Firebase is faked."""
import base64
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.auth import current_uid
from app.main import app
from app.orchestrator.blackboard import Blackboard
from app.routers import profile as profile_router
from app.services import account_profile as ap
from app.services import interviewer as iv
from app.services import privacy
from app.services.profile import merged_answers

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 2000
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


# ---------------------------------------------------------------- validation --
def test_clean_accepts_a_full_profile():
    p = ap.clean({"full_name": "  Aqeel   Laghari ", "status": "student", "university": "Bahria University",
                  "degree": "BS Software Engineering", "semester": 7, "graduation_year": 2027, "city": "Karachi",
                  "target_role": "Data Scientist", "linkedin": "linkedin.com/in/someone", "github": "",
                  "phone": "+92 300 1234567", "completed": True}, year=2026)
    assert p["full_name"] == "Aqeel Laghari" and p["semester"] == 7 and p["github"] is None
    assert p["linkedin"] == "https://linkedin.com/in/someone" and p["completed"] is True


def test_clean_reports_each_bad_field():
    with pytest.raises(ap.ProfileError) as e:
        ap.clean({"full_name": "R2D2", "status": "pilot", "semester": 15, "graduation_year": 2099,
                  "phone": "call me", "github": "gitlab.com/x", "colour": "blue"}, year=2026)
    assert set(e.value.errors) == {"full_name", "status", "semester", "graduation_year", "phone", "github", "colour"}


def test_names_in_any_alphabet_and_with_initials():
    for name in ["Muhammad A. Khan", "O'Brien", "Anne-Marie", "عقیل لغاری"]:
        assert ap.clean({"full_name": name})["full_name"] == name


def test_semester_dropped_for_graduates():
    p = ap.clean({"status": "student", "semester": 5})
    assert "semester" not in ap.clean({"status": "graduate"}, p)


def test_photo_checks():
    assert ap.check_photo(JPEG) == "image/jpeg" and ap.check_photo(PNG) == "image/png"
    for bad in [b"", b"GIF89a....", b"\xff\xd8\xff" + b"\x00" * (ap.MAX_PHOTO_BYTES + 1)]:
        with pytest.raises(ap.ProfileError):
            ap.check_photo(bad)


# ------------------------------------------------- shared with other agents --
def test_profile_answers_stop_repeated_questions():
    account = {"status": "student", "graduation_year": 2027, "updated_at": 1}
    answers = merged_answers({"answers": {"interests": {"value": ["data_ai"]}}}, account)
    assert answers["career_stage"]["value"] == "student" and answers["graduation_year"]["value"] == 2027
    real = merged_answers({"answers": {"career_stage": {"value": "career_switch"}}}, account)
    assert real["career_stage"]["value"] == "career_switch"          # a real answer wins


def test_interviewer_prefers_the_profile():
    cv = {"name": "MUHAMMAD AQEEL", "education": [{"institution": "OLD COLLEGE", "end_year": 2015}]}
    who = iv.candidate_info(cv, 2026, account={"full_name": "Aqeel Laghari", "university": "Bahria University",
                                                "degree": "BS Software Engineering", "status": "student"})
    assert who["first_name"] == "Aqeel" and who["university"] == "Bahria University"
    assert who["subject"] == "BS Software Engineering" and who["studying"] is True


def test_privacy_includes_profile_details():
    terms = privacy.terms({}, {"full_name": "Aqeel Laghari", "university": "Bahria University", "city": "Karachi",
                               "linkedin": "https://linkedin.com/in/aqeel-l"})
    text = "I'm Aqeel from Bahria University in Karachi, see linkedin.com/in/aqeel-l"
    assert privacy.scrub(text, terms) == "I'm [name] from [university] in [place], see [link]"


# ------------------------------------------------------------------ the API --
@pytest.fixture
def client(monkeypatch):
    bb = Blackboard(db=None)
    monkeypatch.setattr(profile_router, "blackboard", bb)
    monkeypatch.setattr(profile_router.career_agent, "bb", bb)
    app.dependency_overrides[current_uid] = lambda: "u1"
    yield TestClient(app), bb
    app.dependency_overrides.clear()


def test_profile_api_save_and_suggest(client):
    c, bb = client
    bb.write("u1", "resume", {"entities": {"name": "AQEEL LAGHARI", "location": "Karachi, Pakistan",
                                           "education": [{"institution": "Bahria University", "degree": "BS SE",
                                                          "degree_level": "Bachelors", "end_year": 2027}]}}, agent="t")
    first = c.get("/profile").json()
    assert first["completed"] is False and first["suggested"]["full_name"] == "Aqeel Laghari"
    assert first["suggested"]["university"] == "Bahria University" and first["suggested"]["city"] == "Karachi"
    r = c.put("/profile", json={"full_name": "Aqeel Laghari", "status": "student", "completed": True})
    assert r.status_code == 200 and r.json()["completed"] is True
    bad = c.put("/profile", json={"semester": 40})
    assert bad.status_code == 422 and "semester" in bad.json()["detail"]["errors"]
    assert bb.read_section("u1", "profile")["full_name"] == "Aqeel Laghari"        # unchanged by the bad one


def test_photo_api(client):
    c, bb = client
    assert c.get("/profile/photo").status_code == 404
    r = c.put("/profile/photo", json={"image": "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()})
    assert r.status_code == 200 and r.json()["has_photo"]
    got = c.get("/profile/photo")
    assert got.content == JPEG and got.headers["content-type"] == "image/jpeg"
    assert got.headers["cache-control"] == "no-store"      # never show another account's cached photo
    assert c.get("/profile").json()["has_photo"] is True
    assert c.put("/profile/photo", json={"image": "not base64!"}).status_code == 422
    assert c.put("/profile/photo", json={"image": base64.b64encode(b"GIF89a").decode()}).status_code == 422
    c.delete("/profile/photo")
    assert c.get("/profile/photo").status_code == 404 and c.get("/profile").json()["has_photo"] is False


# -------------------------------------------------------- email verification --
@pytest.fixture
def firebase(monkeypatch):
    accounts = {}

    def verify(token):
        if token not in accounts:
            raise ValueError("bad token")
        return accounts[token]["claims"]

    def get_user(uid):
        created = next(a["created"] for a in accounts.values() if a["claims"]["uid"] == uid)
        return SimpleNamespace(user_metadata=SimpleNamespace(creation_timestamp=created))

    monkeypatch.setattr(auth.fb_auth, "verify_id_token", verify)
    monkeypatch.setattr(auth.fb_auth, "get_user", get_user)
    monkeypatch.setattr(auth, "VERIFY_EMAIL_FROM", "2026-11-16")
    auth._created.clear()
    auth._cutoff.cache_clear()

    def add(token, uid, provider, verified, created_iso):
        from datetime import datetime, timezone
        ms = datetime.fromisoformat(created_iso).replace(tzinfo=timezone.utc).timestamp() * 1000
        accounts[token] = {"claims": {"uid": uid, "email_verified": verified,
                                      "firebase": {"sign_in_provider": provider}}, "created": ms}
    yield add
    auth._created.clear()
    auth._cutoff.cache_clear()


def test_new_unverified_email_accounts_are_blocked(firebase):
    firebase("new", "u-new", "password", False, "2026-11-20")
    firebase("new-ok", "u-new2", "password", True, "2026-11-20")
    firebase("old", "u-old", "password", False, "2026-11-10")          # test account from before Day 23
    firebase("google", "u-g", "google.com", False, "2026-11-20")
    with pytest.raises(Exception) as e:
        current_uid("Bearer new")
    assert e.value.status_code == 403 and "verify" in e.value.detail
    assert auth.uid_from_token("new") is None                           # the WebSockets too
    assert current_uid("Bearer new-ok") == "u-new2"
    assert current_uid("Bearer old") == "u-old"
    assert current_uid("Bearer google") == "u-g"
    with pytest.raises(Exception) as e:
        current_uid("Bearer nonsense")
    assert e.value.status_code == 401
