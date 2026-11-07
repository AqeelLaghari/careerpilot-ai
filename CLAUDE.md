# CareerPilot AI — notes for Claude

FYP (Bahria University Karachi, Software Engineering, 2025-26). Team: Daniyal Jamil Awan, Aqeel, Abdul Mannan Butt. Supervisor: Prof. Dr. Engr. Ghulam Muhammad.

The user is a **beginner**. Explain each step in plain language, give exact commands (Windows PowerShell), and say what output to expect. Keep steps small; have the user run and confirm before moving on.

The plan lives in `ROADMAP.md`. Check which day is next and update the checkboxes when a day is done.

## Stack (fixed; don't change without asking)
- Frontend: Flutter (web first, Android second), Firebase Auth
- Backend: Python 3.11, FastAPI, venv at `backend/.venv`
- State: Blackboard pattern. `backend/app/orchestrator/blackboard.py` is the ONLY place agents read and write shared user state (Firestore + in-process cache). Agents never call each other directly.
- NLP: PyMuPDF, pdfplumber, spaCy (`en_core_web_sm` + EntityRuler skills), Gemini free tier as LLM
- Matching: sentence-transformers `all-MiniLM-L6-v2` + FAISS (IndexFlatIP on normalized vectors = cosine)
- Roadmap: networkx DAG + topological sort
- ATS: HYBRID, 3 layers (rules for format + keywords learned from job postings via TF-IDF + SBERT semantic match). See ROADMAP.md. Never hand-write per-role keyword lists.
- Interview: WebSocket, faster-whisper (`base` model, CPU int8), MediaPipe Face Landmarker on web via JS interop
- LLM calls ONLY via `app/services/llm.py`: tier="fast" (Flash-Lite) for simple/frequent tasks, tier="smart" (Flash) only for interview grading/final feedback. Batch requests, store results on the Blackboard, and always have a rule-based fallback when it returns None.
- Zero budget: free tiers only. Never add paid services.

## Conventions
- Secrets live in `backend/.env` and `backend/firebase-key.json` (both git-ignored). Never print or commit them.
- Commit after every working step. Push to GitHub (`origin main`) at the end of each roadmap day; the user approved this. Run `git pull` first if teammates may have pushed.
