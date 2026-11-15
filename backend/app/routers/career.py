"""HTTP endpoints for the Career Guide Agent."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.career_agent import CareerAgent, NoResumeError
from app.auth import current_uid
from app.deps import blackboard

router = APIRouter(prefix="/career", tags=["Career Guide Agent"])
agent = CareerAgent(blackboard)


class TargetIn(BaseModel):
    role: str = Field(min_length=2, max_length=100)


class JobDescriptionIn(BaseModel):
    job_description: str = Field(min_length=50, max_length=20000)


def _run(fn, *args):
    try:
        out = fn(*args)
    except NoResumeError as e:
        raise HTTPException(404, str(e)) from e
    if out is None:
        raise HTTPException(503, "Market model not built yet, or role not found")
    return out


@router.post("/match")
def match(uid: str = Depends(current_uid)):
    """Compute best-fit careers for the uploaded resume (top 5)."""
    return _run(agent.match, uid)


@router.get("")
def get_career(uid: str = Depends(current_uid)):
    career = blackboard.read_section(uid, "career")
    if career is None:
        raise HTTPException(404, "No career data yet")
    return career


@router.post("/target")
def set_target(body: TargetIn, uid: str = Depends(current_uid)):
    return _run(agent.set_target, uid, body.role)


@router.post("/jd-match")
def jd_match(body: JobDescriptionIn, uid: str = Depends(current_uid)):
    """Paste any job description → match score + missing skills."""
    return _run(agent.jd_match, uid, body.job_description)
