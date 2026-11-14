"""HTTP endpoints for the Interview Coach Agent."""
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.agents.interview_agent import InterviewAgent, NoResumeError
from app.auth import current_uid, uid_from_token
from app.deps import blackboard
from app.services import audio_store, eye_contact, speech
from app.services import interview_questions as iq

router = APIRouter(prefix="/interview", tags=["Interview Coach Agent"])
agent = InterviewAgent(blackboard)


class NewSessionIn(BaseModel):
    count: int = Field(default=iq.DEFAULT_COUNT, ge=iq.MIN_COUNT, le=iq.MAX_COUNT)
    role: str | None = Field(default=None, max_length=100)   # default: the user's target role


@router.post("/sessions")
def new_session(body: NewSessionIn, uid: str = Depends(current_uid)):
    """A fresh set of interview questions made for this user (about 3-8 s with Gemini)."""
    try:
        return agent.new_session(uid, body.count, body.role)
    except NoResumeError as e:
        raise HTTPException(404, str(e))


@router.get("/sessions")
def list_sessions(uid: str = Depends(current_uid)):
    return agent.sessions(uid)


@router.get("/sessions/{session_id}")
def get_session(session_id: str, uid: str = Depends(current_uid)):
    s = agent.session(uid, session_id)
    if s is None:
        raise HTTPException(404, "No such interview session")
    if agent.needs_report(s):                    # finished but not graded yet (or interrupted)
        start_grading(uid, session_id)
        s["report"] = {"status": "grading"}
    s.pop("private", None)                       # the private words list stays on the server
    return s


# Grading (Day 21): one Gemini call per finished live interview, in the background.
_grader = ThreadPoolExecutor(max_workers=2, thread_name_prefix="grader")


def start_grading(uid: str, session_id: str):
    _grader.submit(agent.grade_live, uid, session_id)


# ------------------------------------------------------------------ live audio (Day 16) --
# One WebSocket per interview session. Messages (JSON text unless said otherwise):
#   app → server   {"type": "auth", "token": <Firebase login token>, "session_id": ...}   first, within AUTH_WAIT s
#   server → app   {"type": "ready", "questions": [...], "answered": [...], "audio": {format}}
#   app → server   {"type": "start", "question_id": "q1"}
#   app → server   BINARY frames: raw audio, PCM 16-bit mono 16 kHz, a few per second
#   server → app   {"type": "progress", "question_id", "seconds"}   about once a second
#   app → server   {"type": "stop", "question_id": "q1"}   → server saves the .wav
#   server → app   {"type": "saved", "question_id", "duration_sec", "answered", "total", "status"}
#   app → server   {"type": "vision", "question_id", "fps", "codes": "SSSddS..."}  (Day 19, before
#                  "stop"): where the user looked, one letter per look; scored by eye_contact.py
#   app → server   {"type": "cancel"} drops the answer being recorded; {"type": "ping"} → "pong"
#   server → app   {"type": "error", "code", "message"} (the connection stays open unless it's about login)
# Close codes: 4401 not logged in, 4404 no such session, 4408 nothing received for IDLE_TIMEOUT s.
#   server → app   {"type": "transcribed", "question_id", "transcript", "metrics"}  a few s after "saved"
#                  (or {"type": "transcribed", "question_id", "error"} if speech-to-text failed)
AUTH_WAIT, IDLE_TIMEOUT = 10, 120
MIN_SECONDS = 0.5            # shorter = nothing was said
EXTRA_SECONDS = 60           # an answer may run this much past its time limit, then it is cut
MAX_SECONDS = 600            # never more than 10 minutes per answer


log = logging.getLogger(__name__)
_stt = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")   # one at a time: CPU-heavy


async def _send(ws: WebSocket, **msg):
    await ws.send_text(json.dumps(msg))


def _terms(session: dict) -> list[str]:
    """Words Whisper should expect: the skills and projects the questions are about."""
    return [x for q in session["questions"] for x in (q.get("skill"), q.get("project")) if x]


def _transcribe_job(uid: str, session: dict, qid: str, take: float) -> dict:
    """Runs in the Whisper thread: transcribe, measure, store, then delete the audio."""
    path = audio_store.answer_path(uid, session["id"], qid)
    if not path.exists():
        return {"question_id": qid, "error": "The recording is no longer on the server. Please record again."}
    try:
        result = speech.process(str(path), session.get("role"), _terms(session))
    except Exception as e:
        log.exception("Transcription failed")
        agent.save_transcript(uid, session["id"], qid, take, None, str(e))
        return {"question_id": qid, "error": "Could not turn this answer into text. Please record again."}
    if agent.save_transcript(uid, session["id"], qid, take, result):
        audio_store.delete_answer(uid, session["id"], qid)    # keep only the text and the numbers
    return {"question_id": qid, "transcript": result["transcript"], "metrics": result["metrics"],
            "seconds_taken": result["seconds_taken"]}


async def transcribe_and_notify(ws: WebSocket, uid: str, session: dict, qid: str, take: float):
    out = await asyncio.get_running_loop().run_in_executor(_stt, _transcribe_job, uid, session, qid, take)
    try:
        await _send(ws, type="transcribed", **out)
    except Exception:
        pass                       # the app went away; the result is on the Blackboard anyway


@router.websocket("/ws")
async def interview_ws(ws: WebSocket):
    await ws.accept()
    try:
        first = json.loads(await asyncio.wait_for(ws.receive_text(), AUTH_WAIT))
    except (asyncio.TimeoutError, ValueError, KeyError):
        await ws.close(4401)
        return
    except WebSocketDisconnect:
        return
    uid = await run_in_threadpool(uid_from_token, str(first.get("token", ""))) if first.get("type") == "auth" else None
    if uid is None:
        await _send(ws, type="error", code="auth", message="Please log in again")
        await ws.close(4401)
        return
    session_id = str(first.get("session_id", ""))
    session = await run_in_threadpool(agent.session, uid, session_id)
    if session is None:
        await _send(ws, type="error", code="session", message="No such interview session")
        await ws.close(4404)
        return
    limits = {q["id"]: q["time_limit_sec"] for q in session["questions"]}
    await _send(ws, type="ready", session_id=session_id,
                questions=[{"id": q["id"], "time_limit_sec": q["time_limit_sec"]} for q in session["questions"]],
                answered=sorted((session.get("answers") or {}).keys()),
                audio={"format": "pcm16", "sample_rate": audio_store.SAMPLE_RATE, "channels": audio_store.CHANNELS})

    current, buf, reported = None, bytearray(), 0
    vision = None                                        # eye contact for the current answer
    jobs: set = set()
    # Answers recorded before a server restart, still waiting for their transcript
    for qid, ans in (session.get("answers") or {}).items():
        if ans.get("status") == "recorded" and audio_store.answer_path(uid, session_id, qid).exists():
            jobs.add(asyncio.create_task(transcribe_and_notify(ws, uid, session, qid, ans["recorded_at"])))

    async def finish(cut: bool = False):
        nonlocal current, buf, vision
        qid, pcm, eyes = current, bytes(buf), vision
        current, buf, vision = None, bytearray(), None
        secs = audio_store.seconds(len(pcm))
        if secs < MIN_SECONDS:
            await _send(ws, type="error", code="too_short", question_id=qid,
                        message="No answer was recorded. Check your microphone and try again.")
            return
        info = await run_in_threadpool(audio_store.save_answer, uid, session_id, qid, pcm)
        progress = await run_in_threadpool(agent.save_answer, uid, session_id, qid,
                                           {k: info[k] for k in ("bytes", "duration_sec", "format")}
                                           | {"cut": cut, "vision": eyes})
        progress = progress or {}
        take = progress.pop("take", None)
        await _send(ws, type="saved", question_id=qid, duration_sec=info["duration_sec"], cut=cut, vision=eyes,
                    **progress)
        if take is not None:
            jobs.add(asyncio.create_task(transcribe_and_notify(ws, uid, session, qid, take)))

    try:
        while True:
            msg = await asyncio.wait_for(ws.receive(), IDLE_TIMEOUT)
            if msg["type"] == "websocket.disconnect":
                return                                   # an unfinished answer is dropped
            if msg.get("bytes") is not None:
                if current is None:
                    continue                             # audio between questions: ignore
                buf.extend(msg["bytes"])
                secs = audio_store.seconds(len(buf))
                if int(secs) > reported:
                    reported = int(secs)
                    await _send(ws, type="progress", question_id=current, seconds=round(secs, 1))
                if secs >= min(limits[current] + EXTRA_SECONDS, MAX_SECONDS):
                    await finish(cut=True)               # too long: keep what was said
                continue
            try:
                data = json.loads(msg.get("text") or "")
            except ValueError:
                await _send(ws, type="error", code="bad_message", message="Messages must be JSON")
                continue
            kind, qid = data.get("type"), data.get("question_id")
            if kind == "ping":
                await _send(ws, type="pong")
            elif kind == "start":
                if qid not in limits:
                    await _send(ws, type="error", code="question", message=f"No question {qid!r} in this session")
                    continue
                current, buf, reported, vision = qid, bytearray(), 0, None   # a new take replaces the old
                await _send(ws, type="started", question_id=qid, time_limit_sec=limits[qid])
            elif kind == "stop":
                if current is None or (qid and qid != current):
                    await _send(ws, type="error", code="not_recording", message="Nothing is being recorded")
                    continue
                await finish()
            elif kind == "vision":
                if current is not None and qid in (None, current):
                    vision = eye_contact.analyse(str(data.get("codes", ""))[:20000], data.get("fps", 5))
            elif kind == "cancel":
                current, buf = None, bytearray()
                await _send(ws, type="cancelled")
            else:
                await _send(ws, type="error", code="bad_message", message=f"Unknown message type {kind!r}")
    except asyncio.TimeoutError:
        await ws.close(4408)
    except WebSocketDisconnect:
        return
