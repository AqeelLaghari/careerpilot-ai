"""HTTP endpoints for the Resume Intelligence Agent."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.agents.resume_agent import ResumeAgent
from app.auth import current_uid
from app.deps import blackboard
from app.services.pdf_parser import MAX_PDF_BYTES, PDFError

router = APIRouter(prefix="/resume", tags=["Resume Intelligence Agent"])
agent = ResumeAgent(blackboard)


@router.post("/upload")
def upload_resume(file: UploadFile = File(...), uid: str = Depends(current_uid)):
    data = file.file.read(MAX_PDF_BYTES + 1)
    try:
        return agent.process(uid, data, file.filename or "resume.pdf")
    except PDFError as e:
        raise HTTPException(400, str(e))


@router.get("")
def get_resume(uid: str = Depends(current_uid)):
    resume = blackboard.read_section(uid, "resume")
    if resume is None:
        raise HTTPException(404, "No resume uploaded yet")
    return resume
