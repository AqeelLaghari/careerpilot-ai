from fastapi.testclient import TestClient

from app.auth import current_uid
from app.main import app
from app.orchestrator.blackboard import Blackboard
from app.routers import resume as resume_router


def test_upload_end_to_end(single_column_pdf, monkeypatch):
    bb = Blackboard()  # in-memory: tests never touch real Firestore
    monkeypatch.setattr(resume_router.agent, "bb", bb)
    monkeypatch.setattr("app.services.llm.available", lambda: False)
    app.dependency_overrides[current_uid] = lambda: "test-user"
    try:
        client = TestClient(app)
        r = client.post("/resume/upload", files={"file": ("cv.pdf", single_column_pdf, "application/pdf")})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["entities"]["name"] == "Ali Raza"
        assert 0 < body["ats"]["readability_score"] <= 100
        assert bb.read("test-user")["resume"]["ats"]["version"] == "ats-layer1-v1"

        bad = client.post("/resume/upload", files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
        assert bad.status_code == 400
    finally:
        app.dependency_overrides.clear()
