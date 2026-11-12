"""HTTP endpoints for the Interview Coach Agent."""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.agents.interview_agent import InterviewAgent, NoResumeError
from app.auth import current_uid, uid_from_token
from app.deps import blackboard
from app.services import audio_store
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
    return s


# ------------------------------------------------------------------ live audio (Day 16) --
# One WebSocket per interview session. Messages (JSON text unless said otherwise):
#   app → server   {"type": "auth", "token": <Firebase login token>, "session_id": ...}   first, within AUTH_WAIT s
#   server → app   {"type": "ready", "questions": [...], "answered": [...], "audio": {format}}
#   app → server   {"type": "start", "question_id": "q1"}
#   app → server   BINARY frames: raw audio, PCM 16-bit mono 16 kHz, a few per second
#   server → app   {"type": "progress", "question_id", "seconds"}   about once a second
#   app → server   {"type": "stop", "question_id": "q1"}   → server saves the .wav
#   server → app   {"type": "saved", "question_id", "duration_sec", "answered", "total", "status"}
#   app → server   {"type": "cancel"} drops the answer being recorded; {"type": "ping"} → "pong"
#   server → app   {"type": "error", "code", "message"} (the connection stays open unless it's about login)
# Close codes: 4401 not logged in, 4404 no such session, 4408 nothing received for IDLE_TIMEOUT s.
AUTH_WAIT, IDLE_TIMEOUT = 10, 120
MIN_SECONDS = 0.5            # shorter = nothing was said
EXTRA_SECONDS = 60           # an answer may run this much past its time limit, then it is cut
MAX_SECONDS = 600            # never more than 10 minutes per answer


async def _send(ws: WebSocket, **msg):
    await ws.send_text(json.dumps(msg))


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

    async def finish(cut: bool = False):
        nonlocal current, buf
        qid, pcm = current, bytes(buf)
        current, buf = None, bytearray()
        secs = audio_store.seconds(len(pcm))
        if secs < MIN_SECONDS:
            await _send(ws, type="error", code="too_short", question_id=qid,
                        message="No answer was recorded. Check your microphone and try again.")
            return
        info = await run_in_threadpool(audio_store.save_answer, uid, session_id, qid, pcm)
        progress = await run_in_threadpool(agent.save_answer, uid, session_id, qid,
                                           {k: info[k] for k in ("bytes", "duration_sec", "format")} | {"cut": cut})
        await _send(ws, type="saved", question_id=qid, duration_sec=info["duration_sec"], cut=cut, **(progress or {}))

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
                current, buf, reported = qid, bytearray(), 0     # starting again replaces the old take
                await _send(ws, type="started", question_id=qid, time_limit_sec=limits[qid])
            elif kind == "stop":
                if current is None or (qid and qid != current):
                    await _send(ws, type="error", code="not_recording", message="Nothing is being recorded")
                    continue
                await finish()
            elif kind == "cancel":
                current, buf = None, bytearray()
                await _send(ws, type="cancelled")
            else:
                await _send(ws, type="error", code="bad_message", message=f"Unknown message type {kind!r}")
    except asyncio.TimeoutError:
        await ws.close(4408)
    except WebSocketDisconnect:
        return
