# CareerPilot AI

[![CI](https://github.com/AqeelLaghari/careerpilot-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/AqeelLaghari/careerpilot-ai/actions/workflows/ci.yml)
[![Docker](https://github.com/AqeelLaghari/careerpilot-ai/actions/workflows/docker.yml/badge.svg)](https://github.com/AqeelLaghari/careerpilot-ai/actions/workflows/docker.yml)

**Your 24/7 AI career counselor.** Upload your CV and CareerPilot AI scores it like an applicant
tracking system (ATS), matches you to careers, builds a week-by-week learning roadmap, finds remote
jobs open to Pakistani candidates, and runs a **live video mock interview** with a spoken AI
interviewer and a graded feedback report.

Final Year Project, BS Software Engineering, Bahria University Karachi (2025-26).
Team: Daniyal Jamil Awan, Aqeel, Abdul Mannan Butt. Supervisor: Prof. Dr. Engr. Ghulam Muhammad.

## Features
| Agent | What it does |
|---|---|
| **Resume Analyzer** | PDF parsing (PyMuPDF, pdfplumber), entity extraction (spaCy + skill EntityRuler), hybrid ATS score: format rules + role keywords learned from job postings (TF-IDF) + semantic match (SBERT) |
| **Career Guide** | Career matching (sentence-transformers + FAISS), adaptive questionnaire, skill-gap roadmap (networkx DAG + topological sort), live remote jobs, self-learning skill dictionary |
| **Interview Coach** | Live video interview: adaptive Gemini interviewer, faster-whisper speech-to-text, speaking metrics, eye contact (MediaPipe in the browser), graded report (content 60 / speaking 20 / presence 20) |

Agents never call each other: they share state through a **Blackboard** (`backend/app/orchestrator/blackboard.py`, Firestore).

## Tech stack
Flutter (web + Android) · Firebase Auth · Python 3.11 · FastAPI · WebSockets · spaCy · sentence-transformers · FAISS · faster-whisper · MediaPipe · Gemini (free tier) · Docker · GitHub Actions

## Run it locally
**Backend** (Windows PowerShell):
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
copy .env.example .env          # then fill in your own keys
uvicorn app.main:app --reload   # http://localhost:8000/health
```
**Or with Docker** (needs Docker Desktop): `docker compose up --build`

**Frontend:**
```powershell
cd frontend
flutter pub get
flutter run -d chrome
```

## Tests and code quality
```powershell
cd backend; pytest --cov=app        # backend tests + coverage
ruff check app tests scripts        # Python linter
cd ..\frontend; flutter analyze; flutter test
```

## DevOps
- **CI** (GitHub Actions, `.github/workflows/ci.yml`): every push and pull request runs the backend tests with coverage, ruff, `dart format`, `flutter analyze`, `flutter test` and a gitleaks secret scan.
- **Docker** (`backend/Dockerfile`, `.github/workflows/docker.yml`): the backend image is built and smoke-tested on every backend change (container must answer `/health`; debug endpoints must not exist in production).
- **Pre-commit hooks** (`.pre-commit-config.yaml`): formatting, linting, secret scanning and a block on secret files before every commit.
- **Dependabot**: weekly dependency update pull requests, tested by CI.
- **Workflow**: feature branches, pull requests with a template, review, merge when CI is green. See [CONTRIBUTING.md](CONTRIBUTING.md).
- **Planned** (see [ROADMAP.md](ROADMAP.md)): automatic deployment to Hugging Face Spaces and Firebase Hosting, APK builds on GitHub Releases, uptime monitoring.

## Privacy
Video never leaves the browser (only "where you looked" letters are sent). Interview audio is deleted
right after transcription. Names, universities, companies, emails and phone numbers are replaced with
placeholders before any text is sent to Gemini. Secrets live only in git-ignored files and secret stores.

## Development tools
Development was assisted by Claude Code (an AI coding assistant). Features were specified, reviewed and
tested by the team.
