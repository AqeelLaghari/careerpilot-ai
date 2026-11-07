"""Loads settings from backend/.env so secrets never live in code."""
import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")            # "smart": grading, feedback
GEMINI_MODEL_FAST = os.getenv("GEMINI_MODEL_FAST", "gemini-3.5-flash-lite")  # "fast": simple, frequent tasks
FIREBASE_KEY_PATH = BACKEND_DIR / os.getenv("FIREBASE_KEY_PATH", "firebase-key.json")
DATA_DIR = BACKEND_DIR / "data"
