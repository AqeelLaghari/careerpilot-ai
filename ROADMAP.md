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
- **Turn end:** 3 s of quiet after speaking (countdown shown from 1 s; background noise = quietest moment of the last 4 s, so soft voices count); the next question is prepared early at the first pause.
- **Grading (decided 14 Nov 2026):** content 60% (Gemini smart tier, one call per interview: correctness with corrections, relevance, completeness vs key points, specifics, STAR), speaking 20%, presence 20%. Personal claims can't be verified; technical facts are. Rule-based fallback: SBERT match against key points.
- **Interviewer style (decided 14 Nov 2026):** like a real first round: calm, neutral, never says an answer is right or wrong and never lectures. A clear technical mistake gets a gentle probing follow-up ("Are you sure about that?", "How is a container different from a VM?", "Walk me through that step again"), a vague answer gets "what did you do / what was the result?". Possible mishearings and personal claims are not probed. The silent check (mistake / vague + note) is saved per answer for the Day 21 report, where the corrections are shown.
- **Urdu interviews (decided 14 Nov 2026, a MAIN feature, not beta):** language choice English / Urdu for the whole interview: questions in Urdu (Roman Urdu subtitles), Urdu voice (Android Google Urdu voice; on web the best available, with a clear fallback), answers in Urdu or mixed Urdu-English, Whisper tuned for Urdu (model size chosen by testing speed vs accuracy), Urdu filler words (matlab, yani, acha, woh...), Urdu pace range, grading and report in Roman Urdu.

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
- [x] **Day 17**: faster-whisper transcription, WPM, filler-word counter
- [x] **Day 18**: Live camera preview for the whole interview + MediaPipe Face Landmarker in Flutter Web (JS interop), iris position
- [x] **Day 19**: Eye-contact score + gaze-away log; AI voice (flutter_tts) + automatic end-of-answer (silence) detection
- [x] **Day 20**: Live conversation loop (Gemini interviewer: follow-ups, gentle probing of mistakes, time keeping, 5/10/15 min, planned-question fallback) + live video interview screen (camera full screen, subtitles, End). Answer grading moved to Day 21.
- [x] **Day 21**: Answer grading (correctness with corrections, key points, STAR) + combined interview score (content 60 / speaking 20 / presence 20) + final report screen. **Milestone 3: full live mock interview** (may use a Week 4 buffer day)

## Week 4+: DevOps, accounts, design, evaluation, deployment (re-planned 15 Nov 2026, still before 7 Dec)
- [x] **Day 22**: **DevOps foundation** (see "DevOps" below): GitHub Actions CI (backend tests + coverage, flutter analyze/test, ruff + dart format, gitleaks secret scan), backend Dockerfile + docker-compose (image built in CI), pre-commit hooks (formatting, block .env / firebase-key), Dependabot, PR + issue templates, feature-branch + pull-request workflow, GitHub Projects board
- [x] **Day 23**: **Accounts & profile**: new login / sign-up design, Continue with Google, password rules (live checklist + strength bar), forgot password, email verification, 3-step profile setup (student / graduate / professional, university, degree, semester or graduation year, city, target role, links), profile photo (resized on device, stored in Firestore: Firebase Storage is not free), "My profile" page; profile details pre-fill the questionnaire and the interviewer greeting
- [x] **Day 24**: **New look**: design system (Inter/Poppins font, palette, cards, skeleton loading, empty states, animations, dark mode), left sidebar on web (photo, name, university) / bottom tabs on phone, profile dropdown menu (profile, target role, settings: theme / voice / language, help, log out with confirm), new dashboard (score tiles, "your next step", ATS score history chart, recent activity) = orchestrator synthesis with live refresh; AI bullet rewriter button (Gemini fast, on click only)
- [x] **Day 25**: Restyle Resume, Career, Jobs, Interview and the report in the new look
- [ ] **Day 26**: Evaluation: parsing F1 on 25 labelled resumes (needs non-tech CVs); FAISS latency; WebSocket / interviewer latency
- [ ] **Day 27**: **Urdu interviews** (full feature, see "Live video interview") + error handling / bug fixing
- [ ] **Day 28**: **CD backend**: Docker image auto-deployed to Hugging Face Spaces by GitHub Actions on push to main (secrets in GitHub / HF), /debug endpoints off in production, structured logs, UptimeRobot monitoring of /health
- [ ] **Day 29**: **CD web + mobile**: auto-deploy to Firebase Hosting; Android APK built by GitHub Actions and attached to a GitHub Release (tag v1.0.0, release notes)
- [ ] **Day 30**: Pilot test with 5 to 10 classmates (Google Form feedback)
- [ ] **Day 31**: Fix pilot feedback
- [ ] **Day 32**: README (with CI badges), architecture + **CI/CD pipeline diagrams**, results tables for the report
- [ ] **Day 33**: Demo video + defense rehearsal

## DevOps (decided 15 Nov 2026; the team's DevOps member does the hands-on parts from his own GitHub account)
- **CI (GitHub Actions, free):** every push / pull request runs pytest with coverage, flutter analyze + test, ruff and dart format checks, gitleaks; status badges in the README.
- **Containers:** backend Dockerfile (Python 3.11, Whisper, spaCy, SBERT models) + docker-compose for one-command local runs; the same image deploys to Hugging Face Spaces.
- **CD:** main → Hugging Face Spaces (backend) and Firebase Hosting (web); tag vX.Y.Z → APK built and attached to a GitHub Release.
- **Workflow:** feature branches → pull request → CI must pass → review → merge; PR / issue templates; GitHub Projects board; semantic versioning; Dependabot updates. Branch protection needs a public repo (free) or a paid plan.
- **Quality and security:** pre-commit hooks (format, block secrets), secret scanning, secrets only in GitHub / HF secret stores and git-ignored files.
- **Monitoring:** UptimeRobot on /health, structured logs, request timing; debug endpoints disabled in production.
- **Docs:** pipeline diagram, screenshots of pipeline runs, DevOps section in the report.

## Future work (not in this FYP; for the report's "Future work" section)
- **Recruiter accounts** (decided 15 Nov 2026: not now): recruiters post jobs, search and shortlist candidates by ATS score / skills / interview results, invite candidates to an AI screening interview. Accounts in this FYP are for students, fresh graduates and working professionals.

If you fall behind, cut these first: Android APK → roadmap auto-update → Gemini fallback in parsing.
