"""CareerPilot AI backend. Run with:  uvicorn app.main:app --reload"""
import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.auth import current_uid
from app.services import llm
from app.deps import blackboard
from app.orchestrator.blackboard import SECTIONS
from app.routers import resume

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="CareerPilot AI", version="0.1.0")

# Lets the Flutter web app (running on a different port) call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(resume.router)


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
