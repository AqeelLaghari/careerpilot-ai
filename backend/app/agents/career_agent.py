"""Career Guide Agent (CGA).

Reads:  the "resume" section of the Blackboard (written by the Resume Agent)
Writes: the "questionnaire" and "career" sections of the Blackboard

It never calls the Resume Agent directly; it only reads what that agent
left on the Blackboard (Blackboard pattern).

Grows over Days 9-11:
    Day 9:  best-fit careers (SBERT + FAISS + learned keywords)
    Day 10: adaptive questionnaire (asks only what the resume is missing);
            its answers enrich the profile used for career matching
    Day 11: skill gap + learning roadmap
"""
import time

from app.orchestrator.blackboard import Blackboard
from app.services import career_matcher
from app.services import questionnaire as qn

AGENT_NAME = "career_agent"


class NoResumeError(LookupError):
    pass


class CareerAgent:
    def __init__(self, blackboard: Blackboard):
        self.bb = blackboard

    # ------------------------------------------------------------ profile --
    def _entities(self, uid: str) -> dict:
        resume = self.bb.read_section(uid, "resume")
        if not resume:
            raise NoResumeError("Upload a resume first")
        return resume["entities"]

    def _answers(self, uid: str) -> dict:
        return (self.bb.read_section(uid, "questionnaire") or {}).get("answers", {})

    def _profile(self, uid: str) -> tuple[dict, dict]:
        """Resume entities enriched with questionnaire answers, plus the raw answers."""
        answers = self._answers(uid)
        return qn.profile_entities(self._entities(uid), answers), answers

    # ------------------------------------------------------------ matching --
    def match(self, uid: str) -> dict | None:
        """Find best-fit careers and store them on the Blackboard."""
        profile, answers = self._profile(uid)
        interests = qn.interest_categories((answers.get("interests") or {}).get("value"))
        matches = career_matcher.match_careers(profile, interests=interests or None)
        if matches is None:
            return None
        career = self.bb.read_section(uid, "career") or {}
        career.update({"matches": matches, "matched_at": time.time()})
        self.bb.write(uid, "career", career, agent=AGENT_NAME)
        return career

    def set_target(self, uid: str, role: str) -> dict | None:
        """User picks a target role; store it with its Layer 2 + 3 match."""
        profile, _ = self._profile(uid)
        rm = career_matcher.role_match(profile, role)
        if rm is None:
            return None
        career = self.bb.read_section(uid, "career") or {}
        career.update({"target_role": rm["role"], "target_match": rm, "target_set_at": time.time()})
        self.bb.write(uid, "career", career, agent=AGENT_NAME)
        return career

    def jd_match(self, uid: str, job_description: str) -> dict:
        profile, _ = self._profile(uid)
        return career_matcher.jd_match(profile, job_description)

    # ------------------------------------------------------- questionnaire --
    def _career_for_questions(self, uid: str) -> dict:
        career = self.bb.read_section(uid, "career") or {}
        if not career.get("matches"):           # role options come from the best-fit roles
            career = self.match(uid) or career
        return career

    def questionnaire(self, uid: str) -> dict:
        """The questions still worth asking, given the resume and answers so far."""
        entities = self._entities(uid)
        answers = self._answers(uid)
        pending = qn.pending_questions(entities, self._career_for_questions(uid), answers)
        return self._state(answers, pending)

    def answer(self, uid: str, submitted: dict) -> dict:
        """Validate and store answers (in order, so follow-up questions work in one
        request), then refresh the career results the answers affect."""
        entities = self._entities(uid)
        career = self._career_for_questions(uid)
        answers = self._answers(uid)
        errors, accepted = {}, []
        for qid, value in submitted.items():
            pending = {q["id"]: q for q in qn.pending_questions(entities, career, answers)}
            q = pending.get(qid)
            if q is None:
                errors[qid] = "This question isn't being asked right now"
                continue
            try:
                clean = qn.validate(q, value)
            except qn.AnswerError as e:
                errors[qid] = str(e)
                continue
            answers[qid] = {"value": clean, "answered_at": time.time(), "context": q.get("context")}
            accepted.append(qid)
            if qid == "target_role":            # later questions depend on the target role
                career = {**career, "target_role": clean}

        if accepted:
            self._save(uid, answers)
            if "target_role" in accepted:
                self.set_target(uid, answers["target_role"]["value"])
            if {"extra_skills", "interests", "experience_years"} & set(accepted):
                self.match(uid)
                target = (self.bb.read_section(uid, "career") or {}).get("target_role")
                if target and "target_role" not in accepted:
                    self.set_target(uid, target)  # refresh its score with the new skills
            career = self.bb.read_section(uid, "career") or career

        pending = qn.pending_questions(entities, career, answers)
        if accepted:
            self._save(uid, answers, completed=not pending)
        return self._state(answers, pending) | {"accepted": accepted, "errors": errors, "career": career}

    def reset_questionnaire(self, uid: str) -> dict:
        self._save(uid, {})
        return self.questionnaire(uid)

    def _save(self, uid: str, answers: dict, completed: bool = False):
        self.bb.write(uid, "questionnaire", {"answers": answers, "completed": completed,
                                             "updated_at": time.time()}, agent=AGENT_NAME)

    @staticmethod
    def _state(answers: dict, pending: list[dict]) -> dict:
        done = len(answers)
        return {"questions": pending, "answered": qn.answer_summary(answers), "completed": not pending,
                "progress": {"answered": done, "remaining": len(pending)}}
