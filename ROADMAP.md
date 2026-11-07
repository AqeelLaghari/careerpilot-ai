# CareerPilot AI â€” 30-Day Build Roadmap

Start: Sun 8 Nov 2026 Â· Target finish: Mon 7 Dec 2026
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

## ATS design: hybrid, 3 layers (decided 8 Nov 2026)
1. **Rules (format/structure)**: how real ATS parsers behave: headings, tables, images, scanned, contact, action verbs, metrics, length. Explainable point deductions.
2. **Data-driven keywords**: required skills per role LEARNED from real job postings (TF-IDF / frequency), not hand-written. Advice like "Power BI appears in 52% of Data Analyst postings".
3. **Semantic (Sentence-BERT)**: meaning-based match, so "trained prediction models" ≈ "Machine Learning".

Scores shown: ATS readability (Layer 1, on upload) → Role match (Layers 2+3, after choosing a target role) → optional job-description match.
Validation (Day 23): Spearman correlation with 2–3 human expert ratings on about 20 CVs of mixed quality, plus a before/after fix test.

## Folder structure

```
CareerPilot AI/
â”œâ”€â”€ backend/            FastAPI + agents (Python)
â”‚   â”œâ”€â”€ app/
â”‚   â”‚   â”œâ”€â”€ main.py
â”‚   â”‚   â”œâ”€â”€ orchestrator/   blackboard.py (shared state), orchestrator.py
â”‚   â”‚   â”œâ”€â”€ agents/         resume_agent.py, career_agent.py, interview_agent.py
â”‚   â”‚   â”œâ”€â”€ services/       pdf_parser.py, ats_scorer.py, embeddings.py, whisper_service.py, llm.py
â”‚   â”‚   â””â”€â”€ routers/        resume.py, career.py, interview.py (incl. WebSocket)
â”‚   â”œâ”€â”€ data/           jobs.csv, skills.json, skill_graph.json, faiss.index
â”‚   â””â”€â”€ tests/
â”œâ”€â”€ frontend/           Flutter app (web + Android)
â”œâ”€â”€ evaluation/         labelled resumes + accuracy scripts (for the report)
â””â”€â”€ docs/
```

---

## CV collection checkpoints (all domains, no compromise)
Goal: about 40 CVs in `evaluation/resumes/` covering every domain below, in many formats.
- **By Day 7:** 10 CVs (different domains + formats) to catch parser bugs early
- **By Day 14:** 25 CVs; every domain row has at least 1
- **By Day 23:** 40 CVs; 25 hand-labelled for the accuracy/F1 table

| Domain group | Examples |
|---|---|
| Software | web frontend, backend, full-stack, mobile, game dev, embedded/IoT |
| Data & AI | data science, ML/AI, data analyst, data engineer |
| Infra & security | DevOps ✓, cloud, networking, cybersecurity, sysadmin |
| Quality & product | QA/testing, product/project manager, business analyst |
| Design | UI/UX, graphic design |
| Business | marketing/digital marketing, sales, finance/accounting, HR |
| Other | teaching, healthcare, engineering (mech/electrical/civil), fresh grad with no experience |

Formats to include: 1-column, 2-column, Canva/designed, Word export, with photo, 2+ pages, scanned image.
Sources: classmates (with permission) and the Kaggle "Resume Dataset" (Snehaan Bhawal, 24 categories).

## Week 1: Foundations + Resume Intelligence Agent
- [x] **Day 1**: Accounts (GitHub, Firebase, Gemini API key), git, Python venv, `flutter doctor`
- [x] **Day 2**: FastAPI skeleton, `/health`, Blackboard state class, Firebase Admin connection
- [x] **Day 3**: Flutter skeleton: Firebase Auth login/signup, navigation, empty dashboard
- [x] **Day 4**: PDF text extraction (PyMuPDF + pdfplumber) with layout info
- [x] **Day 5**: spaCy pipeline: skills EntityRuler, education, experience, dates, plus Gemini JSON fallback
- [ ] **Day 6**: ATS scorecard, Layer 1 (rule-based readability: headings, tables/images, scanned, contact, action verbs, metrics, length) + slots for role-keyword score
- [ ] **Day 7**: Flutter upload screen + ATS report UI. **Milestone 1: resume â†’ score works end-to-end**

## Week 2: Career Guide Agent
- [ ] **Day 8**: Job-POSTINGS dataset (Kaggle LinkedIn Job Postings, 100k+, all industries) → group by role → TF-IDF skill importance per role (ATS Layer 2); flag unknown skills for dictionary growth
- [ ] **Day 9**: Sentence-Transformers embeddings + FAISS index + `/career/match` (top 3); role match score (Layer 2 keywords + Layer 3 semantic) added to the ATS report; optional paste-a-job-description match
- [ ] **Day 10**: Adaptive questionnaire (asks only for what the resume is missing)
- [ ] **Day 11**: Skill-gap (set difference) + skill DAG (networkx topological sort) â†’ weekly roadmap
- [ ] **Day 12**: Flutter: questionnaire + career matches screens
- [ ] **Day 13**: Flutter: interactive roadmap (tick tasks; roadmap updates)
- [ ] **Day 14**: Buffer / bug fixing. **Milestone 2: resume â†’ career â†’ roadmap**

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

If you fall behind, cut these first: Android APK â†’ roadmap auto-update â†’ Gemini fallback in parsing.
