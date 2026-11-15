"""Live remote jobs open to Pakistan (Career Guide Agent, Day 14)."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.agents.career_agent import NoResumeError
from app.auth import current_uid
from app.routers.career import agent
from app.services import live_jobs

router = APIRouter(prefix="/jobs", tags=["Live jobs"])


@router.get("")
def jobs(q: str | None = Query(default=None, max_length=80), limit: int = Query(default=30, ge=1, le=100),
         uid: str = Depends(current_uid)):
    """Remote jobs a Pakistani can apply to, ranked by match with the user's profile."""
    try:
        return agent.jobs(uid, query=(q or "").strip() or None, limit=limit)
    except NoResumeError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/status")
def jobs_status():
    """How fresh the jobs are and how many each source gave (no login needed)."""
    return live_jobs.status()
