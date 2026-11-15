"""The dashboard: one summary of the user's whole Blackboard state (Day 24)."""
from fastapi import APIRouter, Depends

from app.auth import current_uid
from app.deps import blackboard
from app.orchestrator.dashboard import summary

router = APIRouter(prefix="/dashboard", tags=["Orchestrator"])


@router.get("")
def get_dashboard(uid: str = Depends(current_uid)):
    return summary(blackboard.read(uid))
