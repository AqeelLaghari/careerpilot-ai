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
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()                # free: YouTube Data API v3
HIMALAYAS_API_KEY = os.getenv("HIMALAYAS_API_KEY", "").strip()
# Firebase user IDs (comma separated) allowed to manage learned skills
ADMIN_UIDS = {u.strip() for u in os.getenv("ADMIN_UIDS", "").split(",") if u.strip()}   # optional: higher rate limit
# "development" on laptops; the Docker image sets "production" (debug endpoints are then switched off)
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
APP_VERSION = os.getenv("APP_VERSION", "0.3.0")
# Email/password accounts created on or after this date must verify their email (Day 23);
# older test accounts keep working. Google accounts are always verified by Google.
VERIFY_EMAIL_FROM = os.getenv("VERIFY_EMAIL_FROM", "2026-11-16")
# Whisper model for Urdu interviews (Day 27): "small" is clearly more accurate in Urdu than "base"
# (tested: about 6 s for a 17 s answer on a laptop CPU vs 2 s); "base" if speed matters more.
WHISPER_MODEL_URDU = os.getenv("WHISPER_MODEL_URDU", "small").strip()
