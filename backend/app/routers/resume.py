"""HTTP endpoints for the Resume Intelligence Agent."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.agents.resume_agent import ResumeAgent
from app.auth import current_uid
from app.deps import blackboard
from app.services import bullet_rewriter, privacy
from app.services.pdf_parser import MAX_PDF_BYTES, PDFError

router = APIRouter(prefix="/resume", tags=["Resume Intelligence Agent"])
agent = ResumeAgent(blackboard)


@router.post("/upload")
def upload_resume(file: UploadFile = File(...), uid: str = Depends(current_uid)):
    data = file.file.read(MAX_PDF_BYTES + 1)
    try:
        return agent.process(uid, data, file.filename or "resume.pdf")
    except PDFError as e:
        raise HTTPException(400, str(e)) from e


@router.get("")
def get_resume(uid: str = Depends(current_uid)):
    resume = blackboard.read_section(uid, "resume")
    if resume is None:
        raise HTTPException(404, "No resume uploaded yet")
    return resume


# ---- AI bullet rewriter (Day 24) ----
@router.get("/bullets")
def list_bullets(uid: str = Depends(current_uid)):
    """The CV's bullet points, weak ones marked, for the "Improve" buttons."""
    resume = blackboard.read_section(uid, "resume")
    if resume is None:
        raise HTTPException(404, "No resume uploaded yet")
    return {"bullets": bullet_rewriter.review(resume.get("entities"))}


class RewriteIn(BaseModel):
    bullet: str = Field(min_length=5, max_length=bullet_rewriter.MAX_BULLET)


@router.post("/rewrite")
def rewrite_bullet(body: RewriteIn, uid: str = Depends(current_uid)):
    """Stronger versions of one bullet (Gemini fast tier, rules if it's unavailable)."""
    state = blackboard.read(uid)
    entities = (state.get("resume") or {}).get("entities")
    role = (state.get("career") or {}).get("target_role")
    try:
        return bullet_rewriter.rewrite(body.bullet, role, privacy.terms(entities, state.get("profile")))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
