"""Live video interview (Day 20): one continuous spoken conversation.

POST /interview/live {"minutes": 5|10|15}   → a live session (agenda from the user's CV)
WS   /interview/live/ws                     → the conversation

Messages (JSON text unless said otherwise):
  app → server   {"type": "auth", "token", "session_id"}                 first, within AUTH_WAIT s
  server → app   {"type": "ready", "minutes", "role"}
  server → app   {"type": "say", "turn_id", "text", "kind", "remaining_sec"}   the interviewer speaks
  app → server   {"type": "listening", "turn_id"}      the app has finished speaking; the mic is open
  app → server   BINARY frames: the answer (PCM 16-bit mono 16 kHz)
  app → server   {"type": "vision", "fps", "codes"}    where the user looked (eye_contact.py letters)
  app → server   {"type": "pause"}                     the user went quiet (~1 s) after speaking: the server
                 starts transcribing + choosing the next question NOW, in case this is the end
  app → server   {"type": "answered", "turn_id", "spoke_since_pause"}   the user finished (quiet for a few
                 s, or "I'm done"); if they didn't speak again since the last pause, the early result is used
  server → app   {"type": "thinking"}                  transcribing + deciding the next question
  ...            the next "say", and so on, until
  server → app   {"type": "ended"}                     after the goodbye (or after {"type": "end"} from the app)
  server → app   {"type": "error", "code", "message"}
The video never reaches the server; only the eye-contact letters do.
"""
import asyncio
import copy
import json
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.agents.interview_agent import NoResumeError
from app.auth import current_uid, uid_from_token
from app.routers.interview import _stt, agent, start_grading
from app.services import audio_store, eye_contact, interviewer, speech

router = APIRouter(prefix="/interview", tags=["Interview Coach Agent"])
log = logging.getLogger(__name__)

AUTH_WAIT, IDLE_TIMEOUT = 10, 300
MAX_ANSWER_SECONDS = 240          # one answer can't run longer than this


class LiveIn(BaseModel):
    minutes: int = 10
    role: str | None = None


@router.post("/live")
def new_live(body: LiveIn, uid: str = Depends(current_uid)):
    """Prepare a live interview (the agenda is made from the CV; about 3-10 s)."""
    if body.minutes not in interviewer.TOPICS_FOR:
        raise HTTPException(422, "minutes must be 5, 10 or 15")
    try:
        live = agent.new_live(uid, body.minutes, body.role)
    except NoResumeError as e:
        raise HTTPException(404, str(e))
    return {k: live[k] for k in ("id", "role", "level", "minutes", "status")}


async def _send(ws: WebSocket, **msg):
    try:
        await ws.send_text(json.dumps(msg))
    except (WebSocketDisconnect, RuntimeError):
        pass            # the app already left (e.g. pressed End and went back); state is saved anyway


def _process_answer(uid: str, live: dict, file_id: str, pcm: bytes, vision: dict | None) -> dict:
    """Whisper thread: save the audio, transcribe (fast mode), measure, delete the audio."""
    secs = audio_store.seconds(len(pcm))
    answer = {"duration_sec": round(secs, 1), "vision": vision}
    if secs < 0.5:
        return answer | {"transcript": "", "metrics": speech.analyse([], 0)}
    audio_store.save_answer(uid, live["id"], file_id, pcm)
    path = audio_store.answer_path(uid, live["id"], file_id)
    terms = [x for t in live["agenda"] for x in (t.get("skill"), t.get("project")) if x]
    try:
        r = speech.process(str(path), live["role"], terms, fast=True)
        m = dict(r["metrics"])
        m["pauses"] = m.get("pauses", [])[:10]
        return answer | {"transcript": r["transcript"][:3000], "metrics": m}
    except Exception:
        log.exception("Live transcription failed")
        return answer | {"transcript": "", "metrics": speech.analyse([], secs), "error": "transcription failed"}
    finally:
        audio_store.delete_answer(uid, live["id"], file_id)


@router.websocket("/live/ws")
async def live_ws(ws: WebSocket):
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
    live = await run_in_threadpool(agent.session, uid, str(first.get("session_id", "")))
    if live is None or live.get("mode") != "live":
        await _send(ws, type="error", code="session", message="No such live interview")
        await ws.close(4404)
        return
    if live["status"] == "completed":
        await _send(ws, type="ended")
        await ws.close()
        return
    await _send(ws, type="ready", minutes=live["minutes"], role=live["role"])
    loop = asyncio.get_running_loop()

    async def save():
        await run_in_threadpool(agent.save_live, uid, live)

    async def say(nxt: dict):
        turn = {"id": f"t{len(live['turns']) + 1}", "topic_id": nxt["topic_id"], "kind": nxt["kind"],
                "text": nxt["text"], "source": nxt.get("source"), "at": time.time()}
        if nxt.get("check") and live["turns"]:
            # the interviewer's silent check of the PREVIOUS answer (mistake / vague) for the report
            live["turns"][-1]["check"] = {"kind": nxt["check"], "note": nxt.get("note", "")}
        live["turns"].append(turn)
        await _send(ws, type="say", turn_id=turn["id"], text=turn["text"], kind=turn["kind"],
                    remaining_sec=round(interviewer.remaining_seconds(live)))
        await save()
        if nxt["kind"] == "goodbye":
            await finish()

    finished = False

    async def finish():
        nonlocal finished
        if finished:                     # e.g. the goodbye ended it and then the app sent "end"
            await _send(ws, type="ended")
            return
        finished = True
        live["status"], live["ended_at"] = "completed", time.time()
        for t in live["agenda"]:
            if t["status"] == "current":
                t["status"] = "done"
        await save()
        start_grading(uid, live["id"])   # the report is prepared in the background (Day 21)
        await _send(ws, type="ended")

    # start, or carry on after a dropped connection
    if not live["turns"]:
        live["started_at"], live["status"] = time.time(), "in_progress"
        await say(interviewer.start(live))
    else:
        last = live["turns"][-1]
        if last.get("answer") is None:                     # repeat the question that was not answered
            await _send(ws, type="say", turn_id=last["id"], text=last["text"], kind=last["kind"],
                        remaining_sec=round(interviewer.remaining_seconds(live)))
        else:
            await say(await loop.run_in_executor(None, interviewer.decide, live))

    listening, buf, vision = None, bytearray(), None
    spec: dict = {}            # early work started at the last pause: {"n", "task"}

    def think_early(turn_id: str, pcm: bytes, n: int):
        """At a pause: transcribe what was said so far and choose the next question, on a COPY
        of the interview (thrown away if the user carries on speaking)."""
        draft = copy.deepcopy(live)
        turn = next(t for t in draft["turns"] if t["id"] == turn_id)
        turn["answer"] = _process_answer(uid, draft, f"{turn_id}_early{n}", pcm, None)
        return draft, interviewer.decide(draft)

    try:
        while True:
            msg = await asyncio.wait_for(ws.receive(), IDLE_TIMEOUT)
            if msg["type"] == "websocket.disconnect":
                return
            if msg.get("bytes") is not None:
                if listening is not None and audio_store.seconds(len(buf)) < MAX_ANSWER_SECONDS:
                    buf.extend(msg["bytes"])
                continue
            try:
                data = json.loads(msg.get("text") or "")
            except ValueError:
                continue
            kind = data.get("type")
            if kind == "listening":
                listening, buf, vision = data.get("turn_id"), bytearray(), None
                spec = {}
            elif kind == "pause" and listening is not None:
                n = spec.get("n", 0) + 1
                spec = {"n": n, "task": loop.run_in_executor(_stt, think_early, listening, bytes(buf), n)}
            elif kind == "vision":
                vision = eye_contact.analyse(str(data.get("codes", ""))[:20000], data.get("fps", 5))
            elif kind == "answered" and listening is not None and live["status"] != "completed":
                turn = next((t for t in live["turns"] if t["id"] == listening), live["turns"][-1])
                pcm, eyes = bytes(buf), vision
                listening, buf, vision = None, bytearray(), None
                await _send(ws, type="thinking")
                t0, early = time.time(), None
                if spec.get("task") is not None and not data.get("spoke_since_pause"):
                    try:
                        early = await spec["task"]               # usually finished already
                    except Exception:
                        log.warning("Early answer processing failed; doing it now", exc_info=True)
                spec = {}
                if early is not None:
                    draft, nxt = early
                    live["agenda"] = draft["agenda"]
                    turn["answer"] = next(t for t in draft["turns"] if t["id"] == turn["id"])["answer"] | {
                        "duration_sec": round(audio_store.seconds(len(pcm)), 1), "vision": eyes}
                else:
                    turn["answer"] = await loop.run_in_executor(_stt, _process_answer, uid, live, turn["id"], pcm, eyes)
                    nxt = await loop.run_in_executor(None, interviewer.decide, live)
                log.info("Live turn %s: answer %.1f s, next ready %.1f s after the end (%s%s)", turn["id"],
                         turn["answer"]["duration_sec"], time.time() - t0, nxt.get("source"),
                         ", prepared early" if early else "")
                if nxt["kind"] == "end":
                    await finish()
                else:
                    await say(nxt)
            elif kind == "end":
                await finish()
            elif kind == "ping":
                await _send(ws, type="pong")
    except asyncio.TimeoutError:
        await ws.close(4408)
    except WebSocketDisconnect:
        return
