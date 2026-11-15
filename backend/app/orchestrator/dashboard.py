"""Dashboard synthesis (Day 24): one summary of everything the agents wrote.

The orchestrator reads the whole Blackboard state and turns it into:
    tiles       - ATS score, career match, roadmap progress, interviews
    next_step   - the single most useful thing to do now (rule-based, in priority order)
    ats_history - the ATS score of every CV upload, for the chart
    activity    - the latest things that happened, newest first

Read-only and deterministic: no agent is called and no LLM is used, so the dashboard is
instant and costs nothing. It is rebuilt on every request, so it is always current.
"""
import time

from app.services import roadmap as rm

GOOD_ATS = 70                  # below this, fixing the CV comes first
ACTIVITY_LIMIT = 8


def _ats_tile(resume: dict) -> dict | None:
    ats = resume.get("ats") or {}
    score = ats.get("readability_score")
    if score is None:
        return None
    history = resume.get("history") or []
    previous = history[-2]["score"] if len(history) >= 2 else None
    return {"score": score, "grade": ats.get("grade"),
            "change": None if previous is None else score - previous,
            "top_fix": ((ats.get("top_fixes") or [{}])[0]).get("fix") or None}


def _match_tile(career: dict) -> dict | None:
    target = career.get("target_match")
    if career.get("target_role") and target:
        return {"role": career["target_role"], "score": target.get("score"), "basis": "target"}
    matches = career.get("matches") or []
    if matches:
        return {"role": matches[0]["role"], "score": matches[0].get("score"), "basis": "best fit"}
    return None


def _roadmap_tile(plan: dict | None, now: float) -> dict | None:
    if not plan or not plan.get("weeks"):
        return None
    p = rm.progress(plan, now)
    next_task = next((t for w in plan["weeks"] for t in w["tasks"] if not t["done"]), None)
    return {"role": plan.get("role"), "percent": p["percent"], "status": p["status"], "message": p["message"],
            "tasks_done": p["tasks_done"], "tasks_total": p["tasks_total"],
            "next_task": next_task and {"title": next_task.get("title"), "skill": next_task.get("skill")}}


def _graded(interviews: dict) -> list[dict]:
    return [s for s in interviews.get("sessions", []) if (s.get("report") or {}).get("overall") is not None]


def _interview_tile(interviews: dict) -> dict:
    graded = _graded(interviews)
    scores = [s["report"]["overall"] for s in graded]
    return {"count": len(graded), "last": scores[-1] if scores else None, "best": max(scores) if scores else None,
            "last_role": graded[-1].get("role") if graded else None}


def next_step(state: dict, now: float | None = None) -> dict:
    """{"title", "text", "action", "tab"}: tab is the app tab that does it."""
    now = now or time.time()
    resume = state.get("resume") or {}
    career = state.get("career") or {}
    ats = _ats_tile(resume)
    if ats is None:
        return {"title": "Upload your CV", "text": "Everything starts here: we check it for ATS problems and "
                "use it to find careers that fit you.", "action": "Upload CV", "tab": "resume"}
    if ats["score"] < GOOD_ATS:
        fix = f" Start with this: {ats['top_fix']}" if ats["top_fix"] else ""
        return {"title": "Improve your CV", "text": f"Your ATS score is {ats['score']}/100. Recruiters' "
                f"systems may skip it below {GOOD_ATS}.{fix}", "action": "See the fixes", "tab": "resume"}
    if not career.get("matches"):
        return {"title": "Find your best-fit careers", "text": "Answer a few quick questions and we'll match "
                "your skills to real roles.", "action": "Get matches", "tab": "career"}
    if not career.get("target_role"):
        return {"title": "Choose a target role", "text": "Pick the role you're aiming for, so your roadmap, "
                "jobs and interviews focus on it.", "action": "Choose a role", "tab": "career"}
    road = _roadmap_tile(state.get("roadmap"), now)
    if road is None:
        return {"title": "Build your learning roadmap", "text": f"A week-by-week plan for the skills you still "
                f"need as a {career['target_role']}.", "action": "Build roadmap", "tab": "career"}
    interviews = _interview_tile(state.get("interviews") or {})
    if interviews["count"] == 0:
        return {"title": "Practise a mock interview", "text": f"A live {career['target_role']} interview with "
                "an AI interviewer, then a detailed report.", "action": "Start interview", "tab": "interview"}
    if road["status"] == "behind" and road["next_task"]:
        return {"title": "Catch up on your roadmap", "text": f"{road['message']} Next: {road['next_task']['title']}.",
                "action": "Open roadmap", "tab": "career"}
    if not (state.get("jobs") or {}).get("top"):
        return {"title": "Look at matching jobs", "text": "Remote jobs open to applicants from Pakistan, ranked "
                "by how well they fit your skills.", "action": "See jobs", "tab": "jobs"}
    if road["next_task"]:
        return {"title": "Keep learning", "text": f"Next on your roadmap: {road['next_task']['title']}.",
                "action": "Open roadmap", "tab": "career"}
    return {"title": "Practise another interview", "text": "Your roadmap is complete. Keep your answers sharp "
            "with another mock interview.", "action": "Start interview", "tab": "interview"}


def activity(state: dict, limit: int = ACTIVITY_LIMIT) -> list[dict]:
    """[{"at", "kind", "text"}] newest first."""
    items = []
    for h in (state.get("resume") or {}).get("history") or []:
        if h.get("at"):
            items.append({"at": h["at"], "kind": "resume", "text": f"Uploaded your CV: ATS score {h['score']}/100"})
    career = state.get("career") or {}
    if career.get("target_set_at"):
        items.append({"at": career["target_set_at"], "kind": "career",
                      "text": f"Set your target role: {career.get('target_role')}"})
    plan = state.get("roadmap") or {}
    if plan.get("generated_at"):
        items.append({"at": plan["generated_at"], "kind": "roadmap",
                      "text": f"Built a roadmap for {plan.get('role') or 'your role'}"})
    for w in plan.get("weeks") or []:
        for t in w["tasks"]:
            if t.get("done") and t.get("done_at"):
                items.append({"at": t["done_at"], "kind": "roadmap", "text": f"Finished: {t.get('title')}"})
    for s in _graded(state.get("interviews") or {}):
        kind = "Live interview" if s.get("mode") == "live" else "Practice interview"
        items.append({"at": s.get("created_at") or 0, "kind": "interview",
                      "text": f"{kind}: {s.get('role')}, scored {s['report']['overall']}/100"})
    items.sort(key=lambda i: -i["at"])
    return items[:limit]


def summary(state: dict, now: float | None = None) -> dict:
    now = now or time.time()
    resume = state.get("resume") or {}
    return {
        "tiles": {"ats": _ats_tile(resume), "match": _match_tile(state.get("career") or {}),
                  "roadmap": _roadmap_tile(state.get("roadmap"), now),
                  "interviews": _interview_tile(state.get("interviews") or {})},
        "next_step": next_step(state, now),
        "ats_history": [{"at": h.get("at"), "score": h["score"]} for h in resume.get("history") or []],
        "activity": activity(state),
        "updated_at": now,
    }
