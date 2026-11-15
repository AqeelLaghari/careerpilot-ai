"""HTTP endpoints for the learning roadmap (built by the Career Guide Agent)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.career_agent import NoResumeError
from app.auth import current_uid
from app.routers.career import agent

router = APIRouter(prefix="/roadmap", tags=["Career Guide Agent"])


class RoadmapIn(BaseModel):
    role: str | None = Field(default=None, min_length=2, max_length=100)


@router.post("")
def build(body: RoadmapIn | None = None, uid: str = Depends(current_uid)):
    """Build the weekly roadmap (for the given role, else the target / best-fit role)."""
    try:
        plan = agent.build_roadmap(uid, body.role if body else None)
    except NoResumeError as e:
        raise HTTPException(404, str(e)) from e
    if plan is None:
        raise HTTPException(503, "Market model not built yet, or role not found")
    return plan


class TaskIn(BaseModel):
    done: bool


@router.get("")
def get(uid: str = Depends(current_uid)):
    """The roadmap with live progress (on track / behind)."""
    plan = agent.get_roadmap(uid)
    if plan is None:
        raise HTTPException(404, "No roadmap yet")
    return plan


@router.post("/tasks/{task_id}")
def tick(task_id: str, body: TaskIn, uid: str = Depends(current_uid)):
    """Tick or untick a task. Finishing a skill's last task marks the skill as learned."""
    try:
        plan = agent.update_task(uid, task_id, body.done)
    except KeyError:
        raise HTTPException(404, f"No task '{task_id}' in your roadmap") from None
    except NoResumeError as e:
        raise HTTPException(404, str(e)) from e
    if plan is None:
        raise HTTPException(404, "No roadmap yet")
    return plan
