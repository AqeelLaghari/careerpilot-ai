# CareerPilot AI — 30-Day Build Roadmap

Start: Sun 8 Nov 2026 · Target finish: Mon 7 Dec 2026
Budget: Claude Pro ($20) + free tiers only (Firebase Spark, Gemini API free tier, Hugging Face Spaces).

Tick each box when it's done and committed to git.

---

## Scope decisions (what we build vs. what the proposal says)

| Proposal says | What we build | Why |
|---|---|---|
| Custom-trained spaCy NER, 90% accuracy | spaCy pipeline + EntityRuler (skills dictionary, ~2,000 skills) + Gemini structured extraction as a fallback. We measure precision/recall/F1 on 25 hand-labelled resumes | Training a real NER model needs hundreds of labelled resumes, which we can't make in 30 days. This is still a spaCy pipeline, and we report a real F1 |
| Redis + Firestore blackboard | Firestore (persistent) + in-process Python cache with the same interface | Redis needs a paid or self-hosted server. We can swap it in later without changing agent code |
| OpenAI Whisper | `faster-whisper` (same Whisper models, runs free on CPU) | No API cost |
| Gemini/OpenAI API | Gemini API free tier | $0 |
| MediaPipe Face Mesh on mobile + web | MediaPipe Face Landmarker (iris) on **Flutter Web**. Mobile gets every feature except eye tracking | MediaPipe iris tracking has no stable Flutter mobile plugin. Web gives the panel a full demo |
| AWS/GCP deployment | Backend on Hugging Face Spaces (Docker, free 16 GB RAM), web app on Firebase Hosting, Android APK | Free |

---

## Folder structure

```
CareerPilot AI/
├── backend/            FastAPI + agents (Python)
│   ├── app/
│   │   ├── main.py
│   │   ├── orchestrator/   blackboard.py (shared state), orchestrator.py
│   │   ├── agents/         resume_agent.py, career_agent.py, interview_agent.py
│   │   ├── services/       pdf_parser.py, ats_scorer.py, embeddings.py, whisper_service.py, llm.py
│   │   └── routers/        resume.py, career.py, interview.py (incl. WebSocket)
│   ├── data/           jobs.csv, skills.json, skill_graph.json, faiss.index
│   └── tests/
├── frontend/           Flutter app (web + Android)
├── evaluation/         labelled resumes + accuracy scripts (for the report)
└── docs/
```

---

## Week 1: Foundations + Resume Intelligence Agent
- [ ] **Day 1**: Accounts (GitHub, Firebase, Gemini API key), git, Python venv, `flutter doctor`
- [ ] **Day 2**: FastAPI skeleton, `/health`, Blackboard state class, Firebase Admin connection
- [ ] **Day 3**: Flutter skeleton: Firebase Auth login/signup, navigation, empty dashboard
- [ ] **Day 4**: PDF text extraction (PyMuPDF + pdfplumber) with layout info
- [ ] **Day 5**: spaCy pipeline: skills EntityRuler, education, experience, dates, plus Gemini JSON fallback
- [ ] **Day 6**: ATS scorecard (sections, keyword density, formatting issues, fix suggestions)
- [ ] **Day 7**: Flutter upload screen + ATS report UI. **Milestone 1: resume → score works end-to-end**

## Week 2: Career Guide Agent
- [ ] **Day 8**: Job-role dataset (O*NET / Kaggle) cleaned to about 300 to 1,000 roles
- [ ] **Day 9**: Sentence-Transformers embeddings + FAISS index + `/career/match` (top 3)
- [ ] **Day 10**: Adaptive questionnaire (asks only for what the resume is missing)
- [ ] **Day 11**: Skill-gap (set difference) + skill DAG (networkx topological sort) → weekly roadmap
- [ ] **Day 12**: Flutter: questionnaire + career matches screens
- [ ] **Day 13**: Flutter: interactive roadmap (tick tasks; roadmap updates)
- [ ] **Day 14**: Buffer / bug fixing. **Milestone 2: resume → career → roadmap**

## Week 3: Interview Coach Agent
- [ ] **Day 15**: Question generation from blackboard (profile + target role)
- [ ] **Day 16**: WebSocket endpoint; Flutter records and streams audio chunks
- [ ] **Day 17**: faster-whisper transcription, WPM, filler-word counter
- [ ] **Day 18**: MediaPipe Face Landmarker in Flutter Web (JS interop), iris position
- [ ] **Day 19**: Eye-contact score + gaze-away log
- [ ] **Day 20**: Answer grading (Gemini) + combined interview score
- [ ] **Day 21**: Interview screen + report. **Milestone 3: full mock interview**

## Week 4: Integration, evaluation, deployment
- [ ] **Day 22**: Orchestrator synthesis; dashboard shows everything, live refresh
- [ ] **Day 23**: Evaluation: parsing F1 on 25 labelled resumes; FAISS latency; WebSocket latency
- [ ] **Day 24**: Automated tests (pytest) + error handling
- [ ] **Day 25**: Deploy backend to Hugging Face Spaces
- [ ] **Day 26**: Deploy web to Firebase Hosting; build Android APK
- [ ] **Day 27**: Pilot test with 5 to 10 classmates (Google Form feedback)
- [ ] **Day 28**: Fix pilot feedback
- [ ] **Day 29**: README, architecture diagrams, results tables for the report
- [ ] **Day 30**: Demo video + defense rehearsal

If you fall behind, cut these first: Android APK → roadmap auto-update → Gemini fallback in parsing.
