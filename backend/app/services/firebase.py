"""Connects to Firebase using the service-account key file.

If the key file isn't there yet, the app still runs. It just keeps data in
memory (lost on restart) and logs a warning.
"""
import logging

import firebase_admin
from firebase_admin import credentials, firestore

from app.config import FIREBASE_KEY_PATH

log = logging.getLogger(__name__)


def init_firestore():
    """Return a Firestore client, or None if Firebase isn't configured."""
    if not FIREBASE_KEY_PATH.exists():
        log.warning("No Firebase key at %s: running in memory-only mode.", FIREBASE_KEY_PATH)
        return None
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(str(FIREBASE_KEY_PATH)))
    return firestore.client()
