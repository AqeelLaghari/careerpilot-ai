"""HTTP endpoints for the adaptive questionnaire (run by the Career Guide Agent)."""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.career_agent import NoResumeError
from app.auth import current_uid
from app.routers.career import agent

router = APIRouter(prefix="/questionnaire", tags=["Career Guide Agent"])


class AnswersIn(BaseModel):
    # {question_id: value}; value is a string, number, list or {skill: level}
    answers: dict[str, Any] = Field(min_length=1, max_length=20)


def _run(fn, *args):
    try:
        return fn(*args)
    except NoResumeError as e:
        raise HTTPException(404, str(e))


@router.get("")
def get_questions(uid: str = Depends(current_uid)):
    """Questions still worth asking (only what the resume doesn't tell us)."""
    return _run(agent.questionnaire, uid)


@router.post("/answers")
def submit_answers(body: AnswersIn, uid: str = Depends(current_uid)):
    """Save answers; returns the next questions and the refreshed career matches."""
    return _run(agent.answer, uid, body.answers)


@router.delete("")
def reset(uid: str = Depends(current_uid)):
    """Clear all answers and start over."""
    return _run(agent.reset_questionnaire, uid)
