"""Market model endpoints: roles and the skills they need, learned from job postings."""
from fastapi import APIRouter, Depends, HTTPException

from app.auth import current_uid
from app.deps import blackboard
from app.services import market_model

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
