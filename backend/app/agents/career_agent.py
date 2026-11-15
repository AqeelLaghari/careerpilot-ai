"""Career Guide Agent (CGA).

Reads:  the "resume" section of the Blackboard (written by the Resume Agent)
Writes: the "questionnaire", "career", "roadmap" and "jobs" sections of the Blackboard

It never calls the Resume Agent directly; it only reads what that agent
left on the Blackboard (Blackboard pattern).

Grows over Days 9-11:
    Day 9:  best-fit careers (SBERT + FAISS + learned keywords)
    Day 10: adaptive questionnaire (asks only what the resume is missing);
            its answers enrich the profile used for career matching
    Day 11: skill gap (set difference) + prerequisite DAG (networkx topological
            sort) -> weekly learning roadmap
    Day 14: live remote jobs open to Pakistan, ranked by match with the profile
"""
import time

from app.orchestrator.blackboard import Blackboard
from app.services import career_matcher, live_jobs
from app.services import questionnaire as qn
from app.services import roadmap as rm
from app.services.person import resume_person_key
from app.services.profile import build_profile, merged_answers

AGENT_NAME = "career_agent"
RESET_GAP = 40      # old data without a person key: reset if the target is this far behind the best fit


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
        self._sync_person(uid, resume)
        return resume["entities"]

    def _sync_person(self, uid: str, resume: dict):
        """If the uploaded CV belongs to a different person than the one the career data was
        built for, start fresh: the old target role, answers and roadmap belong to someone else.
        A new version of the same person's CV keeps everything."""
        key = resume_person_key(resume)
        if not key:
            return
        career = self.bb.read_section(uid, "career") or {}
        old = career.get("person_key")
        if old == key:
            return
        if old is None and not career.get("target_role"):
            career["person_key"] = key                 # first time: just remember who this is
            self.bb.write(uid, "career", career, agent=AGENT_NAME)
            return
        if old is None:                                # data saved before keys existed: check the target fit
            target = career.get("target_role")
            best = career_matcher.match_careers(resume["entities"], top_k=1) or []
            tm = career_matcher.role_match(resume["entities"], target)
            if not (best and tm and best[0]["score"] - tm["score"] >= RESET_GAP):
                career["person_key"] = key
                self.bb.write(uid, "career", career, agent=AGENT_NAME)
                return
        self.bb.write(uid, "career", {"person_key": key, "reset_at": time.time()}, agent=AGENT_NAME)
        self.bb.write(uid, "questionnaire", {"answers": {}, "completed": False, "updated_at": time.time()},
                      agent=AGENT_NAME)
        self.bb.write(uid, "roadmap", None, agent=AGENT_NAME)

    def _answers(self, uid: str) -> dict:
        """Questionnaire answers + what the account profile already tells us (Day 23)."""
        return merged_answers(self.bb.read_section(uid, "questionnaire"), self.bb.read_section(uid, "profile"))

    def _profile(self, uid: str) -> tuple[dict, dict]:
        """Resume entities enriched with questionnaire answers, skills completed on the
        roadmap (Day 13) and the account profile (Day 23), plus the answers."""
        entities = self._entities(uid)
        return build_profile(entities, self.bb.read_section(uid, "questionnaire"),
                             self.bb.read_section(uid, "roadmap"), self.bb.read_section(uid, "profile"))

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
        # the target role given at sign-up (Day 23), if none was chosen here yet
        wanted = (self.bb.read_section(uid, "profile") or {}).get("target_role")
        if wanted and not career.get("target_role"):
            career = self.set_target(uid, wanted) or career
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

    # ------------------------------------------------------------- roadmap --
    def build_roadmap(self, uid: str, role: str | None = None) -> dict | None:
        """Roadmap for `role`, else the target role, else the best-fit role."""
        profile, answers = self._profile(uid)
        if not role:
            career = self.bb.read_section(uid, "career") or {}
            role = career.get("target_role")
            if not role:
                matches = career.get("matches") or (self.match(uid) or {}).get("matches")
                role = matches[0]["role"] if matches else None
        if not role:
            return None
        plan = rm.build_roadmap(profile, role, answers)
        if plan is None:
            return None
        plan["generated_at"] = plan["started_at"] = time.time()
        plan = rm.carry_over(self.bb.read_section(uid, "roadmap"), plan)
        self.bb.write(uid, "roadmap", plan, agent=AGENT_NAME)
        return plan | {"progress": rm.progress(plan)}

    def get_roadmap(self, uid: str) -> dict | None:
        resume = self.bb.read_section(uid, "resume")
        if resume:
            self._sync_person(uid, resume)
        plan = self.bb.read_section(uid, "roadmap")
        return plan | {"progress": rm.progress(plan)} if plan else None

    def update_task(self, uid: str, task_id: str, done: bool) -> dict | None:
        """Tick/untick a task. When a skill's last task is ticked, the skill counts as
        learned: it joins the career profile and the target-role match is refreshed."""
        plan = self.bb.read_section(uid, "roadmap")
        if not plan:
            return None
        before = {c["name"] for c in plan.get("completed_skills", [])}
        completed = rm.set_task(plan, task_id, done)          # KeyError if unknown task
        self.bb.write(uid, "roadmap", plan, agent=AGENT_NAME)
        after = {c["name"] for c in plan.get("completed_skills", [])}
        match_change = None
        if before != after:                                    # a skill was completed or reopened
            career = self.bb.read_section(uid, "career") or {}
            target = career.get("target_role")
            if target:                                         # refresh the stored target match
                old = (career.get("target_match") or {}).get("score")
                new = (((self.set_target(uid, target) or {}).get("target_match")) or {}).get("score")
                if old is not None and new is not None:
                    match_change = {"role": target, "before": old, "after": new}
        return plan | {"progress": rm.progress(plan), "skill_completed": completed, "match_change": match_change}

    # ---------------------------------------------------------------- jobs --
    def jobs(self, uid: str, query: str | None = None, limit: int = 30) -> dict:
        """Remote jobs a Pakistani can apply to, best match with this user first.
        The top matches are kept on the Blackboard (for the dashboard)."""
        profile, _ = self._profile(uid)
        live_jobs.ensure_fresh()                                # background, never waits
        career = self.bb.read_section(uid, "career") or {}
        role = career.get("target_role") or ((career.get("matches") or [{}])[0]).get("role")
        if query:
            live_jobs.search_jobs(query)                        # ask Himalayas too (cached per query)
        else:
            live_jobs.add_role_jobs(role)                       # Himalayas search for the role (cached)
        results = live_jobs.match_jobs(profile, query=query, limit=limit)
        status = live_jobs.status()
        if not query and results:
            top = [{"id": j["id"], "title": j["title"], "company": j["company"], "match": j["match"]}
                   for j in results[:10]]
            old = self.bb.read_section(uid, "jobs") or {}
            if [t["id"] for t in old.get("top", [])] != [t["id"] for t in top]:   # write only on change
                self.bb.write(uid, "jobs", {"top": top, "role": role, "matched_at": time.time()},
                              agent=AGENT_NAME)
        return {"jobs": results, "role": role, "query": query, **status,
                "user_skills": [s["name"] for s in profile.get("skills", [])],
                "sources": [{"name": v["name"], "url": v["site"]} for v in live_jobs.job_sources.SOURCES.values()]}

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
