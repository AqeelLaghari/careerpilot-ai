"""CareerPilot AI backend. Run with:  uvicorn app.main:app --reload"""
import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.auth import current_uid
from app.config import GEMINI_API_KEY
from app.orchestrator.blackboard import SECTIONS, Blackboard
from app.services.firebase import init_firestore

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="CareerPilot AI", version="0.1.0")

# Lets the Flutter web app (running on a different port) call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

blackboard = Blackboard(db=init_firestore())


@app.get("/health")
def health():
    return {
        "status": "ok",
        "firestore_connected": blackboard.persistent,
        "gemini_key_set": bool(GEMINI_API_KEY),
    }


@app.get("/me")
def me(uid: str = Depends(current_uid)):
    """The logged-in user's full Blackboard state."""
    return {"uid": uid, "state": blackboard.read(uid)}


# --- Temporary test endpoints (replaced by real agents + login on Day 3+) ---

@app.get("/debug/state/{uid}")
def debug_read(uid: str):
    return blackboard.read(uid)


@app.post("/debug/state/{uid}/{section}")
def debug_write(uid: str, section: str, data: dict):
    if section not in SECTIONS:
        raise HTTPException(400, f"section must be one of {SECTIONS}")
    return blackboard.write(uid, section, data, agent="debug")
