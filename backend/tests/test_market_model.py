"""Market model (ATS Layer 2): build from a tiny fake postings CSV, then query it."""
import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from app.services import market_model
from app.services.market_model import normalize_title

ROOT = Path(__file__).resolve().parent.parent


def _load_build_script():
    spec = importlib.util.spec_from_file_location("build_market_model", ROOT / "scripts" / "build_market_model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("raw,expected", [
    ("Sr. Software Engineer II - Backend (Remote)", "Software Engineer"),
    ("Senior DevOps Engineer, Cloud Platform", "DevOps Engineer"),
    ("Registered Nurse - ICU Night Shift", "Registered Nurse"),
    ("Junior Data Analyst | Hybrid", "Data Analyst"),
    ("Senior UX Designer", "UX Designer"),
    ("Back-End Developer", "Backend Developer"),
    ("Front End Engineer (React)", "Frontend Engineer"),
    ("Full-Stack Developer", "Full Stack Developer"),
    ("HR Business Partner", "HR Business Partner"),
])
def test_normalize_title(raw, expected):
    assert normalize_title(raw) == expected


@pytest.fixture
def built_model(tmp_path, monkeypatch):
    """Build a model from 3 fake roles x 12 postings in a temp folder."""
    raw = tmp_path / "raw"
    raw.mkdir()
    rows = []
    for i in range(12):
        rows.append(("Senior DevOps Engineer", "We need Docker, Kubernetes, Terraform, AWS, Linux and Jenkins. "
                     f"Good communication. Ref {i}.", 1_700_000_000_000 + i))
        rows.append(("Data Analyst", "Strong SQL, Python, Tableau, Power BI, Excel and statistics skills. "
                     f"Good communication. Ref {i}.", 1_700_000_000_000 + i))
        rows.append(("Registered Nurse", "Patient Care, CPR, BLS certification, Vital Signs, Infection Control, "
                     f"Medical Terminology. Good communication. Ref {i}.", 1_700_000_000_000 + i))
    pd.DataFrame(rows, columns=["title", "description", "listed_time"]).to_csv(raw / "postings.csv", index=False)

    script = _load_build_script()
    monkeypatch.setattr(script, "RAW_DIR", raw)
    monkeypatch.setattr(script, "MODEL_PATH", tmp_path / "market_model.json")
    monkeypatch.setattr(script, "CANDIDATES_PATH", tmp_path / "market_candidates.json")
    monkeypatch.setattr(market_model, "MODEL_PATH", tmp_path / "market_model.json")
    market_model.load_model.cache_clear()
    model = script.build(limit=None, min_postings=10, half_life_days=365, top_k=40)
    yield model
    market_model.load_model.cache_clear()


def test_build_learns_roles_and_skills(built_model):
    roles = built_model["roles"]
    assert set(roles) == {"DevOps Engineer", "Data Analyst", "Registered Nurse"}
    devops = [s["name"] for s in roles["DevOps Engineer"]["skills"]]
    assert {"Docker", "Kubernetes", "Terraform"} <= set(devops)
    assert roles["Registered Nurse"]["category"] == "healthcare"


def test_idf_lowers_skills_every_role_has(built_model):
    """'Communication' appears in ALL roles, so it must weigh less than role-specific skills."""
    skills = {s["name"]: s["weight"] for s in built_model["roles"]["Data Analyst"]["skills"]}
    assert skills["Communication"] < skills["Tableau"]


def test_find_role_and_coverage(built_model):
    assert market_model.find_role("devops engineer (remote)") == "DevOps Engineer"
    assert market_model.find_role("Junior Data Analyst") == "Data Analyst"
    cov = market_model.keyword_coverage(["Docker", "Kubernetes", "Python"], "DevOps Engineer")
    assert 0 < cov["score"] < 100
    assert "Docker" in cov["matched"] and "Terraform" in [m["name"] for m in cov["missing"]]


def test_unknown_role_returns_none(built_model):
    assert market_model.keyword_coverage(["Docker"], "Astronaut") is None


def test_market_endpoints(built_model):
    from fastapi.testclient import TestClient

    from app.main import app
    client = TestClient(app)
    info = client.get("/market/info").json()
    assert info["roles"] == 3 and info["postings_used"] == 36
    roles = client.get("/market/roles", params={"q": "nurse"}).json()
    assert roles[0]["role"] == "Registered Nurse"
    prof = client.get("/market/roles/devops engineer").json()
    assert prof["role"] == "DevOps Engineer" and prof["skills"][0]["weight"] == 1.0
    assert client.get("/market/roles/astronaut").status_code == 404


def test_find_role_handles_spelling_synonyms_and_unsure_titles(built_model, monkeypatch):  # noqa: F811
    from app.services import llm
    mm = market_model
    mm._gemini_pick.cache_clear()
    assert mm.find_role("Dev-Ops Engineer") == "DevOps Engineer"            # same letters, other spelling
    assert mm.find_role("RN nurse") == "Registered Nurse"                   # meaning, not just words
    assert mm.find_role("zzzz qqqq") is None
    # unsure case: Gemini picks from the closest roles; an answer outside the list is ignored
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: {"role": "data analyst"})
    mm._gemini_pick.cache_clear()
    assert mm.find_role("Numbers and dashboards person") == "Data Analyst"
    monkeypatch.setattr(llm, "generate_json", lambda *a, **k: {"role": "Astronaut"})
    mm._gemini_pick.cache_clear()
    assert mm.find_role("Space walker") is None
    mm._gemini_pick.cache_clear()
