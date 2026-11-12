"""HTTP endpoints for the Interview Coach Agent."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.interview_agent import InterviewAgent, NoResumeError
from app.auth import current_uid
from app.deps import blackboard
from app.services import interview_questions as iq

router = APIRouter(prefix="/interview", tags=["Interview Coach Agent"])
agent = InterviewAgent(blackboard)


class NewSessionIn(BaseModel):
    count: int = Field(default=iq.DEFAULT_COUNT, ge=iq.MIN_COUNT, le=iq.MAX_COUNT)
    role: str | None = Field(default=None, max_length=100)   # default: the user's target role


@router.post("/sessions")
def new_session(body: NewSessionIn, uid: str = Depends(current_uid)):
    """A fresh set of interview questions made for this user (about 3-8 s with Gemini)."""
    try:
        return agent.new_session(uid, body.count, body.role)
    except NoResumeError as e:
        raise HTTPException(404, str(e))


@router.get("/sessions")
def list_sessions(uid: str = Depends(current_uid)):
    return agent.sessions(uid)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, uid: str = Depends(current_uid)):
    s = agent.session(uid, session_id)
    if s is None:
        raise HTTPException(404, "No such interview session")
    return s
