"""Account profile (Day 23).

GET    /profile           the profile + suggestions from the CV (to pre-fill the sign-up form)
PUT    /profile           save some or all fields (each bad field gets its own message)
GET    /profile/photo     the photo (JPEG/PNG bytes)
PUT    /profile/photo     {"image": "<base64>"}  a small square photo (the app shrinks it first)
DELETE /profile/photo
"""
import base64
import binascii
import time

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.agents.career_agent import NoResumeError
from app.auth import current_uid
from app.deps import blackboard
from app.routers.career import agent as career_agent
from app.services import account_profile as ap

router = APIRouter(prefix="/profile", tags=["Account profile"])
AGENT = "profile"


def _view(uid: str, profile: dict | None) -> dict:
    p = dict(profile or {})
    p["settings"] = ap.DEFAULT_SETTINGS | (p.get("settings") or {})
    resume = blackboard.read_section(uid, "resume") or {}
    return {"profile": p, "completed": bool(p.get("completed")), "has_photo": bool(p.get("photo_version")),
            "suggested": ap.suggestions(resume.get("entities")), "statuses": ap.STATUSES}


@router.get("")
def get_profile(uid: str = Depends(current_uid)):
    return _view(uid, blackboard.read_section(uid, "profile"))


@router.put("")
def save_profile(update: dict, uid: str = Depends(current_uid)):
    old = blackboard.read_section(uid, "profile") or {}
    try:
        new = ap.clean(update, old)
    except ap.ProfileError as e:
        raise HTTPException(422, {"message": "Please check the highlighted fields", "errors": e.errors}) from e
    blackboard.write(uid, "profile", new, agent=AGENT)
    # a new target role: store it with its match score (if a CV is uploaded already)
    if new.get("target_role") and new.get("target_role") != old.get("target_role"):
        try:
            career_agent.set_target(uid, new["target_role"])
        except NoResumeError:
            pass                       # used when the CV is uploaded (career_agent.match)
    return _view(uid, new)


class PhotoIn(BaseModel):
    image: str                         # base64, optionally a data: URL


@router.put("/photo")
def save_photo(body: PhotoIn, uid: str = Depends(current_uid)):
    raw = body.image.split(",", 1)[-1] if body.image.startswith("data:") else body.image
    try:
        data = base64.b64decode(raw, validate=True)
        kind = ap.check_photo(data)
    except (binascii.Error, ValueError) as e:
        errors = e.errors if isinstance(e, ap.ProfileError) else {"photo": "Not a valid image"}
        raise HTTPException(422, {"message": errors["photo"], "errors": errors}) from e
    blackboard.write_file(uid, "photo", data, kind)
    profile = blackboard.read_section(uid, "profile") or {}
    profile["photo_version"] = int(time.time())          # the app reloads the picture when this changes
    blackboard.write(uid, "profile", profile, agent=AGENT)
    return {"has_photo": True, "photo_version": profile["photo_version"]}


@router.get("/photo")
def get_photo(uid: str = Depends(current_uid)):
    f = blackboard.read_file(uid, "photo")
    if not f:
        raise HTTPException(404, "No photo")
    return Response(content=bytes(f["data"]), media_type=f.get("type") or "image/jpeg",
                    headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/photo")
def delete_photo(uid: str = Depends(current_uid)):
    blackboard.write_file(uid, "photo", None)
    profile = blackboard.read_section(uid, "profile") or {}
    profile.pop("photo_version", None)
    blackboard.write(uid, "profile", profile, agent=AGENT)
    return {"has_photo": False}
