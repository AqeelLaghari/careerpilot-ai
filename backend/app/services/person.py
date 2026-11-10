"""Who a CV belongs to, without storing who it is.

A short SHA-256 hash of the email (else the name) lets the agents tell a new version of
the same person's CV from a different person's CV. The raw email/name is never stored here.
"""
import hashlib


def person_key(contact: dict, entities: dict) -> str | None:
    """Who the CV belongs to, as a hash (email first, else name). None if neither is found."""
    who = (contact or {}).get("email") or (entities or {}).get("name")
    who = " ".join(str(who).lower().split()) if who else ""
    return hashlib.sha256(who.encode()).hexdigest()[:16] if who else None


def resume_person_key(resume: dict | None) -> str | None:
    """The stored key, or (for resumes saved before keys existed) one made from their contact."""
    if not resume:
        return None
    return resume.get("person_key") or person_key(resume.get("contact"), resume.get("entities"))
