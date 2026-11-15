"""The user's account profile (Day 23): who they are, filled in at sign-up and editable later.

Stored in the Blackboard "profile" section. Other parts read it from there:
  - the questionnaire doesn't ask again what the profile already says (career stage,
    graduation year)          -> profile_answers()
  - the interviewer greets the user by name and mentions their university -> interviewer.candidate_info
  - the privacy filter hides these details from Gemini                      -> privacy.terms
The photo is stored separately (Blackboard.write_file), not in this section.
"""
import re
import time

STATUSES = {"student": "Student", "graduate": "Fresh graduate", "professional": "Working professional"}
# account status -> the questionnaire's "career_stage" answer
STAGE_FOR = {"student": "student", "graduate": "fresh_graduate", "professional": "working"}

LIMITS = {"full_name": 80, "university": 120, "degree": 120, "city": 60, "target_role": 80}
NAME_RE = re.compile(r"^[^\W\d_]+(?:[ .'\-]+[^\W\d_]+)*\.?$")    # letters, spaces, . ' - (any alphabet)
PHONE_RE = re.compile(r"^\+?[\d\s\-()]{7,20}$")
LINK_RE = {"linkedin": re.compile(r"^(https?://)?([a-z]{2,3}\.)?linkedin\.com/(in|pub)/[\w\-%.]+/?$", re.I),
           "github": re.compile(r"^(https?://)?(www\.)?github\.com/[\w\-]+/?$", re.I)}
MAX_PHOTO_BYTES = 200 * 1024          # the app sends a ~20-40 KB 256x256 JPEG
PHOTO_TYPES = {b"\xff\xd8\xff": "image/jpeg", b"\x89PNG\r\n\x1a\n": "image/png"}


class ProfileError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def _text(v) -> str:
    return " ".join(str(v or "").split())


def clean(update: dict, current: dict | None = None, year: int | None = None) -> dict:
    """Validate a (partial) profile update and return the merged profile. Raises ProfileError
    with a message per bad field, so the app can show it next to that field."""
    year = year or time.localtime().tm_year
    out = dict(current or {})
    errors: dict[str, str] = {}
    for key, value in update.items():
        if key in LIMITS:
            v = _text(value)
            if len(v) > LIMITS[key]:
                errors[key] = f"Keep it under {LIMITS[key]} characters"
            elif key == "full_name" and v and not NAME_RE.match(v):
                errors[key] = "Use letters only (spaces, dots, hyphens and apostrophes are fine)"
            elif key == "full_name" and len(v) < 2:
                errors[key] = "Enter your name"
            else:
                out[key] = v or None
        elif key == "status":
            if value not in STATUSES:
                errors[key] = "Choose student, graduate or professional"
            else:
                out[key] = value
        elif key == "semester":
            if value in (None, ""):
                out[key] = None
            elif not isinstance(value, int) or not 1 <= value <= 12:
                errors[key] = "Semester must be between 1 and 12"
            else:
                out[key] = value
        elif key == "graduation_year":
            if value in (None, ""):
                out[key] = None
            elif not isinstance(value, int) or not 1970 <= value <= year + 8:
                errors[key] = f"Enter a year between 1970 and {year + 8}"
            else:
                out[key] = value
        elif key == "phone":
            v = _text(value)
            if v and not PHONE_RE.match(v):
                errors[key] = "Enter a valid phone number"
            else:
                out[key] = v or None
        elif key in LINK_RE:
            v = _text(value).rstrip("/")
            if v and not LINK_RE[key].match(v):
                errors[key] = f"Paste your full {key.capitalize()} profile link"
            else:
                out[key] = (v if not v or v.startswith("http") else "https://" + v) or None
        elif key == "completed":
            out[key] = bool(value)
        else:
            errors[key] = "Unknown field"
    if errors:
        raise ProfileError(errors)
    if out.get("status") != "student":
        out.pop("semester", None)
    if out.get("completed") and not out.get("full_name"):
        raise ProfileError({"full_name": "Enter your name"})
    out["updated_at"] = time.time()
    out.setdefault("created_at", out["updated_at"])
    return out


def check_photo(data: bytes) -> str:
    """The image type of an uploaded photo; raises ProfileError if it isn't a small JPEG/PNG."""
    if not data:
        raise ProfileError({"photo": "No image received"})
    if len(data) > MAX_PHOTO_BYTES:
        raise ProfileError({"photo": "The photo is too large (the app should shrink it first)"})
    for magic, kind in PHOTO_TYPES.items():
        if data.startswith(magic):
            return kind
    raise ProfileError({"photo": "Use a JPEG or PNG image"})


def profile_answers(profile: dict | None) -> dict:
    """Questionnaire answers the profile already gives, so those questions aren't asked again."""
    p = profile or {}
    out = {}
    if p.get("status") in STAGE_FOR:
        out["career_stage"] = {"value": STAGE_FOR[p["status"]], "answered_at": p.get("updated_at"),
                               "context": None, "source": "profile"}
    if p.get("status") == "student" and p.get("graduation_year"):
        out["graduation_year"] = {"value": p["graduation_year"], "answered_at": p.get("updated_at"),
                                  "context": None, "source": "profile"}
    return out


def suggestions(entities: dict | None) -> dict:
    """Pre-fill for the sign-up form from the CV, if one was uploaded already."""
    e = entities or {}
    out = {}
    if e.get("name"):
        out["full_name"] = _text(e["name"]).title() if str(e["name"]).isupper() else _text(e["name"])
    order = {"PhD": 3, "Masters": 2, "Bachelors": 1}
    edu = [x for x in e.get("education") or [] if x.get("institution")]
    if edu:
        best = max(edu, key=lambda x: (order.get(x.get("degree_level"), 0), x.get("end_year") or 0))
        out["university"] = _text(best["institution"])
        if best.get("degree"):
            out["degree"] = _text(best["degree"])[:120]
        if best.get("end_year"):
            out["graduation_year"] = best["end_year"]
    if e.get("location"):
        out["city"] = _text(str(e["location"]).split(",")[0])
    return out
