"""Checks the Firebase login token that the Flutter app sends.

Any endpoint that has `uid: str = Depends(current_uid)` only works for logged-in users, and
receives their Firebase user ID.

Email verification (Day 23): an email/password account created on or after VERIFY_EMAIL_FROM
must click the link Firebase emailed before it can use the API, so made-up emails can't be used.
This is checked HERE on the server; the app's "check your inbox" screen alone could be skipped.
Google sign-ins are verified by Google. Accounts made before that date (test accounts) still work.
"""
import logging
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import Header, HTTPException
from firebase_admin import auth as fb_auth

from app.config import VERIFY_EMAIL_FROM

log = logging.getLogger(__name__)
NOT_VERIFIED = "Please verify your email address first (check your inbox for the link)."


class EmailNotVerified(Exception):
    pass


def current_uid(authorization: str = Header(default="")) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Not logged in")
    try:
        uid = check_token(authorization.removeprefix("Bearer ").strip())
    except EmailNotVerified:
        raise HTTPException(403, NOT_VERIFIED) from None
    if uid is None:
        raise HTTPException(401, "Invalid or expired login token")
    return uid


def uid_from_token(token: str) -> str | None:
    """Firebase user ID for a login token, or None (also when the email isn't verified yet).
    Used by the WebSockets, which receive the token in their first message (browsers can't
    set WebSocket headers)."""
    try:
        return check_token(token)
    except EmailNotVerified:
        return None


def check_token(token: str) -> str | None:
    """The user ID, None for a bad token; raises EmailNotVerified when verification is needed."""
    try:
        claims = fb_auth.verify_id_token(token)
    except Exception:
        return None
    if needs_verification(claims):
        raise EmailNotVerified()
    return claims["uid"]


def needs_verification(claims: dict) -> bool:
    provider = (claims.get("firebase") or {}).get("sign_in_provider")
    if provider != "password" or claims.get("email_verified"):
        return False
    return _created_after_cutoff(claims["uid"])


_created: dict[str, float] = {}       # uid -> account creation time (s); it never changes


def _created_after_cutoff(uid: str) -> bool:
    """True for accounts made on/after VERIFY_EMAIL_FROM."""
    if uid not in _created:
        try:
            _created[uid] = (fb_auth.get_user(uid).user_metadata.creation_timestamp or 0) / 1000
        except Exception:                 # not cached: tried again on the next request
            log.warning("Could not read the account creation time; not blocking the user", exc_info=True)
            return False
    return _created[uid] >= _cutoff()


@lru_cache(maxsize=1)
def _cutoff() -> float:
    return datetime.fromisoformat(VERIFY_EMAIL_FROM).replace(tzinfo=timezone.utc).timestamp()
