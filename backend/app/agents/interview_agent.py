"""Interview Coach Agent (Week 3).

Reads from the Blackboard: "resume" (skills, projects, experience), "questionnaire"
(career stage, extra skills), "roadmap" (skills learned since), "career" (target role).
Writes: "interviews" (sessions with their questions; answers and scores come later).
It never calls the other agents; everything it needs is on the Blackboard.
"""
import time
from collections import Counter

from app.orchestrator.blackboard import Blackboard
from app.services import career_matcher, market_model
from app.services import interview_questions as iq
from app.services.profile import build_profile

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
                                         self.bb.read_section(uid, "roadmap"))
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
                 "mode": s.get("mode", "practice"), "minutes": s.get("minutes")}
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
        from app.services import interviewer
        count = interviewer.TOPICS_FOR[minutes] + 1           # + the intro the agenda replaces
        session = self.new_session(uid, count, role)
        session.update(mode="live", minutes=minutes, agenda=interviewer.build_agenda(session["questions"], minutes),
                       turns=[], started_at=None, ended_at=None, status="ready")
        self.save_live(uid, session)
        return session

    def save_live(self, uid: str, live: dict):
        """Store the whole live session (replaces the stored copy)."""
        state = self._state(uid)
        state["sessions"] = [live if s["id"] == live["id"] else s for s in state["sessions"]]
        state["updated_at"] = time.time()
        self.bb.write(uid, "interviews", state, agent=AGENT_NAME)
