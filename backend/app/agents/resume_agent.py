"""Resume Intelligence Agent (RIA).

Reads: nothing (it is the first agent in the pipeline)
Writes: the "resume" section of the Blackboard

Pipeline (grows over Days 4-6):
    Day 4: PDF → text, sections, contact, layout   (pdf_parser)
    Day 5: entities: skills, education, experience  (spaCy NER)
    Day 6: ATS scorecard                            (ats_scorer)
"""
import time

from app.orchestrator.blackboard import Blackboard
from app.services.entity_extractor import extract_entities
from app.services.pdf_parser import extract_pdf

AGENT_NAME = "resume_agent"


class ResumeAgent:
    def __init__(self, blackboard: Blackboard):
        self.bb = blackboard

    def process(self, uid: str, pdf_bytes: bytes, filename: str) -> dict:
        parsed = extract_pdf(pdf_bytes)  # raises PDFError on bad files
        entities = extract_entities(parsed["sections"], parsed["text"])

        result = {
            "entities": entities,
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
