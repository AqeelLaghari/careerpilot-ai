"""Resume Intelligence Agent (RIA).

Reads: nothing (it is the first agent in the pipeline)
Writes: the "resume" section of the Blackboard

Pipeline (grows over Days 4-6):
    Day 4: PDF → text, sections, contact, layout   (pdf_parser)
    Day 5: entities: skills, education, experience  (spaCy NER)
    Day 6: ATS scorecard                            (ats_scorer)
    Day 9: role match in the ATS report             (Layer 2 keywords + Layer 3 SBERT)
"""
import logging
import time

from app.orchestrator.blackboard import Blackboard
from app.services import career_matcher
from app.services.ats_scorer import score_resume
from app.services.entity_extractor import extract_entities
from app.services.pdf_parser import extract_pdf

AGENT_NAME = "resume_agent"
log = logging.getLogger(__name__)


class ResumeAgent:
    def __init__(self, blackboard: Blackboard):
        self.bb = blackboard

    def process(self, uid: str, pdf_bytes: bytes, filename: str) -> dict:
        parsed = extract_pdf(pdf_bytes)  # raises PDFError on bad files
        entities = extract_entities(parsed["sections"], parsed["text"])
        ats = score_resume(parsed, entities)
        ats["role_match"] = self._role_match(uid, entities)

        result = {
            "entities": entities,
            "ats": ats,
            "filename": filename,
            "uploaded_at": time.time(),
            "text": parsed["text"],
            "sections": parsed["sections"],
            "headings_found": parsed["headings_found"],
            "contact": parsed["contact"],
            "layout": parsed["layout"],
        }
        self.bb.write(uid, "resume", result, agent=AGENT_NAME)
        return result

    def _role_match(self, uid: str, entities: dict) -> dict | None:
        """Against the user's target role if they chose one (read from the Blackboard,
        written by the Career Agent), otherwise against their best-fit role.
        Never breaks the upload: returns None if matching is unavailable."""
        try:
            target = (self.bb.read_section(uid, "career") or {}).get("target_role")
            if target:
                rm = career_matcher.role_match(entities, target)
                if rm:
                    return rm | {"basis": "target role"}
            best = career_matcher.match_careers(entities, top_k=1)
            return best[0] | {"basis": "best-fit role"} if best else None
        except Exception:
            log.exception("Role match failed; ATS report continues without it")
            return None
