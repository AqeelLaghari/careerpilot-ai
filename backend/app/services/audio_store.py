"""Recorded interview answers on the server's disk (Day 16).

The app streams raw audio while the user speaks: PCM, 16-bit, mono, 16 kHz. That is
exactly what Whisper (Day 17) wants, so nothing needs converting. When an answer ends,
the chunks are written as a normal .wav file (44-byte header + the samples).

Privacy: files live in data/raw/interviews/ (git-ignored), in a folder named by a hash of
the user ID, not the ID itself. Audio is only kept until it is transcribed (Day 17), and
anything older than KEEP_HOURS is deleted anyway.
"""
import hashlib
import re
import struct
import time
from pathlib import Path

from app.config import DATA_DIR

ROOT = DATA_DIR / "raw" / "interviews"
SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2              # bytes per sample (16-bit)
CHANNELS = 1
BYTES_PER_SECOND = SAMPLE_RATE * SAMPLE_WIDTH * CHANNELS
KEEP_HOURS = 24
_SAFE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _user_dir(uid: str) -> str:
    return hashlib.sha256(f"interview|{uid}".encode()).hexdigest()[:16]


def answer_path(uid: str, session_id: str, question_id: str) -> Path:
    if not (_SAFE.match(session_id) and _SAFE.match(question_id)):
        raise ValueError("bad id")                     # never let an id walk out of the folder
    return ROOT / _user_dir(uid) / session_id / f"{question_id}.wav"


def wav_header(data_bytes: int) -> bytes:
    """Standard 44-byte header of a PCM .wav file."""
    return (b"RIFF" + struct.pack("<I", 36 + data_bytes) + b"WAVE"
            + b"fmt " + struct.pack("<IHHIIHH", 16, 1, CHANNELS, SAMPLE_RATE, BYTES_PER_SECOND,
                                    CHANNELS * SAMPLE_WIDTH, SAMPLE_WIDTH * 8)
            + b"data" + struct.pack("<I", data_bytes))


def save_answer(uid: str, session_id: str, question_id: str, pcm: bytes) -> dict:
    """Write the answer as .wav (a new recording of the same question replaces the old one)."""
    if len(pcm) % 2:
        pcm = pcm[:-1]                                 # half a sample can't be played
    path = answer_path(uid, session_id, question_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(wav_header(len(pcm)) + pcm)
    cleanup()
    return {"bytes": len(pcm), "duration_sec": round(len(pcm) / BYTES_PER_SECOND, 2),
            "format": "wav pcm16 mono 16kHz", "path": str(path.relative_to(ROOT))}


def delete_answer(uid: str, session_id: str, question_id: str):
    """After transcription the audio is no longer needed: delete it (privacy)."""
    try:
        answer_path(uid, session_id, question_id).unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def seconds(n_bytes: int) -> float:
    return n_bytes / BYTES_PER_SECOND


def cleanup(now: float | None = None):
    """Delete recordings older than KEEP_HOURS (and empty folders)."""
    if not ROOT.exists():
        return
    limit = (now or time.time()) - KEEP_HOURS * 3600
    for f in ROOT.rglob("*.wav"):
        try:
            if f.stat().st_mtime < limit:
                f.unlink()
        except OSError:
            pass
    for d in sorted((p for p in ROOT.rglob("*") if p.is_dir()), key=lambda p: -len(p.parts)):
        try:
            d.rmdir()                                  # only works when empty
        except OSError:
            pass
