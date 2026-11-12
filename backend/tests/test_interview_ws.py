"""Live answer recording over the WebSocket (Day 16). Login is faked; audio is silence."""
import struct
import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.orchestrator.blackboard import Blackboard
from app.routers import interview
from app.services import audio_store, speech

SECOND = b"\x00\x00" * audio_store.SAMPLE_RATE           # one second of silence (PCM16 mono 16 kHz)


@pytest.fixture
def ws_env(monkeypatch, tmp_path):
    bb = Blackboard(db=None)
    monkeypatch.setattr(interview.agent, "bb", bb)
    monkeypatch.setattr(interview, "uid_from_token", lambda t: "u1" if t == "good" else None)
    monkeypatch.setattr(audio_store, "ROOT", tmp_path / "interviews")
    seen = []

    def fake_process(path, role=None, terms=None):          # Whisper is not run in tests
        seen.append((open(path, "rb").read(), role, terms))
        words = [{"w": w, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, w in enumerate("I, uh, built it".split())]
        return {"transcript": "I, uh, built it", "words": words, "metrics": speech.analyse(words, 2.0),
                "model": "fake", "seconds_taken": 0.1}
    monkeypatch.setattr(speech, "process", fake_process)
    session = {"id": "s1", "created_at": time.time(), "role": "DevOps Engineer", "level": "mid", "status": "ready",
               "source": "template", "questions": [{"id": "q1", "time_limit_sec": 90, "question": "Hi?"},
                                                   {"id": "q2", "time_limit_sec": 2, "question": "Short?"}]}
    bb.write("u1", "interviews", {"sessions": [session], "asked": []}, agent="test")
    return bb, tmp_path, seen


def _connect(client, token="good", session_id="s1"):
    ws = client.websocket_connect("/interview/ws").__enter__()
    ws.send_json({"type": "auth", "token": token, "session_id": session_id})
    return ws


def test_bad_login_and_unknown_session_are_closed(ws_env):
    client = TestClient(app)
    for token, sid, code in [("bad", "s1", 4401), ("good", "nope", 4404)]:
        ws = _connect(client, token, sid)
        assert ws.receive_json()["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == code


def test_record_an_answer_and_save_wav(ws_env):
    bb, tmp, seen = ws_env
    ws = _connect(TestClient(app))
    ready = ws.receive_json()
    assert ready["type"] == "ready" and ready["audio"]["sample_rate"] == 16000 and ready["answered"] == []
    ws.send_bytes(SECOND)                                   # before "start": ignored
    ws.send_json({"type": "start", "question_id": "q1"})
    assert ws.receive_json() == {"type": "started", "question_id": "q1", "time_limit_sec": 90}
    for _ in range(4):
        ws.send_bytes(SECOND[: len(SECOND) // 2])           # 4 chunks of half a second
    assert ws.receive_json() == {"type": "progress", "question_id": "q1", "seconds": 1.0}
    assert ws.receive_json()["seconds"] == 2.0
    ws.send_json({"type": "vision", "question_id": "q1", "fps": 5, "codes": "S" * 8 + "d" * 2})
    ws.send_json({"type": "stop", "question_id": "q1"})
    saved = ws.receive_json()
    assert saved["vision"]["eye_contact_pct"] == 100
    assert saved["type"] == "saved" and saved["duration_sec"] == 2.0 and saved["answered"] == 1
    assert saved["status"] == "in_progress" and saved["total"] == 2 and "take" not in saved
    done = ws.receive_json()                                # Day 17: the transcript follows
    assert done["type"] == "transcribed" and done["transcript"] == "I, uh, built it"
    assert done["metrics"]["fillers"] == {"uh": 1}
    ws.close()
    wav, role, terms = seen[0]
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE" and struct.unpack("<I", wav[24:28])[0] == 16000
    assert len(wav) == 44 + 2 * len(SECOND) and role == "DevOps Engineer"
    ans = bb.read_section("u1", "interviews")["sessions"][0]["answers"]["q1"]
    assert ans["status"] == "transcribed" and ans["duration_sec"] == 2.0 and ans["metrics"]["filler_count"] == 1
    assert "words" not in ans                               # word timings are not stored (doc size)
    assert ans["vision"]["seconds"] == 2.0
    assert not list((tmp / "interviews").rglob("*.wav"))   # audio deleted after transcription


def test_too_short_unknown_question_cancel_and_ping(ws_env):
    ws = _connect(TestClient(app))
    ws.receive_json()
    ws.send_json({"type": "start", "question_id": "q9"})
    assert ws.receive_json()["code"] == "question"
    ws.send_json({"type": "start", "question_id": "q1"})
    ws.receive_json()
    ws.send_bytes(b"\x00\x00" * 100)
    ws.send_json({"type": "stop"})
    assert ws.receive_json()["code"] == "too_short"
    ws.send_json({"type": "stop"})
    assert ws.receive_json()["code"] == "not_recording"
    ws.send_json({"type": "start", "question_id": "q1"})
    ws.receive_json()
    ws.send_json({"type": "cancel"})
    assert ws.receive_json()["type"] == "cancelled"
    ws.send_json({"type": "ping"})
    assert ws.receive_json()["type"] == "pong"
    ws.send_text("not json")
    assert ws.receive_json()["code"] == "bad_message"
    ws.close()


def test_long_answer_is_cut_at_the_limit(ws_env, monkeypatch):
    monkeypatch.setattr(interview, "EXTRA_SECONDS", 1)      # q2: 2 s limit + 1 s
    bb, _, _ = ws_env
    ws = _connect(TestClient(app))
    ws.receive_json()
    ws.send_json({"type": "start", "question_id": "q2"})
    ws.receive_json()
    msgs = []
    for _ in range(4):
        ws.send_bytes(SECOND)
    while True:
        m = ws.receive_json()
        msgs.append(m)
        if m["type"] == "saved":
            break
    assert m["cut"] is True and m["duration_sec"] == 3.0
    assert ws.receive_json()["type"] == "transcribed"
    ws.close()


def test_old_recordings_are_deleted(ws_env):
    _, tmp, _ = ws_env
    info = audio_store.save_answer("u1", "s1", "q1", SECOND)
    assert info["duration_sec"] == 1.0
    audio_store.cleanup(now=time.time() + (audio_store.KEEP_HOURS + 1) * 3600)
    assert not list((tmp / "interviews").rglob("*.wav"))
    with pytest.raises(ValueError):
        audio_store.answer_path("u1", "../../etc", "q1")


def test_wav_folder_is_a_hash_not_the_user_id(ws_env):
    _, tmp, _ = ws_env
    audio_store.save_answer("u1", "s1", "q1", SECOND)
    path = next((tmp / "interviews").rglob("q1.wav"))
    assert "u1" not in str(path.relative_to(tmp))


def test_a_new_take_is_not_overwritten_by_the_old_transcript(ws_env):
    bb, _, _ = ws_env
    from app.routers.interview import agent
    first = agent.save_answer("u1", "s1", "q1", {"bytes": 1, "duration_sec": 1, "format": "wav"})["take"]
    time.sleep(0.01)
    agent.save_answer("u1", "s1", "q1", {"bytes": 1, "duration_sec": 1, "format": "wav"})
    result = {"transcript": "old", "metrics": {"pauses": []}, "model": "fake"}
    assert agent.save_transcript("u1", "s1", "q1", first, result) is False
    assert bb.read_section("u1", "interviews")["sessions"][0]["answers"]["q1"]["status"] == "recorded"
