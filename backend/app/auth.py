"""Checks the Firebase login token that the Flutter app sends.

Any endpoint that has `uid: str = Depends(current_uid)` only works for
logged-in users, and receives their Firebase user ID.
"""
from fastapi import Header, HTTPException
from firebase_admin import auth as fb_auth


def current_uid(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not logged in")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        return fb_auth.verify_id_token(token)["uid"]
    except Exception:
        raise HTTPException(401, "Invalid or expired login token")
