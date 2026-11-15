"""Environments (Day 22, DevOps): production has no debug endpoints; /health reports the version."""
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

BACKEND = Path(__file__).resolve().parent.parent


def _routes(env: str) -> set[str]:
    """Import the app in a fresh Python with APP_ENV set, and list its URL paths."""
    code = "from app.main import app; print('\\n'.join(r.path for r in app.routes))"
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True,
                         env=os.environ | {"APP_ENV": env}, timeout=120)
    assert out.returncode == 0, out.stderr[-2000:]
    return set(out.stdout.split())


def test_debug_endpoints_only_in_development():
    assert "/debug/state/{uid}" in _routes("development")
    prod = _routes("production")
    assert "/debug/state/{uid}" not in prod and "/health" in prod


def test_health_reports_version_and_environment():
    r = TestClient(app).get("/health").json()
    assert r["status"] == "ok" and r["version"] and r["environment"] in ("development", "production")
