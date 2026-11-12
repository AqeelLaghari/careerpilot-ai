# CareerPilot AI — 30-Day Build Roadmap

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

## Live market learning (decided 8 Nov 2026)
Job-market data goes stale, so the app keeps learning from fresh job postings while it runs, with no code change or redeploy.
- **Training sources = ALL jobs (any location, remote or on-site):** the Kaggle dataset + every posting from the remote-job APIs (including US/EU-only ones, which users never see but still teach skills) + normal jobs from JSearch (`country=pk` and others, free key) and Careerjet (`en_PK`), so the model also learns Pakistani market skills. Never scrape LinkedIn, Indeed or Rozee.
- **Collect:** every fetched posting is saved (deduplicated) in Firestore.
- **Learn weekly:** terms that are frequent in recent postings but missing from the skill list become candidates (15+ postings, blocklist for words like "Urgent"/"Hybrid"). Gemini fast tier confirms them and assigns a category in ONE batched call. Approved skills go to Firestore and are hot-reloaded into the skill detector. `skills.json` stays the base list.
- **Trigger:** on a request, if the last update is more than 7 days old, run it in the background (works on free hosting that sleeps).
- **Re-weight:** role keyword weights and trending/declining skills are recomputed, newer postings weighted more.
- **Oversight:** an admin list of learned skills; any wrong skill can be removed.
- **Live jobs = REMOTE jobs a Pakistani can apply to (decided 8 Nov 2026):** sources Himalayas (has candidate-location restrictions + worldwide filter; check its terms on display first), Remotive, Jobicy, RemoteOK (all free, no key; link back/attribution required), optional JSearch `remote_jobs_only`. Keep only jobs open to Worldwide/Anywhere/Asia/APAC/Pakistan; dedupe; match % (skills + SBERT); "Open worldwide" badge; Apply → original posting; cache a few hours. Users see ONLY these remote jobs; every fetched posting (eligible or not) also feeds skill learning. Day 14 starts by counting Pakistan-eligible jobs per API and confirming terms.

## Live video interview (decided 13 Nov 2026)
The mock interview is a real, spoken conversation, not a list of recorded answers.
- **Length:** the user picks 5, 10 or 15 minutes; the interviewer keeps time and closes properly ("Any questions for me?").
- **Camera on for the whole interview** (live preview). Video is NEVER uploaded or recorded: MediaPipe analyses it in the browser and only eye-contact numbers go to the server.
- **AI voice:** questions are spoken with the device's free text-to-speech (`flutter_tts`: browser speechSynthesis on web, Android TTS on phones) and shown as text.
- **Turn-taking:** the user just talks; the turn ends after ~3 s of silence (or an "I'm done" button). Audio streams over the Day 16 WebSocket; Whisper (Day 17) transcribes.
- **Adaptive questions:** the Day 15 plan becomes the AGENDA (topics from the CV: intro, project, key skills, a gap skill, behaviour). After each answer Gemini (fast tier, one short call per turn) decides: follow-up, clarify, or next topic (max 2 follow-ups per topic). A short spoken acknowledgement covers the 3-6 s thinking gap.
- **Fallback:** if Gemini fails, the interview continues with the planned questions.
- **Report:** per-answer grading against key points, speech metrics, eye contact, tips.

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
- [x] **Day 6**: ATS scorecard, Layer 1 (rule-based readability: headings, tables/images, scanned, contact, action verbs, metrics, length) + slots for role-keyword score
- [x] **Day 7**: Flutter upload screen + ATS report UI. **Milestone 1: resume → score works end-to-end**

## Week 2: Career Guide Agent
- [x] **Day 8**: Job-POSTINGS dataset (Kaggle LinkedIn Job Postings, 100k+, all industries) → group by role → TF-IDF skill importance per role (ATS Layer 2). Built as a re-runnable `build_market_model.py` (any postings in → new weights out), newer postings weighted more, "market data updated: <date>, N postings" stamp; flag unknown skills for dictionary growth
- [x] **Day 9**: Sentence-Transformers embeddings + FAISS index + `/career/match` (top 3); role match score (Layer 2 keywords + Layer 3 semantic) added to the ATS report; optional paste-a-job-description match
- [x] **Day 10**: Adaptive questionnaire (asks only for what the resume is missing)
- [x] **Day 11**: Skill-gap (set difference) + skill DAG (networkx topological sort) → weekly roadmap
- [x] **Day 12**: Flutter: questionnaire + career matches screens; Android smoke test (Firebase Android config, backend address from phone, file picker, permissions)
- [x] **Day 13**: Flutter: interactive roadmap (tick tasks; roadmap updates)
- [x] **Day 14**: Self-learning market model + live REMOTE jobs (see "Live market learning" above): remote-job API clients (Himalayas, Remotive, Jobicy, RemoteOK) + Pakistan-eligibility filter + save postings to Firestore + new-skill discovery (Gemini fast, weekly batch) + skills in Firestore, hot-reloaded + trending skills + Jobs tab (match %, Apply). **Milestone 2: resume → career → roadmap**

## Week 3: Interview Coach Agent
- [x] **Day 15**: Question generation from blackboard (profile + target role)
- [x] **Day 16**: WebSocket endpoint; Flutter records and streams audio chunks
- [ ] **Day 17**: faster-whisper transcription, WPM, filler-word counter
- [ ] **Day 18**: Live camera preview for the whole interview + MediaPipe Face Landmarker in Flutter Web (JS interop), iris position
- [ ] **Day 19**: Eye-contact score + gaze-away log; AI voice (flutter_tts) + automatic end-of-answer (silence) detection
- [ ] **Day 20**: Live conversation loop (Gemini interviewer: follow-ups, time keeping, 5/10/15 min, planned-question fallback) + answer grading + combined interview score
- [ ] **Day 21**: Live video interview screen + final report. **Milestone 3: full live mock interview** (may use a Week 4 buffer day)

## Week 4: Integration, evaluation, deployment
- [ ] **Day 22**: Orchestrator synthesis; dashboard shows everything, live refresh; ATS score history across uploads; AI bullet rewriter button (Gemini fast tier, on click only)
- [ ] **Day 23**: Evaluation: parsing F1 on 25 labelled resumes; FAISS latency; WebSocket latency
- [ ] **Day 24**: Automated tests (pytest) + error handling + buffer / bug fixing
- [ ] **Day 25**: Deploy backend to Hugging Face Spaces
- [ ] **Day 26**: Deploy web to Firebase Hosting; build Android APK
- [ ] **Day 27**: Pilot test with 5 to 10 classmates (Google Form feedback)
- [ ] **Day 28**: Fix pilot feedback
- [ ] **Day 29**: README, architecture diagrams, results tables for the report
- [ ] **Day 30**: Demo video + defense rehearsal

If you fall behind, cut these first: Android APK → roadmap auto-update → Gemini fallback in parsing.
