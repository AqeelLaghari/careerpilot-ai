"""The Blackboard: the single shared memory for all agents.

Agents never talk to each other directly. Each agent reads the user's state
from here and writes its results back to its own "section". For example:

    Resume Agent    -> writes "resume"
    Career Agent    -> reads "resume", writes "career" and "roadmap"
    Interview Agent -> reads "resume" + "career", writes "interviews"

Storage has two layers:
    1. an in-memory cache (fast; plays the role of Redis in the proposal)
    2. Firestore document  users/{uid}  (permanent)
"""
import threading
import time
from copy import deepcopy

SECTIONS = ("profile", "resume", "questionnaire", "career", "roadmap", "jobs", "interviews")


class Blackboard:
    def __init__(self, db=None):
        self._db = db          # Firestore client, or None for memory-only
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()

    @property
    def persistent(self) -> bool:
        return self._db is not None

    def _doc(self, uid: str):
        return self._db.collection("users").document(uid)

    def read(self, uid: str) -> dict:
        """Return the user's full state (all sections)."""
        with self._lock:
            if uid in self._cache:
                return deepcopy(self._cache[uid])
        state = {}
        if self._db is not None:
            snap = self._doc(uid).get()
            state = snap.to_dict() or {}
        with self._lock:
            self._cache[uid] = state
        return deepcopy(state)

    def read_section(self, uid: str, section: str):
        return self.read(uid).get(section)

    def write(self, uid: str, section: str, data, agent: str) -> dict:
        """Replace one section of the user's state. Returns the full new state."""
        if section not in SECTIONS:
            raise ValueError(f"Unknown section '{section}'. Allowed: {SECTIONS}")
        meta = {"updated_by": agent, "updated_at": time.time()}

        self.read(uid)  # make sure the cache is loaded
        with self._lock:
            state = self._cache[uid]
            state[section] = deepcopy(data)
            state.setdefault("_meta", {})[section] = meta
            state["_version"] = state.get("_version", 0) + 1
            version = state["_version"]

        if self._db is not None:
            # merge=[...] replaces only this section, leaving the others untouched
            self._doc(uid).set(
                {section: data, "_meta": {section: meta}, "_version": version},
                merge=[section, f"_meta.{section}", "_version"],
            )
        return self.read(uid)
