"""The live interviewer's brain (Day 20): what to say next in a real, spoken interview.

The interview follows an AGENDA made from the user's CV (Day 15 plan), in the order a real
interviewer uses:
    opening      greeting + "tell me about yourself: who you are, your studies, your experience"
    background   follow-up on studies / experience, based on what they said
    project      their own project or job from the CV
    technical    skills the role needs that they have
    gap          a skill the role needs that they lack (fair, rewards honesty)
    behavioural  teamwork, mistakes, deadlines (STAR)
    situational  an on-the-job scenario
    closing      "do you have any questions for me?" then a professional goodbye

After every answer Gemini (fast tier, short time budget) reads the conversation and decides:
follow up on this answer, move to the next topic, or wrap up, and writes a short natural
reaction + the next question. RULES always win over Gemini:
  - at most MAX_FOLLOW_UPS follow-ups per topic; no follow-up when time is short
  - wrap up when the time is nearly used or every topic is covered
  - an empty answer is asked again once ("Sorry, I didn't catch that"), then we move on
If Gemini is slow or down, the planned question for the next topic is used, so the
interview never stops.
"""
import random
import time

from pydantic import BaseModel

from app.services import llm

MAX_FOLLOW_UPS = 2
WRAP_UP_SECONDS = 75          # less time left than this: start closing
FOLLOW_UP_MIN_SECONDS = 120   # no follow-ups when less time than this is left
GEMINI_BUDGET = 6             # seconds; the user is waiting
TOPICS_FOR = {5: 4, 10: 7, 15: 10}      # agenda size (plus opening/background) per interview length

REACTIONS = ["Thank you.", "Okay, thanks for that.", "Alright.", "Got it, thank you.", "I see, thanks.",
             "That's helpful, thank you.", "Okay."]


def opening_text(role: str) -> str:
    return (f"Hello, and thank you for joining. I'll be your interviewer today for the {role} position. "
            "This will feel like a normal conversation, so just answer naturally. "
            "To start, could you tell me a little about yourself: who you are, where you're studying "
            "or studied, and what experience you have so far?")


BACKGROUND_QUESTION = ("Could you tell me a bit more about your studies and any work, internship or project "
                       "experience? What did you enjoy most, and what did you learn from it?")
CANDIDATE_QUESTIONS = "We're almost at the end. Before we finish, do you have any questions for me?"
GOODBYE = ("Thank you very much for your time today. It was good talking to you. "
           "That's the end of the interview; your feedback report is being prepared now.")
REPEAT = "Sorry, I didn't quite catch that. Could you say that again?"


# ---------------------------------------------------------------- agenda --
def build_agenda(questions: list[dict], minutes: int) -> list[dict]:
    """Topics in interview order from the planned questions (Day 15)."""
    n = TOPICS_FOR.get(minutes, 7)
    body = [q for q in questions if q["type"] != "intro"][:n]
    agenda = [{"id": "opening", "type": "intro", "question": None, "key_points": [], "skill": None, "project": None},
              {"id": "background", "type": "background", "question": BACKGROUND_QUESTION, "skill": None, "project": None,
               "key_points": ["Clear summary of studies (degree, where, what stood out)",
                              "Relevant work, internship or project experience",
                              "What they learned and why it matters for the role"]}]
    agenda += [{k: q.get(k) for k in ("id", "type", "question", "key_points", "skill", "project")} for q in body]
    for t in agenda:
        t.update(status="pending", follow_ups=0)
    return agenda


def remaining_seconds(live: dict, now: float | None = None) -> float:
    started = live.get("started_at") or (now or time.time())
    return live["minutes"] * 60 - ((now or time.time()) - started)


def _pending(live: dict) -> list[dict]:
    return [t for t in live["agenda"] if t["status"] == "pending"]


def _current(live: dict) -> dict | None:
    return next((t for t in live["agenda"] if t["status"] == "current"), None)


# ---------------------------------------------------------------- Gemini --
class _Next(BaseModel):
    action: str          # follow_up | next_topic | wrap_up
    reaction: str        # short natural reaction to the answer
    question: str        # what to ask now
    topic_id: str


def _history(live: dict, limit: int = 8) -> str:
    lines = []
    for turn in live["turns"][-limit:]:
        lines.append(f"Interviewer: {turn['text']}")
        ans = (turn.get("answer") or {}).get("transcript")
        if ans is not None:
            lines.append(f"Candidate: {ans[:700] or '(said nothing)'}")
    return "\n".join(lines)


def _prompt(live: dict, remaining: float) -> str:
    cur = _current(live)
    topics = "\n".join(
        f"- {t['id']} [{t['status']}] {t['type']}"
        + (f" (skill: {t['skill']})" if t.get("skill") else "")
        + (f" (their work: {t['project']})" if t.get("project") else "")
        + (f": planned question: {t['question']}" if t.get("question") else "")
        for t in live["agenda"])
    return (
        f"You are a warm, professional human interviewer running a live spoken interview for a "
        f"{live['role']} position ({live['level']} level). About {max(0, int(remaining // 60))} min "
        f"{int(remaining % 60)} s are left.\n"
        "Decide what to say next, based on the candidate's LAST answer:\n"
        "- follow_up: dig into something specific they just said (a vague claim, an interesting detail, "
        "a missing result or example). Stay on the same topic. "
        f"(Follow-ups used on this topic: {cur['follow_ups'] if cur else 0} of {MAX_FOLLOW_UPS}.)\n"
        "- next_topic: move to the next pending topic in the list. Rephrase its planned question naturally, "
        "and link it to what they said when it fits.\n"
        "- wrap_up: only when time is nearly over.\n"
        "Write `reaction`: a short natural reaction to their answer (max 12 words, polite and neutral; never "
        "grade or praise heavily; do not repeat their words back at length). Write `question`: ONE clear "
        "spoken question, max 2 sentences, no lists, no code. Use plain English.\n"
        "Give `topic_id` of the topic the question belongs to.\n"
        f"TOPICS (in order):\n{topics}\n"
        f"CONVERSATION SO FAR:\n{_history(live)}")


def _ask_gemini(live: dict, remaining: float) -> dict | None:
    return llm.generate_json(_prompt(live, remaining), _Next, tier="fast", temperature=0.6, timeout=GEMINI_BUDGET)


# --------------------------------------------------------------- decide --
def decide(live: dict, now: float | None = None, use_gemini: bool = True) -> dict:
    """The next thing the interviewer says: {kind, text, topic_id, source}.
    kind: question | follow_up | repeat | candidate_questions | goodbye.
    Also updates the agenda statuses in `live`."""
    remaining = remaining_seconds(live, now)
    cur = _current(live)
    last = live["turns"][-1] if live["turns"] else None
    answer = ((last or {}).get("answer") or {}).get("transcript", "") or ""

    # the closing sequence: candidate questions -> goodbye
    if last and last["kind"] == "candidate_questions":
        return _goodbye(live, answer)
    if last and last["kind"] == "goodbye":
        return {"kind": "end", "text": "", "topic_id": None, "source": "rules"}

    # nothing heard: ask once more, then move on
    if len(answer.split()) < 3 and last and last["kind"] != "repeat":
        return {"kind": "repeat", "text": REPEAT, "topic_id": last.get("topic_id"), "source": "rules"}

    pending = _pending(live)
    if remaining < WRAP_UP_SECONDS or (not pending and (cur is None or cur["follow_ups"] >= MAX_FOLLOW_UPS)):
        return _wrap_up(live)

    out = _ask_gemini(live, remaining) if use_gemini else None
    can_follow = cur is not None and cur["follow_ups"] < MAX_FOLLOW_UPS and remaining > FOLLOW_UP_MIN_SECONDS \
        and len(answer.split()) >= 3
    if out and out.get("action") == "follow_up" and can_follow and out.get("question", "").strip():
        cur["follow_ups"] += 1
        return {"kind": "follow_up", "text": _join(out.get("reaction"), out["question"]),
                "topic_id": cur["id"], "source": "gemini"}
    if not pending:
        return _wrap_up(live)
    # next topic: Gemini's choice if it is a pending topic, else the next one in order
    nxt = next((t for t in pending if out and t["id"] == out.get("topic_id")), pending[0])
    _set_current(live, nxt)
    if out and out.get("action") == "next_topic" and out.get("question", "").strip() and out.get("topic_id") == nxt["id"]:
        return {"kind": "question", "text": _join(out.get("reaction"), out["question"]), "topic_id": nxt["id"],
                "source": "gemini"}
    reaction = (out or {}).get("reaction") or random.choice(REACTIONS)
    return {"kind": "question", "text": _join(reaction, nxt["question"] or BACKGROUND_QUESTION),
            "topic_id": nxt["id"], "source": "gemini+plan" if out else "plan"}


def start(live: dict) -> dict:
    """The first thing the interviewer says."""
    _set_current(live, live["agenda"][0])
    return {"kind": "question", "text": opening_text(live["role"]), "topic_id": "opening", "source": "rules"}


def _set_current(live: dict, topic: dict):
    for t in live["agenda"]:
        if t["status"] == "current":
            t["status"] = "done"
    topic["status"] = "current"


def _wrap_up(live: dict) -> dict:
    cur = _current(live)
    if cur:
        cur["status"] = "done"
    return {"kind": "candidate_questions", "text": _join(random.choice(REACTIONS), CANDIDATE_QUESTIONS),
            "topic_id": None, "source": "rules"}


class _Reply(BaseModel):
    reply: str


def _goodbye(live: dict, answer: str) -> dict:
    """Answer the candidate's question briefly (Gemini), then say goodbye."""
    reply = ""
    if len(answer.split()) >= 4 and not any(w in answer.lower() for w in ("no question", "no, thank", "nothing")):
        out = llm.generate_json(
            f"You are a friendly interviewer for a {live['role']} position at a typical company. At the end of "
            f"the interview the candidate asked: \"{answer[:500]}\". Reply in at most 2 short spoken sentences, "
            "honest and general (you don't know this company's private details; say the team will share "
            "specifics in the next round if needed).", _Reply, tier="fast", temperature=0.5, timeout=GEMINI_BUDGET)
        reply = (out or {}).get("reply", "").strip() or "That's a good question; the team will share the details in the next round."
    return {"kind": "goodbye", "text": _join(reply, GOODBYE), "topic_id": None, "source": "gemini" if reply else "rules"}


def _join(*parts) -> str:
    return " ".join(str(p).strip() for p in parts if p and str(p).strip())
