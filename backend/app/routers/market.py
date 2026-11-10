"""Market model endpoints: roles and the skills they need, learned from job postings."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import config

from app.auth import current_uid
from app.deps import blackboard
from app.services import market_learning, market_model

router = APIRouter(tags=["Market model (ATS Layer 2)"])


def _require_model() -> dict:
    model = market_model.load_model()
    if not model:
        raise HTTPException(503, "Market model not built yet. Run scripts/build_market_model.py")
    return model


@router.get("/market/info")
def market_info():
    """How fresh the market data is (shown to users as 'market data updated ...')."""
    m = _require_model()
    return {k: m[k] for k in ("version", "built_at", "postings_used", "data_from", "data_to", "sources")} | {
        "roles": len(m["roles"])}


@router.get("/market/roles")
def market_roles(q: str = "", limit: int = 50):
    _require_model()
    return market_model.list_roles(q, min(limit, 200))


@router.get("/market/roles/{role}")
def market_role(role: str):
    _require_model()
    prof = market_model.role_profile(role)
    if not prof:
        raise HTTPException(404, f"No learned role matches '{role}'")
    return prof


@router.get("/resume/role-keywords")
def resume_role_keywords(role: str, uid: str = Depends(current_uid)):
    """ATS Layer 2 for the user's uploaded resume against a target role."""
    _require_model()
    resume = blackboard.read_section(uid, "resume")
    if resume is None:
        raise HTTPException(404, "No resume uploaded yet")
    skills = [s["name"] for s in resume["entities"]["skills"]]
    result = market_model.keyword_coverage(skills, role)
    if result is None:
        raise HTTPException(404, f"No learned role matches '{role}'")
    return result


# ----------------------------------------------- self-learning (Day 14, part 3) --
@router.get("/market/trending")
def market_trending(uid: str = Depends(current_uid)):
    """Skills most in demand in recent postings, plus rising / falling ones and the newly learned."""
    return market_learning.trends()


def require_admin(uid: str = Depends(current_uid)) -> str:
    if uid not in config.ADMIN_UIDS:
        raise HTTPException(403, "Admins only. Add your user ID to ADMIN_UIDS in backend/.env")
    return uid


@router.get("/market/admin/me")
def market_admin_me(uid: str = Depends(current_uid)):
    """Is the logged-in user an admin? (Shows the admin screen in the app.)"""
    return {"is_admin": uid in config.ADMIN_UIDS}


@router.get("/market/learned")
def market_learned(_: str = Depends(require_admin)):
    """Every skill the app learned from live postings (approved, pending, removed)."""
    return market_learning.learned_skills()


class _Status(BaseModel):
    status: str                       # "approved" or "removed"
    category: str | None = None       # needed to approve a pending skill


@router.post("/market/learned/{name}")
def market_learned_status(name: str, body: _Status, _: str = Depends(require_admin)):
    """Approve a pending skill or remove a wrong one (a removed skill is never learned again)."""
    if body.status not in {"approved", "removed"}:
        raise HTTPException(400, "status must be 'approved' or 'removed'")
    try:
        s = market_learning.set_status(name, body.status, body.category)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if s is None:
        raise HTTPException(404, f"No learned skill called '{name}'")
    return s


@router.post("/market/learn")
def market_learn_now(_: str = Depends(require_admin)):
    """Run the weekly learning now (in the background)."""
    return {"running": market_learning.maybe_learn(force=True)}
