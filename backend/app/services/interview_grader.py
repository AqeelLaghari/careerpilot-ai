"""Interview report (Day 21): grade every answer and give one overall score.

Overall score (0-100) = content 60% + speaking 20% + presence 20%
  content   what was said. ONE Gemini call (smart tier) for the whole interview grades every
            answer out of 10: are the technical facts correct (with corrections), does it answer
            the question, are the key points covered, are there specifics (what YOU did, how, the
            result), STAR for behavioural answers. Personal claims can't be checked, so they are
            never marked wrong. If a word looks misheard by the speech-to-text, it is flagged
            instead of being called a mistake.
            Fallback without Gemini: SBERT similarity between the answer and the key points,
            plus answer length (no corrections then; the report says so).
  speaking  pace, filler words, habit words, long pauses (Day 17 metrics, whole interview).
  presence  eye contact (Day 19), weighted by answer length.
Without camera data the weights become content 75% + speaking 25%.
"""
import logging
import math

from pydantic import BaseModel

from app.services import llm, privacy

log = logging.getLogger(__name__)

WEIGHTS = {"content": 0.6, "speaking": 0.2, "presence": 0.2}
GEMINI_BUDGET = 120          # s; the user sees "preparing your report"
MIN_WORDS = 3                # fewer words = nothing was really said
GRADED_KINDS = {"question", "follow_up", "repeat"}
LEVELS = [(85, "excellent"), (70, "good"), (55, "fair"), (0, "needs work")]


# ------------------------------------------------------------------ answers --
def answers_to_grade(live: dict) -> list[dict]:
    """The answered turns, with their topic. An empty answer followed by "Sorry, could you
    say that again?" is skipped: the next answer replaces it."""
    topics = {t["id"]: t for t in live.get("agenda", [])}
    turns = live.get("turns", [])
    out = []
    for i, t in enumerate(turns):
        ans = t.get("answer")
        if ans is None or t.get("kind") not in GRADED_KINDS:
            continue
        text = (ans.get("transcript") or "").strip()
        nxt = turns[i + 1] if i + 1 < len(turns) else None
        if len(text.split()) < MIN_WORDS and nxt and nxt.get("kind") == "repeat":
            continue
        topic = topics.get(t.get("topic_id")) or {}
        out.append({"turn_id": t["id"], "question": t["text"], "answer": text, "kind": t["kind"],
                    "type": topic.get("type") or "general", "key_points": topic.get("key_points") or [],
                    "skill": topic.get("skill"), "check": t.get("check")})
    return out


class _Fix(BaseModel):
    said: str            # what the candidate said (short quote or paraphrase)
    correct: str         # the correct fact


class _Grade(BaseModel):
    turn_id: str
    score: int           # 0-10
    verdict: str         # correct | partly_correct | incorrect | no_facts
    corrections: list[_Fix]
    covered: list[str]
    missing: list[str]
    star: str            # behavioural/situational: which STAR parts were missing; else ""
    misheard: str        # a word that was probably misheard by speech-to-text; else ""
    feedback: str
    better_answer: str


class _Report(BaseModel):
    answers: list[_Grade]
    summary: str
    strengths: list[str]
    improvements: list[str]


def _prompt(live: dict, items: list[dict]) -> str:
    private = live.get("private")
    blocks = []
    for it in items:
        lines = [f"[{it['turn_id']}] type: {it['type']}" + (f", skill: {it['skill']}" if it.get("skill") else ""),
                 f"Question: {privacy.scrub(it['question'], private)}",
                 f"Answer: {privacy.scrub(it['answer'][:1500], private) or '(said nothing)'}"]
        if it["key_points"]:
            lines.append("Key points a strong answer covers: " + "; ".join(it["key_points"]))
        if it.get("check") and it["check"].get("note"):
            lines.append(f"Interviewer's note during the interview: {it['check']['note']}")
        blocks.append("\n".join(lines))
    return (
        f"You are an experienced, fair interviewer writing the feedback report for a mock interview for a "
        f"{live.get('role')} position ({live.get('level')} level). Grade EVERY answer below.\n"
        "For each answer give:\n"
        "- score 0-10: 9-10 excellent (correct, complete, specific), 7-8 good, 5-6 fair (correct but vague "
        "or incomplete), 3-4 weak (major gaps or errors), 0-2 no real answer. Be honest, not harsh; judge "
        "it for the level.\n"
        "- verdict: correct | partly_correct | incorrect for technical or factual content; no_facts when the "
        "answer is personal (about themselves, their projects or experience) and there is nothing to check.\n"
        "- corrections: every technical or factual error, as {said, correct}, short. NEVER mark personal "
        "claims (their projects, jobs, grades, team size) as errors. The answers are speech-to-text: if a "
        "single odd word looks misheard (e.g. 'docker' as 'doctor'), put it in `misheard` instead of a "
        "correction, and grade the intended meaning.\n"
        "- covered / missing: which key points (or other important points) were covered / missing, short.\n"
        "- star: for behavioural or situational answers, which of Situation, Task, Action, Result were missing "
        "(e.g. 'No clear result'); otherwise ''.\n"
        "- feedback: 1-2 sentences, specific and encouraging, speaking to the candidate as 'you'.\n"
        "- better_answer: a short example of a stronger answer (2-4 sentences, first person, in their "
        "situation; don't invent big achievements).\n"
        "Then: summary (2-3 sentences on the whole interview), strengths (2-4 short points), improvements "
        "(2-4 short, practical points).\n"
        f"Use the turn ids exactly as given. Plain English. {privacy.NOTE}\n\n"
        + "\n\n".join(blocks))


def _gemini_grades(live: dict, items: list[dict]) -> dict | None:
    out = llm.generate_json(_prompt(live, items), _Report, tier="smart", temperature=0.2, timeout=GEMINI_BUDGET)
    if not out:
        return None
    by_id = {g.get("turn_id"): g for g in out.get("answers", [])}
    if not any(it["turn_id"] in by_id for it in items):
        return None
    return {"by_id": by_id, "summary": out.get("summary", ""), "strengths": out.get("strengths", []),
            "improvements": out.get("improvements", [])}


def _clean_grade(g: dict, item: dict) -> dict:
    score = g.get("score")
    score = max(0, min(10, int(score))) if isinstance(score, (int, float)) else 0
    if len(item["answer"].split()) < MIN_WORDS:
        score = 0
    verdict = g.get("verdict") if g.get("verdict") in ("correct", "partly_correct", "incorrect", "no_facts") else "no_facts"
    short = lambda xs, n, m: [str(x)[:m] for x in (xs or []) if str(x).strip()][:n]
    fixes = [{"said": str(f.get("said", ""))[:200], "correct": str(f.get("correct", ""))[:300]}
             for f in (g.get("corrections") or []) if isinstance(f, dict) and f.get("correct")][:4]
    return {"score": score, "verdict": verdict, "corrections": fixes, "covered": short(g.get("covered"), 5, 120),
            "missing": short(g.get("missing"), 5, 120), "star": str(g.get("star") or "")[:200],
            "misheard": str(g.get("misheard") or "")[:120], "feedback": str(g.get("feedback") or "")[:400],
            "better_answer": str(g.get("better_answer") or "")[:700], "graded_by": "gemini"}


def _fallback_grade(item: dict) -> dict:
    """No Gemini: how close the answer is in MEANING to the key points (SBERT), and its length."""
    words = len(item["answer"].split())
    if words < MIN_WORDS:
        return {"score": 0, "verdict": "no_facts", "corrections": [], "covered": [], "missing": item["key_points"][:5],
                "star": "", "misheard": "", "feedback": "No answer was heard for this question.",
                "better_answer": "", "graded_by": "rules"}
    covered, missing = [], []
    if item["key_points"]:
        from app.services import embeddings
        vecs = embeddings.embed([item["answer"]] + item["key_points"])
        for point, sim in zip(item["key_points"], (vecs[1:] @ vecs[0]).tolist()):
            (covered if sim >= 0.35 else missing).append(point)
        coverage = len(covered) / len(item["key_points"])
    else:
        coverage = 0.6
    length = min(1.0, words / 60)                    # about 60+ words is a full spoken answer
    score = round(10 * (0.65 * coverage + 0.35 * length))
    tip = ("Cover these points too: " + "; ".join(missing[:3]) + ".") if missing else "You covered the main points."
    return {"score": max(1, min(10, score)), "verdict": "no_facts", "corrections": [], "covered": covered[:5],
            "missing": missing[:5], "star": "", "misheard": "", "feedback": tip, "better_answer": "",
            "graded_by": "rules"}


# --------------------------------------------------------- speaking + eyes --
def speaking_score(live: dict) -> dict:
    """Pace, fillers, habits and long pauses over all answers together."""
    ms = [(t.get("answer") or {}).get("metrics") or {} for t in live.get("turns", [])]
    ms = [m for m in ms if m.get("word_count")]
    if not ms:
        return {"score": None}
    secs = sum(m.get("speaking_seconds", 0) for m in ms) or 1
    minutes = secs / 60
    words = sum(m["word_count"] for m in ms)
    wpm = round(words / minutes) if minutes else 0
    fillers = sum(m.get("filler_count", 0) for m in ms)
    habits = sum(m.get("habit_count", 0) for m in ms)
    pauses = sum(m.get("long_pauses", 0) for m in ms)
    from app.services.speech import _pace
    pace, _ = _pace(wpm)
    score = 100
    score -= {"good": 0, "a bit slow": 8, "a bit fast": 8}.get(pace, 20)
    score -= min(30, max(0.0, fillers / minutes - 3) * 5)
    score -= min(15, max(0.0, habits / minutes - 4) * 3)
    score -= min(20, max(0.0, pauses / minutes - 1) * 8)
    return {"score": round(max(0, score)), "wpm": wpm, "pace": pace, "fillers": fillers,
            "fillers_per_min": round(fillers / minutes, 1), "habits": habits, "long_pauses": pauses,
            "speaking_minutes": round(minutes, 1)}


def presence_score(live: dict) -> dict:
    """Eye contact over the whole interview, longer answers counting more."""
    vs = [(t.get("answer") or {}).get("vision") or {} for t in live.get("turns", [])]
    vs = [v for v in vs if v.get("eye_contact_pct") is not None and v.get("seconds")]
    if not vs:
        return {"score": None}
    total = sum(v["seconds"] for v in vs)
    pct = round(sum(v["eye_contact_pct"] * v["seconds"] for v in vs) / total)
    return {"score": pct, "eye_contact_pct": pct, "look_aways": sum(v.get("away_count", 0) for v in vs),
            "face_missing_seconds": round(sum(v.get("face_missing_seconds", 0) for v in vs), 1)}


def _level(score: int) -> str:
    return next(name for limit, name in LEVELS if score >= limit)


# ------------------------------------------------------------------ report --
def grade(live: dict, use_gemini: bool = True) -> dict:
    """The full report for a finished live interview (stored as live["report"])."""
    items = answers_to_grade(live)
    gem = _gemini_grades(live, items) if (use_gemini and items) else None
    answers = []
    for it in items:
        g = (gem or {}).get("by_id", {}).get(it["turn_id"]) if gem else None
        answers.append({"turn_id": it["turn_id"]} | (_clean_grade(g, it) if g else _fallback_grade(it)))
    content = round(10 * sum(a["score"] for a in answers) / len(answers)) if answers else 0
    speaking, presence = speaking_score(live), presence_score(live)

    parts = {"content": content, "speaking": speaking["score"], "presence": presence["score"]}
    weights = {k: w for k, w in WEIGHTS.items() if parts[k] is not None}
    total_w = sum(weights.values())
    overall = round(sum(parts[k] * w for k, w in weights.items()) / total_w) if total_w else 0

    if gem:
        summary = str(gem["summary"])[:600]
        strengths = [str(x)[:200] for x in gem["strengths"]][:4]
        improvements = [str(x)[:200] for x in gem["improvements"]][:4]
    else:
        summary, strengths, improvements = _rule_summary(answers, speaking, presence, content)
    return {"status": "ready", "overall": overall, "level": _level(overall),
            "parts": parts, "weights": {k: round(w / total_w, 2) for k, w in weights.items()} if total_w else {},
            "speaking": speaking, "presence": presence, "answers": answers,
            "summary": summary, "strengths": strengths, "improvements": improvements,
            "graded_by": "gemini" if gem else "rules",
            "corrections": sum(len(a["corrections"]) for a in answers)}


def _rule_summary(answers, speaking, presence, content):
    strengths, improvements = [], []
    if content >= 70:
        strengths.append("Your answers covered most of the important points.")
    else:
        improvements.append("Cover more of the key points in each answer, with an example and a result.")
    if speaking.get("pace") == "good":
        strengths.append("You spoke at a clear, comfortable pace.")
    elif speaking.get("pace"):
        improvements.append(f"Your pace was {speaking['pace']} ({speaking['wpm']} words a minute); aim for 120-160.")
    if speaking.get("fillers_per_min", 0) > 3:
        improvements.append("Replace filler words (um, uh) with a short silent pause.")
    if presence.get("score") is not None:
        (strengths if presence["score"] >= 70 else improvements).append(
            "Good eye contact with the camera." if presence["score"] >= 70
            else "Look at the camera more while you speak.")
    summary = (f"You answered {len(answers)} questions. Detailed fact-checking was not available this time, "
               "so content was scored by how well your answers matched the key points.")
    return summary, strengths[:4], improvements[:4]
