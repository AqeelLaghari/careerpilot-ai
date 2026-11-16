"""Urdu interviews (Day 27): speech metrics, the interviewer in Urdu (3 forms: Urdu script for an
Urdu voice, Roman Urdu subtitles, Devanagari for a Hindi voice), the report in Roman Urdu, and the
WebSocket. Gemini and Whisper are faked; no network."""
import time

from fastapi.testclient import TestClient

from app.auth import current_uid
from app.main import app
from app.services import interview_grader as grader
from app.services import interviewer as iv
from app.services import speech
from tests.test_live_interview import QUESTIONS, _answer, _answer_turn, _say, live_env  # noqa: F401


def _words(text, gap=0.4):
    return [{"w": w, "start": round(i * gap, 2), "end": round(i * gap + 0.3, 2)} for i, w in enumerate(text.split())]


def _live(minutes=10):
    return {"id": "L1", "role": "DevOps Engineer", "level": "mid", "minutes": minutes, "started_at": time.time(),
            "agenda": iv.build_agenda(QUESTIONS, minutes), "turns": [], "language": "ur",
            "candidate": {"first_name": "Aqeel", "university": "NED University", "subject": "Software Engineering",
                          "studying": True}}


URDU_NEXT = {"check": "vague", "note": "No result given.", "action": "follow_up",
             "reaction": "ٹھیک ہے۔", "reaction_roman": "Theek hai.", "reaction_hindi": "ठीक है।",
             "question": "اس پروجیکٹ کا نتیجہ کیا نکلا؟", "question_roman": "Is project ka nateeja kya nikla?",
             "question_hindi": "इस प्रोजेक्ट का नतीजा क्या निकला?", "topic_id": "opening"}


# ------------------------------------------------------------------ speech --
def test_urdu_fillers_habits_and_roman_tips():
    text = "ام میں نے مطلب ایک ویب ایپ بنائی امم یعنی Python میں مطلب API بنائی ام اور ٹیسٹنگ کی"
    m = speech.analyse(_words(text), 10, language="ur")
    assert m["fillers"] == {"ام": 3}                      # "امم" counted as "ام"
    assert m["habits"]["مطلب"] == 2 and m["habits"]["یعنی"] == 1
    assert m["word_count"] == len(text.split()) - 3
    assert any("dafa" in t for t in m["tips"])           # Roman Urdu tips
    assert speech.analyse([], 3, language="ur")["tips"][0].startswith("Koi awaaz")


def test_urdu_pace_range_and_model():
    # 170 words a minute: "good" in Urdu (many short words such as ka, ki, hai), "a bit fast" in English
    assert speech._pace(170, "ur")[0] == "good" and speech._pace(170)[0] == "a bit fast"
    assert speech.model_size("ur") == speech.config.WHISPER_MODEL_URDU and speech.model_size("en") == "base"
    assert speech._norm("مطلب،") == "مطلب" and speech._norm("Um,") == "um"
    p = speech.make_prompt("Data Analyst", ["SQL", "Power BI"], language="ur")
    assert "مطلب" in p and "Data Analyst" in p and "SQL, Power BI" in p


# ------------------------------------------------------------- interviewer --
def test_urdu_opening_in_three_forms_greets_by_name():
    first = iv.start(_live())
    assert first["text"].startswith("السلام علیکم Aqeel") and "DevOps Engineer" in first["text"]
    assert first["roman"].startswith("Assalam o Alaikum Aqeel") and "NED University" in first["roman"]
    assert "अस्सलाम" in first["hindi"] and first["roman"].endswith("?")
    for who in ({}, {"university": "IBA", "studying": None}, {"university": "IBA", "studying": False}):
        text, roman, hindi = iv._urdu_opening("Data Analyst", who)
        assert text and hindi and roman.endswith("?")


def test_urdu_follow_up_from_gemini(monkeypatch):
    live = _live()
    _say(live, iv.start(live))
    _answer(live, "میں نے ایک پائپ لائن بنائی تھی Docker کے ساتھ")
    calls = []
    monkeypatch.setattr(iv.llm, "generate_json", lambda prompt, model, **k: calls.append((prompt, model)) or URDU_NEXT)
    nxt = iv.decide(live)
    assert nxt["kind"] == "follow_up" and nxt["check"] == "vague"
    assert nxt["text"] == "ٹھیک ہے۔ اس پروجیکٹ کا نتیجہ کیا نکلا؟"
    assert nxt["roman"] == "Theek hai. Is project ka nateeja kya nikla?" and nxt["hindi"].startswith("ठीक है।")
    assert "URDU" in calls[0][0] and calls[0][1] is iv._NextUrdu


def test_urdu_verdict_is_never_spoken(monkeypatch):
    live = _live()
    live["agenda"][2]["urdu"] = {"text": "پائپ لائن کے بارے میں بتائیں؟", "roman": "Pipeline ke baare mein batayein?",
                                 "hindi": "पाइपलाइन के बारे में बताइए?"}
    _say(live, iv.start(live))
    _answer(live, "میں نے ایک پائپ لائن بنائی تھی Docker کے ساتھ")
    judged = URDU_NEXT | {"reaction_roman": "Zabardast!", "question_roman": "Yeh ghalat hai, kya aap dobara sochein?",
                          "action": "next_topic", "topic_id": "background"}
    monkeypatch.setattr(iv.llm, "generate_json", lambda *a, **k: judged)
    nxt = iv.decide(live)
    assert "ghalat" not in nxt["roman"].lower() and "Zabardast" not in nxt["roman"]
    assert nxt["roman"].endswith(iv.URDU["background"][1])          # the planned Urdu question instead
    assert any(nxt["roman"].startswith(r[1]) for r in iv.URDU_REACTIONS)


def test_urdu_plan_fallback_translation_or_english(monkeypatch):
    monkeypatch.setattr(iv.llm, "generate_json", lambda *a, **k: None)
    live = _live()
    live["agenda"][2]["urdu"] = {"text": "پائپ لائن؟", "roman": "Pipeline ke baare mein batayein?", "hindi": "पाइपलाइन?"}
    _say(live, iv.start(live))
    _answer(live, "میں فائنل ایئر کا طالب علم ہوں اور میں نے پروجیکٹ بنایا")
    second = iv.decide(live)                                             # background: fixed Urdu question
    assert second["roman"].endswith(iv.URDU["background"][1])
    _say(live, second)
    _answer(live, "میں نے کلاؤڈ میں انٹرن شپ کی اور بہت کچھ سیکھا")
    third = iv.decide(live)
    assert third["roman"].endswith("Pipeline ke baare mein batayein?")   # translated when created
    _say(live, third)
    _answer(live, "ہم نے Jenkins اور Docker استعمال کیا تھا")
    fourth = iv.decide(live)
    assert fourth["roman"].endswith("How do you debug a Kubernetes pod?")  # not translated: English


def test_urdu_repeat_wrap_up_and_goodbye(monkeypatch):
    monkeypatch.setattr(iv.llm, "generate_json", lambda *a, **k: None)
    live = _live()
    _say(live, iv.start(live))
    _answer(live, "")
    assert iv.decide(live)["roman"] == iv.URDU["repeat"][1]
    live["started_at"] = time.time() - live["minutes"] * 60 + 30            # 30 s left
    _answer(live, "میں نے ایک ویب ایپ بنائی تھی")
    live["turns"][-1]["kind"] = "repeat"
    wrap = iv.decide(live)
    assert wrap["kind"] == "candidate_questions" and wrap["roman"].endswith(iv.URDU["candidate_questions"][1])
    _say(live, wrap)
    _answer(live, "نہیں شکریہ، کوئی سوال نہیں ہے")
    bye = iv.decide(live)
    assert bye["kind"] == "goodbye" and bye["roman"] == iv.URDU["goodbye"][1] and bye["hindi"]


def test_translate_agenda_keeps_only_clean_translations(monkeypatch):
    live = _live()
    seen = []

    def fake(prompt, model, **k):
        seen.append(prompt)
        return {"questions": [
            {"id": "q2", "text": "شاپ پائپ لائن کے بارے میں بتائیں؟", "roman": "Shop pipeline ke baare mein batayein?",
             "hindi": "शॉप पाइपलाइन के बारे में बताइए?"},
            {"id": "q3", "text": "[company] میں", "roman": "[company] mein", "hindi": "[company] में"}]}
    monkeypatch.setattr(iv.llm, "generate_json", fake)
    iv.translate_agenda(live)
    topics = {t["id"]: t for t in live["agenda"]}
    assert topics["q2"]["urdu"]["roman"] == "Shop pipeline ke baare mein batayein?"
    assert "urdu" not in topics["q3"] and "urdu" not in topics["background"]
    assert "Walk me through your shop pipeline?" in seen[0]


# ------------------------------------------------------------------ report --
def test_urdu_report_without_gemini_is_roman_urdu():
    live = _live()
    _say(live, iv.start(live))
    live["turns"][-1]["answer"] = {"transcript": " ".join(["لفظ"] * 40),
                                   "metrics": speech.analyse(_words(" ".join(["لفظ"] * 40)), 20, "ur")}
    rep = grader.grade(live, use_gemini=False)
    assert rep["graded_by"] == "rules" and rep["summary"].startswith("Aap ne 1 sawalon")
    assert rep["answers"][0]["feedback"].startswith("Jawab mein") and 1 <= rep["answers"][0]["score"] <= 10
    assert rep["speaking"]["pace"] in {"too slow", "a bit slow", "good", "a bit fast", "too fast"}
    assert "Koi" not in rep["summary"]
    empty = grader.grade(_live(), use_gemini=False)
    assert empty["summary"].startswith("Is interview mein")


def test_urdu_report_prompt_asks_for_roman_urdu():
    live = _live()
    items = [{"turn_id": "t1", "question": "سوال؟", "answer": "جواب", "kind": "question", "type": "intro",
              "key_points": [], "skill": None, "check": None}]
    assert "Roman Urdu" in grader._prompt(live, items)
    assert "Plain English" in grader._prompt(live | {"language": "en"}, items)


# ----------------------------------------------------------------- websocket --
def test_urdu_say_messages_carry_subtitles(live_env):  # noqa: F811 (the fixture)
    bb = live_env
    state = bb.read_section("u1", "interviews")
    state["sessions"][0]["language"] = "ur"
    bb.write("u1", "interviews", state, agent="test")
    with TestClient(app).websocket_connect("/interview/live/ws") as ws:
        ws.send_json({"type": "auth", "token": "good", "session_id": "L1"})
        assert ws.receive_json()["language"] == "ur"
        first = ws.receive_json()
        assert first["text"].startswith("السلام علیکم") and first["roman"].startswith("Assalam") and first["hindi"]
        second = _answer_turn(ws, "t1")
        assert second["roman"].endswith(iv.URDU["background"][1])
        ws.send_json({"type": "end"})
        ws.receive_json()
    turns = bb.read_section("u1", "interviews")["sessions"][0]["turns"]
    assert turns[0]["roman"].startswith("Assalam") and turns[1]["hindi"].endswith(iv.URDU["background"][2])


def test_language_is_checked():
    app.dependency_overrides[current_uid] = lambda: "u1"
    try:
        r = TestClient(app).post("/interview/live", json={"minutes": 10, "language": "fr"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 422 and "language" in r.text
