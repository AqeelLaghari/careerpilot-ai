# How we work

## One-time setup
1. Backend venv and tools: see "Run it locally" in the README (`pip install -r backend/requirements-dev.txt`).
2. Turn on the pre-commit checks (from the project folder):
   ```powershell
   backend\.venv\Scripts\pre-commit.exe install
   ```
   On Windows with the Microsoft Store Python, first run this once (avoids a "path too long" error):
   ```powershell
   [Environment]::SetEnvironmentVariable("VIRTUALENV_APP_DATA", "$env:USERPROFILE\.vapp", "User")
   ```

## Every change: branch -> pull request -> CI -> review -> merge
1. Get the latest `main`:
   ```powershell
   git checkout main
   git pull
   ```
2. Make a branch named after the work:
   `feature/<name>` (new feature), `fix/<name>` (bug), `devops/<name>` (CI, Docker, deploy), `docs/<name>`
   ```powershell
   git checkout -b feature/urdu-interview
   ```
3. Commit in small working steps. The pre-commit checks run automatically; if one fails, fix it
   and commit again.
4. Push the branch and open a pull request on GitHub (the template asks what changed and how it was tested):
   ```powershell
   git push -u origin feature/urdu-interview
   ```
5. CI runs on the pull request. Wait for all checks to be green.
6. A teammate reviews and approves. Then **Squash and merge**, and delete the branch.

## Rules
- Never commit `.env`, `firebase-key.json`, CVs (`evaluation/resumes/`) or anything in `backend/data/raw/`.
  The pre-commit hook and the CI secret scan block most mistakes, but check your diff anyway.
- New logic comes with tests. CI must stay green on `main`.
- LLM calls only through `backend/app/services/llm.py`, always with a rule-based fallback.
- Free tiers only.

## Versions and releases
Semantic versioning: `vMAJOR.MINOR.PATCH` (e.g. `v1.0.0`). A release is a Git tag plus a GitHub
Release with notes (from Day 29 the Android APK is attached automatically).
