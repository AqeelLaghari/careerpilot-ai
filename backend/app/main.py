"""CareerPilot AI backend. Run with:  uvicorn app.main:app --reload"""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.auth import current_uid
from app.services import llm
from app.deps import blackboard
from app.orchestrator.blackboard import SECTIONS
from app.routers import career, market, questionnaire, resume

logging.basicConfig(level=logging.INFO)

def _warm_up():
    """Load the SBERT model + role index in the background, so the first
    user request doesn't wait ~10 s for them."""
    try:
        from app.services import career_matcher
        career_matcher.role_index()
    except Exception:
        logging.getLogger(__name__).exception("Warm-up failed (matching will retry on first use)")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=_warm_up, daemon=True).start()
    yield


app = FastAPI(title="CareerPilot AI", version="0.2.0", lifespan=lifespan)

# Lets the Flutter web app (running on a different port) call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(resume.router)
app.include_router(market.router)
app.include_router(career.router)
app.include_router(questionnaire.router)



@app.get("/health")
def health():
    return {
        "status": "ok",
        "firestore_connected": blackboard.persistent,
        "gemini_key_set": llm.available(),
        "gemini_models": llm.MODELS,
        "gemini_usage": dict(llm.usage),
    }


@app.get("/me")
def me(uid: str = Depends(current_uid)):
    """The logged-in user's full Blackboard state."""
    return {"uid": uid, "state": blackboard.read(uid)}


# --- Temporary test endpoints (removed before deployment, Day 25) ---

@app.get("/debug/state/{uid}")
def debug_read(uid: str):
    return blackboard.read(uid)


@app.post("/debug/state/{uid}/{section}")
def debug_write(uid: str, section: str, data: dict):
    if section not in SECTIONS:
        raise HTTPException(400, f"section must be one of {SECTIONS}")
    return blackboard.write(uid, section, data, agent="debug")
