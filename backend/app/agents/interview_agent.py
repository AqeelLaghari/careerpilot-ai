"""Interview Coach Agent (Week 3).

Reads from the Blackboard: "resume" (skills, projects, experience), "questionnaire"
(career stage, extra skills), "roadmap" (skills learned since), "career" (target role).
Writes: "interviews" (sessions with their questions; answers and scores come later).
It never calls the other agents; everything it needs is on the Blackboard.
"""
import logging
import time
from collections import Counter

from app.orchestrator.blackboard import Blackboard
from app.services import career_matcher, market_model
from app.services import interview_questions as iq
from app.services.profile import build_profile, merged_answers

AGENT_NAME = "interview_agent"
KEEP_SESSIONS = 10          # older sessions are dropped (one Firestore doc per user: max 1 MB)
KEEP_ASKED = 300            # question fingerprints remembered, so questions are not repeated
RECENT_FOR_SKILLS = 3       # sessions looked at when choosing less-practised skills


class NoResumeError(LookupError):
    pass


class InterviewAgent:
    def __init__(self, blackboard: Blackboard):
        self.bb = blackboard

    def _state(self, uid: str) -> dict:
        return self.bb.read_section(uid, "interviews") or {"sessions": [], "asked": []}

    def _role(self, uid: str, profile: dict, role: str | None) -> str | None:
        if role:
            return market_model.find_role(role) or role.strip()
        career = self.bb.read_section(uid, "career") or {}
        if career.get("target_role"):
            return career["target_role"]
        if career.get("matches"):
            return career["matches"][0]["role"]
        best = career_matcher.match_careers(profile, top_k=1) or []
        return best[0]["role"] if best else None

    def new_session(self, uid: str, count: int = iq.DEFAULT_COUNT, role: str | None = None) -> dict:
        """Plan and write a fresh set of questions for this user and store it."""
        resume = self.bb.read_section(uid, "resume")
        if not resume:
            raise NoResumeError("Upload a resume first")
        profile, answers = build_profile(resume["entities"], self.bb.read_section(uid, "questionnaire"),
                                         self.bb.read_section(uid, "roadmap"), self.bb.read_section(uid, "profile"))
        role = self._role(uid, profile, role) or (profile.get("headline") or "professional")
        coverage = market_model.keyword_coverage([s["name"] for s in profile.get("skills", [])], role)
        state = self._state(uid)
        recent = Counter(q["skill"].lower() for s in state["sessions"][-RECENT_FOR_SKILLS:]
                         for q in s["questions"] if q.get("skill"))
        plan = iq.plan_session(profile, role, coverage, answers, count, recent)
        avoid = [q["question"] for s in state["sessions"][-3:] for q in s["questions"]]
        session = iq.write_questions(plan, profile, avoid, set(state.get("asked", [])))
        state["sessions"] = (state["sessions"] + [session])[-KEEP_SESSIONS:]
        state["asked"] = (state.get("asked", []) + [iq.qhash(q["question"]) for q in session["questions"]])[-KEEP_ASKED:]
        state["updated_at"] = time.time()
        self.bb.write(uid, "interviews", state, agent=AGENT_NAME)
        return session

    def sessions(self, uid: str) -> list[dict]:
        """Newest first, short form."""
        return [{"id": s["id"], "created_at": s["created_at"], "role": s["role"], "level": s["level"],
                 "questions": len(s["questions"]), "status": s["status"], "source": s["source"],
                 "mode": s.get("mode", "practice"), "minutes": s.get("minutes"),
                 "score": (s.get("report") or {}).get("overall"),
                 "answered": sum(1 for t in s.get("turns", []) if t.get("answer"))}
                for s in reversed(self._state(uid)["sessions"])]

    def session(self, uid: str, session_id: str) -> dict | None:
        return next((s for s in self._state(uid)["sessions"] if s["id"] == session_id), None)

    def save_answer(self, uid: str, session_id: str, question_id: str, info: dict) -> dict | None:
        """Note on the Blackboard that a question was answered (the audio itself is on disk).
        Day 17 adds the transcript and speaking metrics to the same entry."""
        state = self._state(uid)
        s = next((x for x in state["sessions"] if x["id"] == session_id), None)
        if s is None or not any(q["id"] == question_id for q in s["questions"]):
            return None
        take = time.time()                      # identifies this recording (a new take replaces it)
        s.setdefault("answers", {})[question_id] = info | {"status": "recorded", "recorded_at": take}
        done = all(q["id"] in s["answers"] for q in s["questions"])
        s["status"] = "recorded" if done else "in_progress"
        state["updated_at"] = time.time()
        self.bb.write(uid, "interviews", state, agent=AGENT_NAME)
        return {"status": s["status"], "answered": len(s["answers"]), "total": len(s["questions"]), "take": take}

    def save_transcript(self, uid: str, session_id: str, question_id: str, take: float,
                        result: dict | None, error: str | None = None) -> bool:
        """Day 17: transcript + speaking metrics for one answer. Ignored if the user has
        recorded the question again since (a newer take is waiting for its own transcript)."""
        state = self._state(uid)
        s = next((x for x in state["sessions"] if x["id"] == session_id), None)
        ans = ((s or {}).get("answers") or {}).get(question_id)
        if ans is None or ans.get("recorded_at") != take:
            return False
        if result is None:
            ans.update(status="failed", error=(error or "transcription failed")[:200])
        else:
            m = dict(result["metrics"])
            m["pauses"] = m.get("pauses", [])[:10]
            ans.update(status="transcribed", transcript=result["transcript"][:3000], metrics=m,
                       stt_model=result["model"], transcribed_at=time.time())
        if all((s["answers"].get(q["id"]) or {}).get("status") == "transcribed" for q in s["questions"]):
            s["status"] = "transcribed"
        state["updated_at"] = time.time()
        self.bb.write(uid, "interviews", state, agent=AGENT_NAME)
        return True

    # ------------------------------------------------------- live interview (Day 20) --
    def new_live(self, uid: str, minutes: int, role: str | None = None) -> dict:
        """A live interview: the planned questions become the agenda the interviewer follows."""
        from app.services import interviewer, privacy
        count = interviewer.TOPICS_FOR[minutes] + 1           # + the intro the agenda replaces
        session = self.new_session(uid, count, role)
        entities = (self.bb.read_section(uid, "resume") or {}).get("entities")
        account = self.bb.read_section(uid, "profile")
        answers = merged_answers(self.bb.read_section(uid, "questionnaire"), account)
        session.update(mode="live", minutes=minutes, agenda=interviewer.build_agenda(session["questions"], minutes),
                       turns=[], started_at=None, ended_at=None, status="ready",
                       private=privacy.terms(entities, account),  # hidden from Gemini (privacy.scrub)
                       candidate=interviewer.candidate_info(entities, answers=answers, account=account))
        self.save_live(uid, session)
        return session

    def save_live(self, uid: str, live: dict):
        """Store the whole live session (replaces the stored copy, but never drops its report)."""
        state = self._state(uid)
        old = next((s for s in state["sessions"] if s["id"] == live["id"]), {})
        if old.get("report") and not live.get("report"):
            live["report"] = old["report"]
        state["sessions"] = [live if s["id"] == live["id"] else s for s in state["sessions"]]
        state["updated_at"] = time.time()
        self.bb.write(uid, "interviews", state, agent=AGENT_NAME)

    # ------------------------------------------------------------ report (Day 21) --
    GRADING_STALE = 600            # s: a "grading" report older than this was interrupted (restart)
    _grading: set = set()          # session ids being graded in this process

    def needs_report(self, live: dict | None) -> bool:
        if not live or live.get("mode") != "live" or live.get("status") != "completed":
            return False
        rep = live.get("report") or {}
        if rep.get("status") == "ready":
            return False
        if rep.get("status") == "grading" and time.time() - rep.get("started_at", 0) < self.GRADING_STALE:
            return live["id"] not in self._grading and time.time() - rep.get("started_at", 0) > 30
        return True

    def _save_report(self, uid: str, session_id: str, report: dict):
        state = self._state(uid)
        s = next((x for x in state["sessions"] if x["id"] == session_id), None)
        if s is None:
            return
        s["report"] = report
        state["updated_at"] = time.time()
        self.bb.write(uid, "interviews", state, agent=AGENT_NAME)

    def grade_live(self, uid: str, session_id: str) -> dict | None:
        """Grade a finished live interview and store the report (slow: Gemini; run in a thread)."""
        from app.services import interview_grader
        if session_id in self._grading:
            return None
        self._grading.add(session_id)
        try:
            live = self.session(uid, session_id)
            if not live or live.get("mode") != "live":
                return None
            if "private" not in live:              # interviews from before Day 21: same privacy filter
                from app.services import privacy
                live["private"] = privacy.terms((self.bb.read_section(uid, "resume") or {}).get("entities"),
                                                self.bb.read_section(uid, "profile"))
            self._save_report(uid, session_id, {"status": "grading", "started_at": time.time()})
            try:
                report = interview_grader.grade(live) | {"graded_at": time.time()}
            except Exception:
                logging.getLogger(__name__).exception("Grading failed; using the rule-based report")
                report = interview_grader.grade(live, use_gemini=False) | {"graded_at": time.time()}
            self._save_report(uid, session_id, report)
            return report
        finally:
            self._grading.discard(session_id)
