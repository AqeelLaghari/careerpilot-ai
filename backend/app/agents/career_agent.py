"""Career Guide Agent (CGA).

Reads:  the "resume" section of the Blackboard (written by the Resume Agent)
Writes: the "career" section of the Blackboard

It never calls the Resume Agent directly; it only reads what that agent
left on the Blackboard (Blackboard pattern).

Grows over Days 9-11:
    Day 9:  best-fit careers (SBERT + FAISS + learned keywords)
    Day 10: adaptive questionnaire
    Day 11: skill gap + learning roadmap
"""
import time

from app.orchestrator.blackboard import Blackboard
from app.services import career_matcher

AGENT_NAME = "career_agent"


class NoResumeError(LookupError):
    pass


class CareerAgent:
    def __init__(self, blackboard: Blackboard):
        self.bb = blackboard

    def _entities(self, uid: str) -> dict:
        resume = self.bb.read_section(uid, "resume")
        if not resume:
            raise NoResumeError("Upload a resume first")
        return resume["entities"]

    def match(self, uid: str) -> dict | None:
        """Find best-fit careers and store them on the Blackboard."""
        matches = career_matcher.match_careers(self._entities(uid))
        if matches is None:
            return None
        career = self.bb.read_section(uid, "career") or {}
        career.update({"matches": matches, "matched_at": time.time()})
        self.bb.write(uid, "career", career, agent=AGENT_NAME)
        return career

    def set_target(self, uid: str, role: str) -> dict | None:
        """User picks a target role; store it with its Layer 2 + 3 match."""
        rm = career_matcher.role_match(self._entities(uid), role)
        if rm is None:
            return None
        career = self.bb.read_section(uid, "career") or {}
        career.update({"target_role": rm["role"], "target_match": rm, "target_set_at": time.time()})
        self.bb.write(uid, "career", career, agent=AGENT_NAME)
        return career

    def jd_match(self, uid: str, job_description: str) -> dict:
        return career_matcher.jd_match(self._entities(uid), job_description)
