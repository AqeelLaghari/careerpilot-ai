"""Interview report (Day 21): grading, scores, fallback, privacy. Gemini and SBERT are faked."""
import time

import numpy as np

from app.agents.interview_agent import InterviewAgent
from app.orchestrator.blackboard import Blackboard
from app.services import embeddings, privacy
from app.services import interview_grader as g


def _metrics(words, secs, fillers=0, pauses=0):
    return {"word_count": words, "speaking_seconds": secs, "filler_count": fillers, "habit_count": 0,
            "long_pauses": pauses}


def _live():
    agenda = [
        {"id": "opening", "type": "intro", "key_points": [], "skill": None, "status": "done"},
        {"id": "q3", "type": "technical", "skill": "Docker", "status": "done",
         "key_points": ["Containers share the host kernel", "Images are built from a Dockerfile"]},
    ]
    turns = [
        {"id": "t1", "kind": "question", "topic_id": "opening", "text": "Tell me about yourself?",
         "answer": {"transcript": "I am Aqeel Laghari, I worked at Acme Labs on cloud tools.",
                    "metrics": _metrics(60, 30), "vision": {"eye_contact_pct": 90, "seconds": 30}}},
        {"id": "t2", "kind": "question", "topic_id": "q3", "text": "What is Docker?",
         "answer": {"transcript": "", "metrics": _metrics(0, 0), "vision": None}},
        {"id": "t3", "kind": "repeat", "topic_id": "q3", "text": "Sorry, could you say that again?",
         "answer": {"transcript": "Docker is a virtual machine with its own kernel, built from a Dockerfile.",
                    "metrics": _metrics(70, 30, fillers=2), "vision": {"eye_contact_pct": 50, "seconds": 10}},
         "check": {"kind": "mistake", "note": "Containers do not have their own kernel."}},
        {"id": "t4", "kind": "candidate_questions", "topic_id": None, "text": "Any questions for me?",
         "answer": {"transcript": "No, thank you.", "metrics": _metrics(3, 2)}},
    ]
    return {"id": "L1", "mode": "live", "status": "completed", "role": "DevOps Engineer", "level": "entry",
            "agenda": agenda, "turns": turns,
            "private": privacy.terms({"name": "Aqeel Laghari", "location": "Karachi",
                                      "experience": [{"company": "Acme Labs"}]})}


def test_which_answers_are_graded():
    items = g.answers_to_grade(_live())
    # the empty answer that was asked again is skipped; "any questions for me" isn't graded
    assert [i["turn_id"] for i in items] == ["t1", "t3"]
    assert items[1]["key_points"][0].startswith("Containers") and items[1]["check"]["kind"] == "mistake"


def test_gemini_report_with_corrections_and_privacy(monkeypatch):
    seen = {}

    def fake(prompt, schema, tier, **k):
        seen["prompt"], seen["tier"] = prompt, tier
        return {"answers": [
            {"turn_id": "t1", "score": 7, "verdict": "no_facts", "corrections": [], "covered": ["Background"],
             "missing": ["A result"], "star": "", "misheard": "", "feedback": "Clear intro.",
             "better_answer": "I am a final-year student..."},
            {"turn_id": "t3", "score": 4, "verdict": "incorrect",
             "corrections": [{"said": "Docker is a virtual machine with its own kernel",
                              "correct": "Containers share the host kernel; they are not VMs."}],
             "covered": ["Dockerfile"], "missing": ["Shared kernel"], "star": "", "misheard": "",
             "feedback": "Check the container vs VM difference.", "better_answer": "Docker runs containers..."}],
            "summary": "A good start.", "strengths": ["Clear voice"], "improvements": ["Revise Docker basics"]}
    monkeypatch.setattr(g.llm, "generate_json", fake)
    r = g.grade(_live())
    assert seen["tier"] == "smart"
    p = seen["prompt"]
    assert "Aqeel" not in p and "Laghari" not in p and "Acme" not in p and "[name]" in p and "[company]" in p
    assert "Containers do not have their own kernel" in p                    # the interviewer's note
    assert r["graded_by"] == "gemini" and r["corrections"] == 1
    assert [a["score"] for a in r["answers"]] == [7, 4]
    assert r["answers"][1]["corrections"][0]["correct"].startswith("Containers share")
    assert r["parts"]["content"] == 55                                      # (7 + 4) / 2 * 10
    assert r["parts"]["presence"] == 80                                     # (90*30 + 50*10) / 40
    assert r["overall"] == round(0.6 * 55 + 0.2 * r["parts"]["speaking"] + 0.2 * 80)
    assert r["level"] in ("good", "fair") and r["summary"] == "A good start."


def test_fallback_without_gemini_uses_meaning(monkeypatch):
    monkeypatch.setattr(g.llm, "generate_json", lambda *a, **k: None)

    def fake_embed(texts):                      # answer close to the 2nd key point only
        rows = {0: [1, 0, 0], 1: [0, 1, 0], 2: [0.8, 0.6, 0]}
        return np.array([rows.get(i, [0, 0, 1]) for i in range(len(texts))], dtype="float32")
    monkeypatch.setattr(embeddings, "embed", fake_embed)
    r = g.grade(_live())
    assert r["graded_by"] == "rules" and all(a["graded_by"] == "rules" for a in r["answers"])
    t3 = r["answers"][1]
    assert t3["covered"] == ["Images are built from a Dockerfile"] and t3["missing"] == ["Containers share the host kernel"]
    assert t3["corrections"] == [] and "fact-checking was not available" in r["summary"]


def test_scores_without_camera_reweight(monkeypatch):
    live = _live()
    for t in live["turns"]:
        if t.get("answer"):
            t["answer"]["vision"] = None
    monkeypatch.setattr(embeddings, "embed", lambda texts: np.ones((len(texts), 3), dtype="float32") / 3 ** 0.5)
    r = g.grade(live, use_gemini=False)
    assert r["parts"]["presence"] is None and r["weights"] == {"content": 0.75, "speaking": 0.25}
    s = g.speaking_score(live)
    assert s["wpm"] == round(133 / (62 / 60)) and 0 <= s["score"] <= 100


def test_interview_without_answers_is_not_scored_zero():
    live = _live()
    live["turns"] = live["turns"][:1]
    live["turns"][0]["answer"] = None
    r = g.grade(live)
    assert r["empty"] and r["overall"] is None and r["answers"] == []


def test_speaking_score_penalises_fillers():
    calm = {"turns": [{"answer": {"metrics": _metrics(140, 60)}}]}
    filler = {"turns": [{"answer": {"metrics": _metrics(140, 60, fillers=12, pauses=4)}}]}
    assert g.speaking_score(calm)["score"] == 100
    assert g.speaking_score(filler)["score"] < 60


def test_privacy_scrub():
    terms = privacy.terms({"name": "Aqeel Laghari", "location": "Karachi, Pakistan",
                           "experience": [{"company": "Acme Labs"}, {"company": None}]})
    text = "I'm aqeel, mail me at a.b@x.com or +92 300 1234567. I was at Acme Labs in Karachi."
    out = privacy.scrub(text, terms)
    assert out == "I'm [name], mail me at [email] or [phone]. I was at [company] in [place]."


def test_agent_grades_and_keeps_the_report(monkeypatch):
    bb = Blackboard(db=None)
    agent = InterviewAgent(bb)
    live = _live()
    bb.write("u1", "interviews", {"sessions": [live], "asked": []}, agent="test")
    assert agent.needs_report(agent.session("u1", "L1"))
    monkeypatch.setattr(g, "grade", lambda live, use_gemini=True: {"status": "ready", "overall": 70})
    agent.grade_live("u1", "L1")
    stored = agent.session("u1", "L1")
    assert stored["report"]["overall"] == 70 and not agent.needs_report(stored)
    agent.save_live("u1", dict(live))                           # a late save doesn't drop the report
    assert agent.session("u1", "L1")["report"]["overall"] == 70


def test_interrupted_grading_is_restarted():
    agent = InterviewAgent(Blackboard(db=None))
    live = _live() | {"report": {"status": "grading", "started_at": time.time() - 5}}
    assert not agent.needs_report(live)                         # just started: wait
    live["report"]["started_at"] = time.time() - 120
    assert agent.needs_report(live)                             # nobody is working on it (restart)
