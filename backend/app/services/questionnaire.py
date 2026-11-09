"""Adaptive questionnaire: asks ONLY what the resume doesn't already tell us.

How it adapts
    Every question has a rule ("when is this needed?") that looks at
        - the parsed resume   (Blackboard "resume", written by the Resume Agent)
        - the career results  (Blackboard "career": best-fit roles, target role)
        - the answers so far  (Blackboard "questionnaire")
    A question is asked only while its rule says the information is missing.
    So a 5-year professional with a full CV gets ~4 questions, while a fresh
    student with a thin CV gets ~9, and answering one question can unlock or
    remove others (e.g. "Student" → "When do you graduate?").

    Options are also adaptive: the role choices are the user's own best-fit roles,
    and the skill choices are the skills the market model says the user's
    target role needs but the CV doesn't show (learned from job postings).

Everything here is rule-based (no LLM call), so it is free, instant and
explainable. This module is pure logic; the Career Agent stores the answers.
"""
import re

from app.services import market_model
from app.services.entity_extractor import find_skills

LEVELS = ["beginner", "intermediate", "advanced"]

# Career fields the user can be interested in -> the market model's role categories.
# (Groups of the skill categories in skills.json, not per-role keyword lists.)
FIELDS = {
    "software": ("Software development", {"programming_languages", "web_backend", "web_frontend", "mobile",
                                          "embedded_iot"}),
    "data_ai": ("Data & AI", {"data_analytics_bi", "data_science_ml", "databases"}),
    "infra": ("Cloud, DevOps, networking & security", {"devops", "cloud", "networking_systems", "security"}),
    "qa": ("Software testing / QA", {"testing_qa"}),
    "design": ("Design (UI/UX, graphic)", {"design_ux"}),
    "business": ("Business, management & projects", {"business_office", "project_management"}),
    "marketing": ("Marketing & sales", {"marketing_sales"}),
    "finance": ("Finance & accounting", {"finance_accounting"}),
    "hr": ("Human resources", {"human_resources"}),
    "healthcare": ("Healthcare", {"healthcare"}),
    "engineering": ("Engineering (mechanical, electrical, civil)", {"engineering_core"}),
    "education": ("Education & teaching", {"education_teaching"}),
    "legal": ("Legal & administration", {"legal_admin"}),
}


def interest_categories(field_ids) -> set[str]:
    return set().union(*(FIELDS[f][1] for f in field_ids if f in FIELDS)) if field_ids else set()


def _opts(pairs) -> list[dict]:
    return [{"value": v, "label": l} for v, l in pairs]


# --------------------------------------------------------------- context --
class Ctx:
    """Everything the rules look at, computed once per request."""

    def __init__(self, entities: dict, career: dict | None, answers: dict):
        self.e = entities or {}
        self.career = career or {}
        self.answers = answers or {}
        self.skills = self.e.get("skills", [])
        self.experience = self.e.get("experience", [])
        self.education = self.e.get("education", [])
        self.months = self.e.get("total_experience_months")
        self.target = self.career.get("target_role")
        matches = self.career.get("matches") or []
        self.focus_role = self.target or (matches[0]["role"] if matches else None)

    def val(self, qid):
        a = self.answers.get(qid)
        return a["value"] if a else None

    def answered(self, qid, context=None) -> bool:
        a = self.answers.get(qid)
        return a is not None and (context is None or a.get("context") == context)

    @property
    def no_experience(self) -> bool:
        return not self.experience and not self.months

    @property
    def thin_profile(self) -> bool:
        return len(self.skills) < 8 or self.no_experience


# ------------------------------------------------------------- questions --
# Each builder returns the question (a dict) when it is needed, else None.

def q_target_role(c: Ctx):
    if c.target or c.answered("target_role"):
        return None
    matches = (c.career.get("matches") or [])[:5]
    return {
        "id": "target_role", "type": "role",
        "text": "Which role are you aiming for?",
        "why": "Your CV doesn't say which job you want. Pick one of your best-fit roles or type any role.",
        "options": _opts((m["role"], f"{m['role']} ({m['score']}% match)") for m in matches),
        "allow_other": True,
    }


def q_career_stage(c: Ctx):
    if not c.no_experience or c.answered("career_stage"):
        return None
    return {
        "id": "career_stage", "type": "single",
        "text": "Which best describes you right now?",
        "why": "Your CV shows no work experience, so we need to know where you're starting from.",
        "options": _opts([("student", "Student"), ("fresh_graduate", "Fresh graduate"),
                          ("career_switch", "Switching to a new field"),
                          ("returning", "Returning after a break"), ("working", "Working, but not listed in CV")]),
    }


def q_graduation_year(c: Ctx):
    if c.val("career_stage") != "student" or c.answered("graduation_year"):
        return None
    if any(ed.get("end_year") for ed in c.education):
        return None
    return {
        "id": "graduation_year", "type": "number", "min": 2024, "max": 2035,
        "text": "In which year do you expect to graduate?",
        "why": "Your CV doesn't show a graduation year; it decides between internships and full-time roles.",
    }


def q_experience_years(c: Ctx):
    # Experience is listed but its dates couldn't be read, or the user said they work
    listed_without_dates = c.experience and not c.months
    if not (listed_without_dates or c.val("career_stage") == "working") or c.answered("experience_years"):
        return None
    return {
        "id": "experience_years", "type": "number", "min": 0, "max": 50, "step": 0.5,
        "text": "How many years of work experience do you have in total?",
        "why": "We couldn't read dates for your experience in your CV.",
    }


def q_education_level(c: Ctx):
    if c.education or c.answered("education_level"):
        return None
    return {
        "id": "education_level", "type": "single",
        "text": "What is your highest education (completed or in progress)?",
        "why": "We couldn't find an education section in your CV.",
        "options": _opts([("matric", "Matric / O-Level"), ("intermediate", "Intermediate / A-Level"),
                          ("diploma", "Diploma / DAE"), ("bachelor", "Bachelor's"),
                          ("master", "Master's"), ("phd", "PhD")]),
    }


def q_education_field(c: Ctx):
    if c.val("education_level") not in ("diploma", "bachelor", "master", "phd") or c.answered("education_field"):
        return None
    return {
        "id": "education_field", "type": "text", "max_length": 80,
        "text": "What is (or was) your field of study?",
        "why": "e.g. Software Engineering, Business Administration, Nursing.",
    }


def q_interests(c: Ctx):
    if not c.thin_profile or c.answered("interests"):
        return None
    return {
        "id": "interests", "type": "multi", "max_choices": 3,
        "text": "Which fields interest you? (up to 3)",
        "why": "Your CV is still short, so your interests help us suggest the right careers.",
        "options": _opts((k, label) for k, (label, _) in FIELDS.items()),
    }


SOFT = "soft_skills"   # can't be "ticked" or rated meaningfully; the CV should show them in action


def _missing_role_skills(c: Ctx, limit: int = 10) -> list[str]:
    """The role's most important learned skills the CV doesn't show, hard skills only."""
    if not c.focus_role:
        return []
    prof = market_model.role_profile(c.focus_role)
    have = {s["name"].lower() for s in c.skills}
    return [s["name"] for s in (prof or {}).get("skills", [])[:30]
            if s["name"].lower() not in have and s.get("category") != SOFT][:limit]


def q_extra_skills(c: Ctx):
    """Skills the role needs that the CV doesn't show; maybe the user just forgot them.
    Re-asked if the target role changes, because the list depends on the role."""
    if not c.focus_role or c.answered("extra_skills", context=c.focus_role):
        return None
    missing = _missing_role_skills(c)
    if not missing:
        return None
    return {
        "id": "extra_skills", "type": "multi", "context": c.focus_role,
        "text": f"Do you already know any of these? They're often required for {c.focus_role} jobs.",
        "why": "Your CV doesn't mention them. Tick only the ones you can actually use; you can also type others.",
        "options": _opts((s, s) for s in missing),
        "allow_other": True,
    }


def _weak_evidence_skills(c: Ctx, limit: int = 5) -> list[str]:
    """Skills only listed (mentioned once, never in experience/projects) that matter for the role."""
    role_skills = []
    if c.focus_role:
        prof = market_model.role_profile(c.focus_role)
        role_skills = [s["name"].lower() for s in (prof or {}).get("skills", [])[:25]]
    weak = [s["name"] for s in c.skills
            if s.get("mentions", 1) <= 1 and s.get("category") != SOFT
            and not ({"experience", "projects"} & set(s.get("sections", [])))]
    relevant = [s for s in weak if s.lower() in role_skills]
    return relevant[:limit]


def q_skill_levels(c: Ctx):
    if c.answered("skill_levels", context=c.focus_role):
        return None
    items = _weak_evidence_skills(c)
    if not items:
        return None
    return {
        "id": "skill_levels", "type": "rating", "context": c.focus_role,
        "text": "How comfortable are you with these skills?",
        "why": "Your CV lists them but doesn't show them used in a job or project, so your learning plan "
               "should know your real level.",
        "items": items, "scale": LEVELS,
    }


def q_location(c: Ctx):
    if c.e.get("location") or c.answered("location"):
        return None
    return {
        "id": "location", "type": "text", "max_length": 60,
        "text": "Which city and country are you in?",
        "why": "Your CV has no location; we use it to show jobs you're eligible for.",
    }


# These can't come from a CV, so they are asked once for everyone (needed for the roadmap)
def q_weekly_hours(c: Ctx):
    if c.answered("weekly_hours"):
        return None
    return {
        "id": "weekly_hours", "type": "single",
        "text": "How many hours per week can you spend learning?",
        "why": "Your learning roadmap is planned around this.",
        "options": _opts([("2-5", "2 to 5 hours"), ("5-10", "5 to 10 hours"),
                          ("10-20", "10 to 20 hours"), ("20+", "More than 20 hours")]),
    }


def q_timeline(c: Ctx):
    if c.answered("timeline"):
        return None
    return {
        "id": "timeline", "type": "single",
        "text": "When do you want to be job-ready for your target role?",
        "why": "Decides how much goes into each week of your roadmap.",
        "options": _opts([("1m", "Within 1 month"), ("3m", "In 3 months"),
                          ("6m", "In 6 months"), ("12m", "In about a year")]),
    }


def q_learning_style(c: Ctx):
    if c.answered("learning_style"):
        return None
    return {
        "id": "learning_style", "type": "single",
        "text": "How do you learn best?",
        "why": "We pick roadmap resources (videos, reading, projects) to suit you.",
        "options": _opts([("video", "Watching videos / courses"), ("reading", "Reading docs and articles"),
                          ("projects", "Building projects hands-on"), ("mixed", "A mix")]),
    }


# Order = the order the user sees them in
QUESTIONS = [q_target_role, q_career_stage, q_graduation_year, q_experience_years, q_education_level,
             q_education_field, q_interests, q_extra_skills, q_skill_levels, q_location,
             q_weekly_hours, q_timeline, q_learning_style]
BY_ID = {f.__name__[2:]: f for f in QUESTIONS}


def pending_questions(entities: dict, career: dict | None, answers: dict) -> list[dict]:
    c = Ctx(entities, career, answers)
    return [q for f in QUESTIONS if (q := f(c))]


# ------------------------------------------------------------ validation --
class AnswerError(ValueError):
    pass


def _canonical_skills(values: list) -> tuple[list[str], list[str]]:
    """Map typed skills to the skill list's names; unknown ones are returned separately."""
    known, unknown = [], []
    for v in values:
        v = str(v).strip()[:60]
        if not v:
            continue
        hit = find_skills(v, in_skills_section=True)
        (known.extend(hit) if hit else unknown.append(v))
    return list(dict.fromkeys(known)), unknown


def validate(q: dict, value):
    """Return the cleaned answer, or raise AnswerError with a user-friendly message."""
    t = q["type"]
    allowed = {o["value"] for o in q.get("options", [])}
    if t == "single":
        if value not in allowed:
            raise AnswerError(f"Choose one of: {', '.join(sorted(allowed))}")
        return value
    if t == "number":
        try:
            n = float(value)
        except (TypeError, ValueError):
            raise AnswerError("Enter a number")
        if not q["min"] <= n <= q["max"]:
            raise AnswerError(f"Enter a number between {q['min']} and {q['max']}")
        return int(n) if q.get("step") is None else n
    if t == "text":
        s = re.sub(r"\s+", " ", str(value or "")).strip()
        if not 2 <= len(s) <= q.get("max_length", 100):
            raise AnswerError(f"Enter 2 to {q.get('max_length', 100)} characters")
        return s
    if t == "role":
        role = market_model.find_role(str(value or ""))
        if not role:
            raise AnswerError("We don't know that role yet; try a more common job title")
        return role
    if t == "multi":
        if not isinstance(value, list):
            raise AnswerError("Send a list of choices")
        if q.get("max_choices") and len(value) > q["max_choices"]:
            raise AnswerError(f"Choose at most {q['max_choices']}")
        picked = [v for v in value if v in allowed]
        others = [v for v in value if v not in allowed]
        if others and not q.get("allow_other"):
            raise AnswerError(f"Unknown choice: {others[0]}")
        if q["id"] == "extra_skills":
            known, unknown = _canonical_skills(others)
            return {"skills": list(dict.fromkeys(picked + known)), "unrecognised": unknown}
        return picked
    if t == "rating":
        if not isinstance(value, dict):
            raise AnswerError("Send {skill: level}")
        bad = [lvl for lvl in value.values() if lvl not in LEVELS]
        if bad:
            raise AnswerError(f"Levels must be one of: {', '.join(LEVELS)}")
        return {k: v for k, v in value.items() if k in q["items"]}
    raise AnswerError("Unknown question type")


# ---------------------------------------------- answers -> career profile --
def profile_entities(entities: dict, answers: dict) -> dict:
    """The resume entities enriched with questionnaire answers, used for CAREER matching.
    (The ATS score stays about the CV document itself, so it doesn't use these.)"""
    e = dict(entities or {})
    answers = answers or {}
    extra = (answers.get("extra_skills") or {}).get("value") or {}
    if extra.get("skills"):
        have = {s["name"].lower() for s in e.get("skills", [])}
        added = [{"name": s, "category": "self_reported", "mentions": 1, "sections": ["questionnaire"],
                  "self_reported": True} for s in extra["skills"] if s.lower() not in have]
        e["skills"] = list(e.get("skills", [])) + added
    years = (answers.get("experience_years") or {}).get("value")
    if years is not None and not e.get("total_experience_months"):
        e["total_experience_months"] = round(float(years) * 12)
    if not e.get("location") and answers.get("location"):
        e["location"] = answers["location"]["value"]
    return e


def answer_summary(answers: dict) -> dict:
    """Flat {question_id: value} view, handy for the roadmap (Day 11) and the app."""
    return {qid: a["value"] for qid, a in (answers or {}).items()}
