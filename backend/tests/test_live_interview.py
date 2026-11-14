"""Live interview (Day 20): interviewer brain rules + the conversation over the WebSocket.
Gemini and Whisper are faked; no network."""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orchestrator.blackboard import Blackboard
from app.routers import interview, live_interview
from app.services import interviewer as iv
from app.services import speech

QUESTIONS = [
    {"id": "q1", "type": "intro", "question": "Tell me about yourself?", "key_points": ["a"], "skill": None, "project": None},
    {"id": "q2", "type": "project", "question": "Walk me through your shop pipeline?", "key_points": ["a"], "skill": None,
     "project": "Shop pipeline"},
    {"id": "q3", "type": "technical", "question": "How do you debug a Kubernetes pod?", "key_points": ["a"],
     "skill": "Kubernetes", "project": None},
    {"id": "q4", "type": "behavioural", "question": "Tell me about a disagreement?", "key_points": ["a"], "skill": None,
     "project": None},
]


def _live(minutes=10):
    return {"id": "L1", "role": "DevOps Engineer", "level": "mid", "minutes": minutes, "started_at": time.time(),
            "agenda": iv.build_agenda(QUESTIONS, minutes), "turns": []}


def _answer(live, text):
    live["turns"][-1]["answer"] = {"transcript": text}


def _say(live, nxt):
    live["turns"].append({"id": f"t{len(live['turns']) + 1}", "kind": nxt["kind"], "text": nxt["text"],
                          "topic_id": nxt["topic_id"]})


def test_interview_order_opening_background_then_topics(monkeypatch):
    monkeypatch.setattr(iv.llm, "generate_json", lambda *a, **k: None)          # no Gemini: the plan
    live = _live()
    assert [t["id"] for t in live["agenda"]][:3] == ["opening", "background", "q2"]
    first = iv.start(live)
    assert "tell me a little about yourself" in first["text"] and "studying" in first["text"]
    _say(live, first)
    _answer(live, "I am a final year software engineering student and I built a CI pipeline")
    nxt = iv.decide(live)
    assert nxt["topic_id"] == "background" and nxt["source"] == "plan"
    _say(live, nxt)
    _answer(live, "I studied software engineering and did an internship in cloud")
    assert iv.decide(live)["topic_id"] == "q2"


def test_gemini_follow_ups_are_limited(monkeypatch):
    calls = []

    def fake(prompt, schema, **k):
        calls.append(prompt)
        return {"action": "follow_up", "reaction": "Interesting.", "question": "What did you automate?",
                "topic_id": "opening"}
    monkeypatch.setattr(iv.llm, "generate_json", fake)
    live = _live()
    _say(live, iv.start(live))
    kinds = []
    for _ in range(4):
        _answer(live, "I built a pipeline with Docker and GitHub Actions for my project")
        nxt = iv.decide(live)
        kinds.append(nxt["kind"])
        _say(live, nxt)
    assert kinds == ["follow_up", "follow_up", "question", "follow_up"]   # max 2 per topic, then move on
    assert "Interesting. What did you automate?" == live["turns"][1]["text"]
    assert "Candidate: I built a pipeline" in calls[0] and "DevOps Engineer" in calls[0]


def test_empty_answer_is_asked_again_once(monkeypatch):
    monkeypatch.setattr(iv.llm, "generate_json", lambda *a, **k: None)
    live = _live()
    _say(live, iv.start(live))
    _answer(live, "")
    nxt = iv.decide(live)
    assert nxt["kind"] == "repeat"
    _say(live, nxt)
    _answer(live, "")
    assert iv.decide(live)["kind"] == "question"                            # then move on


def test_wrap_up_when_time_is_nearly_over_then_goodbye(monkeypatch):
    monkeypatch.setattr(iv.llm, "generate_json", lambda *a, **k: {"reply": "We use Kubernetes daily."})
    live = _live(5)
    live["started_at"] = time.time() - 5 * 60 + 30                          # 30 s left
    _say(live, iv.start(live))
    _answer(live, "I am a student who loves cloud computing and automation")
    nxt = iv.decide(live)
    assert nxt["kind"] == "candidate_questions" and "questions for me" in nxt["text"]
    _say(live, nxt)
    _answer(live, "What tools does your team use every day?")
    bye = iv.decide(live)
    assert bye["kind"] == "goodbye" and bye["text"].startswith("We use Kubernetes daily.")
    _say(live, bye)
    assert iv.decide(live)["kind"] == "end"


def test_mistake_is_probed_never_called_wrong(monkeypatch):
    def fake(prompt, schema, **k):
        return {"check": "mistake", "note": "Docker containers are not virtual machines.",
                "action": "follow_up", "reaction": "Hmm, that's not quite right.",
                "question": "That's wrong. How is a container different from a virtual machine?",
                "topic_id": "opening"}
    monkeypatch.setattr(iv.llm, "generate_json", fake)
    live = _live()
    _say(live, iv.start(live))
    _answer(live, "Docker is basically a virtual machine that I used for my project")
    nxt = iv.decide(live)
    assert nxt["kind"] == "follow_up"
    assert nxt["text"].endswith("How is a container different from a virtual machine?")
    assert "wrong" not in nxt["text"].lower() and "not quite" not in nxt["text"].lower()
    assert nxt["check"] == "mistake" and "virtual machines" in nxt["note"]


def test_prompt_asks_for_gentle_probing():
    live = _live()
    iv.start(live)
    p = iv._prompt(live, 300)
    assert "Are you sure about that?" in p and "NEVER say" in p and "misheard" in p


def test_normal_interview_questions_are_not_filtered():
    for q in ["Tell me about a mistake you made and what went wrong?", "What exactly did you do?",
              "Can you walk me through that step again?", "Are you sure about that?"]:
        assert iv._clean_question(q) == q
    assert iv._clean_question("That is incorrect.") == ""
    assert iv._clean_question("Good answer. What did you learn from it?") == "What did you learn from it?"
    assert iv._clean_reaction("Exactly, great!") in iv.REACTIONS
    assert iv._clean_reaction("I see, thank you.") == "I see, thank you."


def test_agenda_size_follows_the_length():
    many = QUESTIONS + [dict(QUESTIONS[2], id=f"x{i}") for i in range(12)]
    assert len(iv.build_agenda(many, 5)) == 2 + iv.TOPICS_FOR[5]
    assert len(iv.build_agenda(many, 15)) == 2 + iv.TOPICS_FOR[15]


# ------------------------------------------------------------ the conversation --
@pytest.fixture
def live_env(monkeypatch, tmp_path):
    from app.services import audio_store
    bb = Blackboard(db=None)
    monkeypatch.setattr(interview.agent, "bb", bb)
    monkeypatch.setattr(live_interview, "uid_from_token", lambda t: "u1" if t == "good" else None)
    monkeypatch.setattr(audio_store, "ROOT", tmp_path / "interviews")
    monkeypatch.setattr(iv.llm, "generate_json", lambda *a, **k: None)
    said = iter(["I am a final year student who built a pipeline with Docker",
                 "I studied software engineering and did a cloud internship last summer",
                 "No questions, thank you"] + ["I would check the logs and the pod events first"] * 20)

    def fake_process(path, role=None, terms=None, fast=False):
        assert fast
        text = next(said)
        words = [{"w": w, "start": i * 0.4, "end": i * 0.4 + 0.3} for i, w in enumerate(text.split())]
        return {"transcript": text, "words": words, "metrics": speech.analyse(words, 5), "model": "fake",
                "seconds_taken": 0.1}
    monkeypatch.setattr(speech, "process", fake_process)
    session = {"id": "L1", "created_at": time.time(), "role": "DevOps Engineer", "level": "mid", "status": "ready",
               "source": "template", "questions": QUESTIONS, "mode": "live", "minutes": 10,
               "agenda": iv.build_agenda(QUESTIONS, 10), "turns": [], "started_at": None}
    bb.write("u1", "interviews", {"sessions": [session], "asked": []}, agent="test")
    return bb


def _answer_turn(ws, turn_id, seconds=3):
    ws.send_json({"type": "listening", "turn_id": turn_id})
    ws.send_bytes(b"\x01\x00" * 16000 * seconds)
    ws.send_json({"type": "vision", "fps": 5, "codes": "S" * 5 * seconds})
    ws.send_json({"type": "answered", "turn_id": turn_id})
    assert ws.receive_json()["type"] == "thinking"
    return ws.receive_json()


def test_live_conversation_over_websocket(live_env):
    bb = live_env
    with TestClient(app).websocket_connect("/interview/live/ws") as ws:
        ws.send_json({"type": "auth", "token": "good", "session_id": "L1"})
        assert ws.receive_json()["type"] == "ready"
        first = ws.receive_json()
        assert first["type"] == "say" and first["turn_id"] == "t1" and "about yourself" in first["text"]
        second = _answer_turn(ws, "t1")
        assert second["type"] == "say" and second["turn_id"] == "t2"
        third = _answer_turn(ws, "t2")
        assert third["turn_id"] == "t3"
        ws.send_json({"type": "end"})
        assert ws.receive_json()["type"] == "ended"
    live = bb.read_section("u1", "interviews")["sessions"][0]
    assert live["status"] == "completed" and len(live["turns"]) == 3
    a1 = live["turns"][0]["answer"]
    assert a1["transcript"].startswith("I am a final year") and a1["vision"]["eye_contact_pct"] == 100
    assert a1["duration_sec"] == 3.0 and a1["metrics"]["word_count"] > 5


def test_answer_check_is_saved_for_the_report(live_env, monkeypatch):
    bb = live_env
    monkeypatch.setattr(iv.llm, "generate_json", lambda *a, **k: {
        "check": "vague", "note": "No result or numbers given.", "action": "follow_up", "reaction": "Okay.",
        "question": "What was the result of that pipeline?", "topic_id": "opening"})
    with TestClient(app).websocket_connect("/interview/live/ws") as ws:
        ws.send_json({"type": "auth", "token": "good", "session_id": "L1"})
        ws.receive_json()
        ws.receive_json()
        nxt = _answer_turn(ws, "t1")
        assert nxt["text"] == "Okay. What was the result of that pipeline?"
        ws.send_json({"type": "end"})
        ws.receive_json()
    turns = bb.read_section("u1", "interviews")["sessions"][0]["turns"]
    assert turns[0]["check"] == {"kind": "vague", "note": "No result or numbers given."}
    assert "check" not in turns[1]


def test_end_then_leave_at_once_still_saves(live_env):
    bb = live_env
    with TestClient(app).websocket_connect("/interview/live/ws") as ws:
        ws.send_json({"type": "auth", "token": "good", "session_id": "L1"})
        ws.receive_json()
        ws.receive_json()
        _answer_turn(ws, "t1")
        ws.send_json({"type": "end"})                 # the app leaves without reading "ended"
    for _ in range(50):
        if bb.read_section("u1", "interviews")["sessions"][0]["status"] == "completed":
            break
        time.sleep(0.05)
    live = bb.read_section("u1", "interviews")["sessions"][0]
    assert live["status"] == "completed" and live["turns"][0]["answer"]["transcript"]


def test_live_needs_login_and_a_live_session(live_env):
    with TestClient(app).websocket_connect("/interview/live/ws") as ws:
        ws.send_json({"type": "auth", "token": "bad", "session_id": "L1"})
        assert ws.receive_json()["code"] == "auth"
    with TestClient(app).websocket_connect("/interview/live/ws") as ws:
        ws.send_json({"type": "auth", "token": "good", "session_id": "nope"})
        assert ws.receive_json()["code"] == "session"


def test_create_live_session_endpoint(monkeypatch):
    from app.auth import current_uid
    bb = Blackboard(db=None)
    monkeypatch.setattr(interview.agent, "bb", bb)
    app.dependency_overrides[current_uid] = lambda: "u1"
    try:
        c = TestClient(app)
        assert c.post("/interview/live", json={"minutes": 10}).status_code == 404       # no resume
        bb.write("u1", "resume", {"entities": {"skills": [{"name": "Docker", "category": "devops", "mentions": 3}],
                                               "projects": [], "experience": []}}, agent="test")
        bb.write("u1", "career", {"target_role": "DevOps Engineer"}, agent="test")
        assert c.post("/interview/live", json={"minutes": 7}).status_code == 422
        r = c.post("/interview/live", json={"minutes": 5}).json()
        assert r["minutes"] == 5 and r["status"] == "ready"
        stored = bb.read_section("u1", "interviews")["sessions"][-1]
        assert stored["mode"] == "live" and stored["agenda"][0]["id"] == "opening"
    finally:
        app.dependency_overrides.clear()


def test_pause_prepares_the_next_question_early(live_env):
    bb = live_env
    with TestClient(app).websocket_connect("/interview/live/ws") as ws:
        ws.send_json({"type": "auth", "token": "good", "session_id": "L1"})
        ws.receive_json()
        ws.receive_json()                                           # opening question
        ws.send_json({"type": "listening", "turn_id": "t1"})
        ws.send_bytes(b"\x01\x00" * 16000 * 3)
        ws.send_json({"type": "pause"})                             # quiet: start early
        ws.send_bytes(b"\x00\x00" * 16000 * 2)                     # 2 more seconds of silence
        ws.send_json({"type": "answered", "turn_id": "t1", "spoke_since_pause": False})
        assert ws.receive_json()["type"] == "thinking"
        nxt = ws.receive_json()
        assert nxt["type"] == "say" and nxt["turn_id"] == "t2"
        ws.send_json({"type": "end"})
        ws.receive_json()
    live = bb.read_section("u1", "interviews")["sessions"][0]
    a = live["turns"][0]["answer"]
    assert a["duration_sec"] == 5.0 and a["transcript"].startswith("I am a final year")   # the early transcript
    assert [t["status"] for t in live["agenda"][:2]] == ["done", "done"]   # agenda taken from the early run
