"""Live video interview (Day 20): one continuous spoken conversation.

POST /interview/live {"minutes": 5|10|15, "language": "en"|"ur"}   → a live session (agenda from the CV)
WS   /interview/live/ws                     → the conversation

Messages (JSON text unless said otherwise):
  app → server   {"type": "auth", "token", "session_id"}                 first, within AUTH_WAIT s
  server → app   {"type": "ready", "minutes", "role"}
  server → app   {"type": "say", "turn_id", "text", "kind", "remaining_sec"}   the interviewer speaks
                 (Urdu, Day 27: also "roman" = subtitles, "hindi" = for a Hindi voice when there's no Urdu one)
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
import threading
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
    language: str = "en"           # "en" | "ur" (Day 27)
    voice: str | None = None       # Urdu: the voice the app found, "ur" | "hi" | "none" (see interviewer.VOICES)


@router.post("/live")
def new_live(body: LiveIn, uid: str = Depends(current_uid)):
    """Prepare a live interview (the agenda is made from the CV; about 3-10 s)."""
    if body.minutes not in interviewer.TOPICS_FOR:
        raise HTTPException(422, "minutes must be 5, 10 or 15")
    if body.language not in interviewer.LANGUAGES:
        raise HTTPException(422, "language must be 'en' or 'ur'")
    if body.language == "ur":
        # load the Urdu speech model now (a few seconds; the first time it is downloaded) so the
        # first answer isn't slow
        threading.Thread(target=speech.get_model, args=(speech.model_size("ur"),), daemon=True).start()
    try:
        live = agent.new_live(uid, body.minutes, body.role, body.language, body.voice)
    except NoResumeError as e:
        raise HTTPException(404, str(e)) from e
    return {k: live[k] for k in ("id", "role", "level", "minutes", "status", "language")}


async def _send(ws: WebSocket, **msg):
    try:
        await ws.send_text(json.dumps(msg))
    except (WebSocketDisconnect, RuntimeError):
        pass            # the app already left (e.g. pressed End and went back); state is saved anyway


def _process_answer(uid: str, live: dict, file_id: str, pcm: bytes, vision: dict | None,
                    heard: dict | None = None) -> dict:
    """Whisper thread: save the audio, transcribe (fast mode), measure, delete the audio.

    heard: {"bytes", "words"}, the part of this answer already transcribed at an earlier pause.
    Only the audio after it is transcribed now (each pause cuts at a silence, so nothing is
    split mid-word), and heard is moved on. Without this, every pause transcribed the whole
    answer again, which made long answers slow (most of all in Urdu, which uses a bigger model)."""
    secs = audio_store.seconds(len(pcm))
    answer = {"duration_sec": round(secs, 1), "vision": vision}
    language = live.get("language", "en")
    if secs < 0.5:
        return answer | {"transcript": "", "metrics": speech.analyse([], 0, language)}
    start = heard["bytes"] if heard and heard["bytes"] <= len(pcm) else 0
    start -= start % 2                                        # 16-bit samples
    words = list(heard["words"]) if start else []
    tail = pcm[start:]
    try:
        if audio_store.seconds(len(tail)) >= 0.3:
            terms = [x for t in live["agenda"] for x in (t.get("skill"), t.get("project")) if x]
            # the candidate's own name and university, so Whisper spells them right (runs locally)
            who = live.get("candidate") or {}
            terms = [x for x in (who.get("full_name"), who.get("university"), who.get("subject")) if x] + terms
            audio_store.save_answer(uid, live["id"], file_id, tail)
            try:
                path = audio_store.answer_path(uid, live["id"], file_id)
                tr = speech.transcribe(str(path), speech.make_prompt(live["role"], terms, language), fast=True,
                                       language=language)
            finally:
                audio_store.delete_answer(uid, live["id"], file_id)
            shift = audio_store.seconds(start)
            words += [w | {"start": round(w["start"] + shift, 2), "end": round(w["end"] + shift, 2)}
                      for w in tr["words"]]
        if heard is not None:
            heard.update(bytes=len(pcm), words=words)
        return answer | _measured(words, secs, language)
    except Exception:
        log.exception("Live transcription failed")
        return answer | {"transcript": "", "metrics": speech.analyse([], secs, language),
                         "error": "transcription failed"}


def _closing(live: dict) -> bool:
    """The candidate is asking THEIR question: the reply needs every word, so wait for all of it."""
    return bool(live["turns"]) and live["turns"][-1]["kind"] == "candidate_questions"


def _measured(words: list[dict], secs: float, language: str) -> dict:
    """{"transcript", "metrics"} for the words heard so far."""
    m = speech.analyse(words, secs, language)
    m["pauses"] = m.get("pauses", [])[:10]
    return {"transcript": " ".join(w["w"] for w in words)[:3000], "metrics": m}


# The next question is chosen from what is ALREADY transcribed when the user pauses, if at most this
# much speech is still being transcribed and enough words are there. Speech-to-text takes ~3 s
# whatever the length (Urdu), so waiting for the last words would add those seconds to every gap;
# the full answer is still saved (a moment later) for the report.
EARLY_MISSING_SECONDS = 8
EARLY_MIN_WORDS = 15


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
    await _send(ws, type="ready", minutes=live["minutes"], role=live["role"], language=live.get("language", "en"))
    loop = asyncio.get_running_loop()

    async def save():
        await run_in_threadpool(agent.save_live, uid, live)

    async def say(nxt: dict):
        turn = {"id": f"t{len(live['turns']) + 1}", "topic_id": nxt["topic_id"], "kind": nxt["kind"],
                "text": nxt["text"], "source": nxt.get("source"), "at": time.time()}
        if nxt.get("roman"):                               # Urdu: subtitles + the Hindi-voice version
            turn.update(roman=nxt["roman"], hindi=nxt.get("hindi") or nxt["text"])
        if nxt.get("check") and live["turns"]:
            # the interviewer's silent check of the PREVIOUS answer (mistake / vague) for the report
            live["turns"][-1]["check"] = {"kind": nxt["check"], "note": nxt.get("note", "")}
        live["turns"].append(turn)
        await _send(ws, type="say", turn_id=turn["id"], text=turn["text"], roman=turn.get("roman"),
                    hindi=turn.get("hindi"), kind=turn["kind"], remaining_sec=round(interviewer.remaining_seconds(live)))
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
        if filling:
            await asyncio.gather(*filling, return_exceptions=True)
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
            await _send(ws, type="say", turn_id=last["id"], text=last["text"], roman=last.get("roman"),
                        hindi=last.get("hindi"), kind=last["kind"],
                        remaining_sec=round(interviewer.remaining_seconds(live)))
        else:
            await say(await loop.run_in_executor(None, interviewer.decide, live))

    listening, buf, vision = None, bytearray(), None
    spec: dict = {}            # early work started at the last pause: {"n", "task", "resumed"}
    heard: dict = {"bytes": 0, "words": []}   # the answer so far, transcribed in pieces while it is spoken
    sent = 0                   # bytes of this answer already handed to Whisper (chunks + pauses)
    filling: set = set()       # answers still being completed in the background

    def transcribe_upto(turn_id: str, pcm: bytes, tag: str, heard: dict) -> asyncio.Future:
        """Queue the audio up to here for Whisper (only the part after `heard` is transcribed)."""
        return loop.run_in_executor(_stt, _process_answer, uid, live, f"{turn_id}_{tag}", pcm, None, heard)

    async def think_early(turn_id: str, pcm: bytes, n: int, heard: dict, full: asyncio.Future):
        """At a pause: choose the next question on a COPY of the interview, from what is already
        transcribed when that is nearly everything (else after `full`, the transcript up to the
        pause). Skipped (None) if the user has spoken again since: a newer pause will do it."""
        language = live.get("language", "en")
        missing = audio_store.seconds(len(pcm) - heard["bytes"])
        if missing > EARLY_MISSING_SECONDS or len(heard["words"]) < EARLY_MIN_WORDS or _closing(live):
            answer = await full
        else:
            answer = {"duration_sec": round(audio_store.seconds(len(pcm)), 1), "vision": None} | _measured(
                list(heard["words"]), audio_store.seconds(len(pcm)), language)
        if spec.get("n") != n or spec.get("resumed"):
            return None
        draft = copy.deepcopy(live)
        next(t for t in draft["turns"] if t["id"] == turn_id)["answer"] = answer
        return draft, await loop.run_in_executor(None, interviewer.decide, draft)

    async def fill_answer(turn: dict, full: asyncio.Future, secs: float, eyes: dict | None):
        """The complete transcript of an answer whose next question was chosen early."""
        turn["answer"] = (await full) | {"duration_sec": round(secs, 1), "vision": eyes}
        await save()

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
                spec, heard, sent = {}, {"bytes": 0, "words": []}, 0
                for t in live["turns"]:
                    if t["id"] == listening:
                        t["listen_at"] = time.time()
            elif kind == "chunk" and listening is not None:
                # a short breath in a long answer: transcribe up to here now, while they carry on
                if audio_store.seconds(len(buf) - sent) >= 1:
                    sent = len(buf)
                    transcribe_upto(listening, bytes(buf), f"c{sent}", heard)
            elif kind == "pause" and listening is not None:
                n = spec.get("n", 0) + 1
                sent = len(buf)
                full = transcribe_upto(listening, bytes(buf), f"p{n}", heard)
                spec = {"n": n, "full": full,
                        "task": asyncio.ensure_future(think_early(listening, bytes(buf), n, heard, full))}
            elif kind == "resumed":
                spec["resumed"] = True                       # speaking again: that early question is out of date
            elif kind == "vision":
                vision = eye_contact.analyse(str(data.get("codes", ""))[:20000], data.get("fps", 5))
            elif kind == "answered" and listening is not None and live["status"] != "completed":
                turn = next((t for t in live["turns"] if t["id"] == listening), live["turns"][-1])
                pcm, eyes = bytes(buf), vision
                listening, buf, vision = None, bytearray(), None
                await _send(ws, type="thinking")
                t0, early, full = time.time(), None, spec.get("full")
                if spec.get("task") is not None and not data.get("spoke_since_pause") and not spec.get("resumed"):
                    try:
                        early = await spec["task"]               # usually finished already
                    except Exception:
                        log.warning("Early answer processing failed; doing it now", exc_info=True)
                spec = {}
                if early is not None:
                    draft, nxt = early
                    live["agenda"] = draft["agenda"]
                    secs = audio_store.seconds(len(pcm))
                    if full.done():
                        turn["answer"] = full.result() | {"duration_sec": round(secs, 1), "vision": eyes}
                    else:                                        # the last words: saved a moment later
                        turn["answer"] = next(t for t in draft["turns"] if t["id"] == turn["id"])["answer"] | {
                            "duration_sec": round(secs, 1), "vision": eyes}
                        task = asyncio.ensure_future(fill_answer(turn, full, secs, eyes))
                        filling.add(task)
                        task.add_done_callback(filling.discard)
                else:
                    # only the audio after the last pause is still to transcribe (heard); it waits
                    # in line behind any pause still being transcribed, so heard is up to date
                    turn["answer"] = await loop.run_in_executor(_stt, _process_answer, uid, live, turn["id"], pcm,
                                                                eyes, heard)
                    nxt = await loop.run_in_executor(None, interviewer.decide, live)
                turn["wait_sec"] = round(time.time() - t0, 1)   # how long the user waited (kept for tuning)
                log.info("Live turn %s: answer %.1f s, next ready %.1f s after the end (%s%s)", turn["id"],
                         turn["answer"]["duration_sec"], turn["wait_sec"], nxt.get("source"),
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
