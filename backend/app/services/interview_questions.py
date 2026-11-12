"""Mock-interview questions made for ONE user (Day 15).

1. PLAN (rules, always the same logic): the mix of question types for a session, and the
   skill / project each question is about. All of it comes from the Blackboard:
     intro        "tell me about yourself" for the target role
     technical    skills the user HAS that the role needs most (market-model weights)
     project      one of the user's own projects (or jobs) from the CV
     gap          a skill the role needs that the user LACKS (honest-answer practice)
     behavioural  teamwork, conflict, failure... (STAR answers)
     situational  a realistic on-the-job situation for the role
   Level (entry / mid / senior) comes from experience months and the career stage answer,
   and sets the difficulty. Skills asked least recently are picked first.
2. WRITE: Gemini (fast tier) writes every planned question in ONE call, with the key points
   a good answer covers (used for grading later) and without repeating earlier questions.
3. FALLBACK: any question Gemini didn't give (or no Gemini at all) is filled from templates,
   so a session is always complete.
Nothing personal (name, email, phone, company names) is sent to Gemini.
"""
import hashlib
import random
import re
import time
import uuid

from pydantic import BaseModel

from app.services import llm

TYPES = ("intro", "technical", "project", "gap", "behavioural", "situational")
TIME_LIMIT = {"intro": 90, "technical": 120, "project": 150, "gap": 90, "behavioural": 150, "situational": 120}
MIN_COUNT, MAX_COUNT, DEFAULT_COUNT = 3, 12, 8
SOFT = {"soft_skills", "self_reported"}


# ------------------------------------------------------------------ level --
def level_of(profile: dict, answers: dict | None = None) -> str:
    stage = ((answers or {}).get("career_stage") or {}).get("value")
    months = profile.get("total_experience_months") or 0
    if stage in {"student", "fresh_graduate"} or months < 12:
        return "entry"
    return "mid" if months < 60 else "senior"


DIFFICULTY = {"entry": "easy", "mid": "medium", "senior": "hard"}


# ------------------------------------------------------------------- plan --
def _mix(count: int, has_projects: bool, has_gaps: bool) -> list[str]:
    """Question types for a session of `count` questions, in interview order."""
    n_tech = max(1, round(count * 0.3))
    n_beh = max(1, round(count * 0.25))
    n_gap = (1 if count >= 5 else 0) + (1 if count >= 10 else 0) if has_gaps else 0
    plan = ["intro"]
    if has_projects and count >= 4:
        plan.append("project")
    plan += ["technical"] * n_tech + ["gap"] * n_gap + ["behavioural"] * n_beh
    if count >= 6:
        plan.append("situational")
    fill = ["technical", "behavioural"] if not has_gaps else ["technical", "behavioural", "gap"]
    i = 0
    while len(plan) < count:
        plan.append(fill[i % len(fill)])
        i += 1
    return plan[:count]


def _least_asked(names: list[str], recent: dict[str, int]) -> list[str]:
    """Keep the order (importance) but skills asked often recently go to the back."""
    return sorted(names, key=lambda s: recent.get(s.lower(), 0))     # stable: ties keep importance


def plan_session(profile: dict, role: str, coverage: dict | None, answers: dict | None = None,
                 count: int = DEFAULT_COUNT, recent_skills: dict[str, int] | None = None) -> dict:
    """What to ask: [{type, skill?, project?}] plus the context Gemini needs."""
    count = max(MIN_COUNT, min(MAX_COUNT, int(count)))
    recent = recent_skills or {}
    skills = [s for s in profile.get("skills", []) if s.get("category") not in SOFT]
    have = {s["name"].lower(): s for s in skills}
    matched = [m for m in (coverage or {}).get("matched", []) if m.lower() in have]
    # strongest other skills (mentioned most, in the CV's skill/experience sections)
    others = [s["name"] for s in sorted(skills, key=lambda s: -s.get("mentions", 1)) if s["name"] not in matched]
    tech_pool = _least_asked(matched, recent) + _least_asked(others, recent)
    gaps = _least_asked([m["name"] for m in (coverage or {}).get("missing", [])][:8], recent)
    projects = [{"title": p["title"], "skills": p.get("skills", [])[:6],
                 "summary": " ".join(p.get("description", []))[:300]}
                for p in profile.get("projects", []) if p.get("title")]
    jobs = [{"title": j["title"], "skills": [], "summary": " ".join(j.get("bullets", []))[:300]}
            for j in profile.get("experience", []) if j.get("title")]
    stories = projects or jobs
    types = _mix(count, bool(stories), bool(gaps))
    if not tech_pool:                                   # no hard skills found: ask about the role instead
        types = ["situational" if t == "technical" else t for t in types]
    slots, ti, gi = [], 0, 0
    for t in types:
        slot = {"type": t}
        if t == "technical":
            slot["skill"] = tech_pool[ti % len(tech_pool)]
            ti += 1
        elif t == "gap":
            slot["skill"] = gaps[gi % len(gaps)]
            gi += 1
        elif t == "project":
            slot["project"] = random.choice(stories[:3])
        slots.append(slot)
    level = level_of(profile, answers)
    return {"role": role, "level": level, "difficulty": DIFFICULTY[level], "slots": slots}


# -------------------------------------------------------------- templates --
_STAR = ["Describes a specific situation (not a general habit)", "Explains their own task and actions clearly",
         "Gives a concrete result, ideally with numbers", "Says what they learned or would do differently"]

TEMPLATES = {
    "intro": [
        ("Tell me about yourself and why you want to work as a {role}.",
         ["Short summary of background and education", "Most relevant skills and experience for {role}",
          "One concrete achievement or project", "Clear reason for wanting this role"]),
        ("Walk me through your background. What led you to apply for a {role} position?",
         ["Clear, short story of their path", "Links past experience to {role}",
          "Mentions strengths that fit the role", "Shows motivation and goals"]),
        ("What makes you a good fit for a {role} role, and what are you looking for in your next position?",
         ["Two or three strengths backed by examples", "Knows what the {role} job involves",
          "Realistic goals that match the role", "Positive, confident tone"]),
        ("Introduce yourself in two minutes, focusing on what is most relevant to a {role}.",
         ["Stays relevant to {role} and within time", "Highlights strongest skills with evidence",
          "Mentions a project or result they are proud of", "Ends with why this role, now"]),
    ],
    "technical": [
        ("How would you explain {skill} to a new team member, and where have you used it yourself?",
         ["Correct, simple explanation of what {skill} is for", "A concrete example from their own work",
          "When to use it and when not to", "Mentions a common mistake or best practice"]),
        ("Tell me about a problem you solved using {skill}. What exactly did you do, and what was the result?",
         ["Clear description of the problem", "Specific steps they took with {skill}",
          "A measurable or visible result", "What they would improve next time"]),
        ("What are common mistakes people make with {skill}, and how do you avoid them?",
         ["Names real, specific mistakes", "Explains why they cause problems",
          "Gives practical ways to avoid them", "Backs it up with own experience"]),
        ("How would you decide whether {skill} is the right choice for a {role} task, and what would you compare it with?",
         ["Understands what {skill} is good and bad at", "Names realistic alternatives",
          "Uses clear criteria (cost, time, quality, team skills)", "Reaches a reasoned decision"]),
    ],
    "project": [
        ("Walk me through \"{project}\". What was your part, what did you use, and what would you do differently today?",
         ["Clear goal of the project", "Their own contribution (not only the team's)",
          "Tools or skills used and why", "Result, and an honest lesson learned"]),
        ("What was the hardest problem in \"{project}\" and how did you solve it?",
         ["A specific, real difficulty", "How they analysed it", "The solution and alternatives considered",
          "Result and what they learned"]),
    ],
    "gap": [
        ("Many {role} roles ask for {skill}. What do you know about it, and how would you get up to speed quickly?",
         ["Honest about their current level", "Basic understanding of what {skill} is used for",
          "Connects it to a skill they already have", "A concrete, short learning plan"]),
        ("If your first task as a {role} needed {skill}, which you haven't used much, what would you do?",
         ["Does not pretend to be an expert", "Practical steps: docs, small test, asking for help",
          "Manages time and keeps the team informed", "Shows ability to learn fast"]),
    ],
    "behavioural": [
        ("Tell me about a time you disagreed with a teammate. How did you handle it?", _STAR),
        ("Describe a time you made a mistake at work or in a project. What happened next?", _STAR),
        ("Tell me about a time you had a tight deadline. How did you manage it?", _STAR),
        ("Give an example of when you took the lead without being asked.", _STAR),
        ("Tell me about a time you had to learn something new very quickly.", _STAR),
        ("Describe a situation where you received critical feedback. How did you respond?", _STAR),
        ("Tell me about your proudest achievement so far.", _STAR),
        ("Describe a time you had to explain something complex to someone without your background.", _STAR),
    ],
    "situational": [
        ("Imagine your first week as a {role}: you get a task with unclear requirements and a tight deadline. What do you do?",
         ["Asks clarifying questions early", "Breaks the task into steps and priorities",
          "Communicates progress and risks", "Delivers something useful on time"]),
        ("As a {role}, you notice a serious problem in work that is already finished and shared. What do you do?",
         ["Takes ownership instead of hiding it", "Checks the impact first",
          "Tells the right people quickly", "Proposes a fix and a way to prevent it"]),
        ("Two senior people give you opposite instructions for the same {role} task. How do you handle it?",
         ["Stays neutral and respectful", "Clarifies the goal and priorities",
          "Brings both together or escalates properly", "Keeps a record of the decision"]),
    ],
}


def qhash(text: str) -> str:
    return hashlib.sha1(re.sub(r"[^a-z0-9]", "", text.lower()).encode()).hexdigest()[:12]


def _from_template(slot: dict, role: str, used: set[str]) -> dict:
    options = TEMPLATES[slot["type"]]
    fills = {"role": role, "skill": slot.get("skill", ""), "project": (slot.get("project") or {}).get("title", "")}
    choices = [(q.format(**fills), [k.format(**fills) for k in kp]) for q, kp in options]
    fresh = [c for c in choices if qhash(c[0]) not in used] or choices
    q, kp = random.choice(fresh)
    return {"question": q, "key_points": kp}


# ------------------------------------------------------------------ write --
class _Q(BaseModel):
    slot: int
    question: str
    key_points: list[str]


class _Batch(BaseModel):
    questions: list[_Q]


def _prompt(plan: dict, profile: dict, avoid: list[str]) -> str:
    lines = []
    for i, s in enumerate(plan["slots"]):
        extra = ""
        if s.get("skill"):
            extra = f" | skill: {s['skill']}"
        if s.get("project"):
            p = s["project"]
            extra = f" | about their work: \"{p['title']}\" (used: {', '.join(p['skills']) or 'n/a'}; {p['summary']})"
        lines.append(f"{i}. {s['type']}{extra}")
    skills = ", ".join(s["name"] for s in profile.get("skills", [])[:25])
    return (
        f"You are an experienced interviewer hiring a {plan['role']} ({plan['level']} level, "
        f"{plan['difficulty']} difficulty). The candidate's skills: {skills or 'not listed'}.\n"
        "Write ONE interview question for each numbered slot below, in the same order.\n"
        "Types: intro = tell me about yourself for this role; technical = test real understanding of the "
        "skill (not a definition quiz; ask how/why/when, trade-offs, or a short scenario); project = dig into "
        "the named work from their CV; gap = a skill the role needs that the candidate does NOT list yet: "
        "ask in a fair way that rewards honesty and a learning plan; behavioural = past behaviour, answered "
        "with STAR; situational = a realistic on-the-job scenario for this role.\n"
        "Rules: questions are spoken aloud, so one or two clear sentences, no lists, no code to write, "
        f"answerable in about 2 minutes; match the {plan['level']} level; sound like a real interviewer; "
        "every question different.\n"
        "For each give `key_points`: 3 to 5 short points a strong answer would cover (used to grade the answer).\n"
        + ("Do NOT repeat or rephrase these earlier questions:\n- " + "\n- ".join(avoid[:20]) + "\n" if avoid else "")
        + "SLOTS:\n" + "\n".join(lines))


def _valid(q: dict) -> bool:
    text = str(q.get("question", "")).strip()
    kp = [k for k in q.get("key_points") or [] if str(k).strip()]
    return 15 <= len(text) <= 400 and 2 <= len(kp) <= 6


def write_questions(plan: dict, profile: dict, avoid: list[str] | None = None,
                    used_hashes: set[str] | None = None) -> dict:
    """The session: every slot gets a question (Gemini first, templates for the rest)."""
    used = set(used_hashes or set())
    out = llm.generate_json(_prompt(plan, profile, avoid or []), _Batch, tier="fast", temperature=0.8)
    by_slot = {}
    for q in (out or {}).get("questions", []):
        if isinstance(q.get("slot"), int) and 0 <= q["slot"] < len(plan["slots"]) and _valid(q) \
                and qhash(q["question"]) not in used:
            by_slot.setdefault(q["slot"], q)
    questions, from_ai = [], 0
    for i, slot in enumerate(plan["slots"]):
        q = by_slot.get(i)
        if q:
            from_ai += 1
            q = {"question": q["question"].strip(), "key_points": [str(k).strip() for k in q["key_points"]][:5]}
        else:
            q = _from_template(slot, plan["role"], used)
        used.add(qhash(q["question"]))
        questions.append({
            "id": f"q{i + 1}", "type": slot["type"], "skill": slot.get("skill"),
            "project": (slot.get("project") or {}).get("title"), "question": q["question"],
            "key_points": q["key_points"], "time_limit_sec": TIME_LIMIT[slot["type"]],
            "difficulty": plan["difficulty"], "source": "gemini" if i in by_slot else "template"})
    source = "gemini" if from_ai == len(questions) else ("template" if from_ai == 0 else "mixed")
    return {"id": uuid.uuid4().hex[:12], "created_at": time.time(), "role": plan["role"],
            "level": plan["level"], "questions": questions, "source": source, "status": "ready"}
