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
KEEP_SESSIONS = 20          # older sessions are dropped from the Blackboard
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
                 "questions": len(s["questions"]), "status": s["status"], "source": s["source"]}
                for s in reversed(self._state(uid)["sessions"])]

    def session(self, uid: str, session_id: str) -> dict | None:
        return next((s for s in self._state(uid)["sessions"] if s["id"] == session_id), None)
