"""Resume Intelligence Agent (RIA).

Reads: nothing (it is the first agent in the pipeline)
Writes: the "resume" section of the Blackboard

Pipeline (grows over Days 4-6):
    Day 4: PDF → text, sections, contact, layout   (pdf_parser)
    Day 5: entities: skills, education, experience  (spaCy NER)
    Day 6: ATS scorecard                            (ats_scorer)
    Day 9: role match in the ATS report             (Layer 2 keywords + Layer 3 SBERT)

Each resume carries a `person_key` (a short hash of the email, else the name; never the
raw value) so the Career Agent can tell a new version of the same CV from a different
person's CV and start fresh for the latter.
"""
import logging
import time

from app.orchestrator.blackboard import Blackboard
from app.services import career_matcher
from app.services.ats_scorer import score_resume
from app.services.entity_extractor import extract_entities
from app.services.pdf_parser import extract_pdf
from app.services.person import person_key, resume_person_key

AGENT_NAME = "resume_agent"
BETTER_FIT_GAP = 25          # points: suggest the best-fit role when the target is this far behind
HISTORY_LIMIT = 20           # ATS scores kept for the dashboard chart (Day 24)
log = logging.getLogger(__name__)


class ResumeAgent:
    def __init__(self, blackboard: Blackboard):
        self.bb = blackboard

    def process(self, uid: str, pdf_bytes: bytes, filename: str) -> dict:
        parsed = extract_pdf(pdf_bytes)  # raises PDFError on bad files
        entities = extract_entities(parsed["sections"], parsed["text"])
        ats = score_resume(parsed, entities)
        key = person_key(parsed["contact"], entities)
        old = self.bb.read_section(uid, "resume") or {}
        old_key = resume_person_key(old)
        same_person = not (key and old_key and key != old_key)
        ats["role_match"] = self._role_match(uid, entities, use_target=same_person)
        now = time.time()

        result = {
            "entities": entities,
            "ats": ats,
            "filename": filename,
            "person_key": key,
            "uploaded_at": now,
            "history": score_history(old if same_person else {}, ats, filename, now),
            "text": parsed["text"],
            "sections": parsed["sections"],
            "headings_found": parsed["headings_found"],
            "contact": parsed["contact"],
            "layout": parsed["layout"],
        }
        self.bb.write(uid, "resume", result, agent=AGENT_NAME)
        return result

    def _role_match(self, uid: str, entities: dict, use_target: bool = True) -> dict | None:
        """Against the user's target role if they chose one (read from the Blackboard,
        written by the Career Agent), otherwise against their best-fit role.
        The target is ignored for a different person's CV (it was chosen for the old one).
        If the CV fits another role much better than the target, that role is suggested.
        Never breaks the upload: returns None if matching is unavailable."""
        try:
            best = career_matcher.match_careers(entities, top_k=1)
            best = best[0] if best else None
            target = (self.bb.read_section(uid, "career") or {}).get("target_role") if use_target else None
            if target:
                rm = career_matcher.role_match(entities, target)
                if rm:
                    if best and best["role"] != rm["role"] and best["score"] - rm["score"] >= BETTER_FIT_GAP:
                        rm["better_fit"] = {"role": best["role"], "score": best["score"]}
                    return rm | {"basis": "target role"}
            return best | {"basis": "best-fit role"} if best else None
        except Exception:
            log.exception("Role match failed; ATS report continues without it")
            return None


def score_history(old: dict, ats: dict, filename: str, now: float) -> list[dict]:
    """The ATS score of every upload, oldest first (a different person's CV starts a new list).
    CVs uploaded before Day 24 have no list yet: their last score becomes the first point."""
    history = list(old.get("history") or [])
    if not history and (old.get("ats") or {}).get("readability_score") is not None:
        history = [{"at": old.get("uploaded_at"), "score": old["ats"]["readability_score"],
                    "filename": old.get("filename")}]
    history.append({"at": now, "score": ats["readability_score"], "filename": filename})
    return history[-HISTORY_LIMIT:]
