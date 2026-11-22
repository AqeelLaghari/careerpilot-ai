"""Connects to Firebase using the service-account key.

The key comes from the FIREBASE_KEY_JSON environment variable (the whole JSON, used on the
cloud server where it is stored as a secret) or, on laptops, from the key file.
If neither is there, the app still runs. It just keeps data in memory (lost on restart)
and logs a warning.
"""
import json
import logging
import os

import firebase_admin
from firebase_admin import credentials, firestore

from app.config import FIREBASE_KEY_PATH

log = logging.getLogger(__name__)


def _credentials():
    raw = os.getenv("FIREBASE_KEY_JSON", "").strip()
    if raw:
        try:
            return credentials.Certificate(json.loads(raw))
        except (ValueError, KeyError) as e:          # never log the key itself
            log.error("FIREBASE_KEY_JSON is not a valid service-account key (%s).", type(e).__name__)
            return None
    if FIREBASE_KEY_PATH.exists():
        return credentials.Certificate(str(FIREBASE_KEY_PATH))
    log.warning("No Firebase key at %s: running in memory-only mode.", FIREBASE_KEY_PATH)
    return None


def init_firestore():
    """Return a Firestore client, or None if Firebase isn't configured."""
    if not firebase_admin._apps:
        cred = _credentials()
        if cred is None:
            return None
        firebase_admin.initialize_app(cred)
    return firestore.client()
