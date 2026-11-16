"""Speech-to-text and speaking metrics for interview answers (Day 17).

Transcription: faster-whisper (the same Whisper models, re-implemented to run fast on a
CPU), model "base", int8 = free, offline, about 2-3 s for a 20 s answer on a laptop.
  - word_timestamps: start/end time of every word -> pace and pauses
  - vad_filter: skips long silences (stops Whisper "hearing" words in silence)
  - initial_prompt: Whisper normally tidies speech and DROPS "um"/"uh". Starting it with a
    sentence full of fillers makes it write them down (tested: 0 vs 3 "uh" in one answer).
    The prompt also lists the role and the user's skills, so technical words are spelled right.

Metrics (rules, all explained to the user):
  pace       words per minute while speaking (first word to last word), fillers not counted
  fillers    um / uh / er / hmm ...                   (sounds, never useful)
  habits     like / you know / basically / actually / I mean / kind of ...   (overused phrases)
  pauses     silences between words longer than PAUSE_SECONDS
  repeats    the same word twice in a row ("I I", "the the")

Urdu (Day 27): language="ur" uses the Whisper model in config.WHISPER_MODEL_URDU ("small":
much better in Urdu than "base"), an Urdu filler prompt, Urdu habit words (matlab, yani, acha;
"woh woh" is caught as a repeat), its own pace range (Urdu has many short words such as ka,
ki, hai, so normal speech has more words a minute) and tips in Roman Urdu.
"""
import logging
import re
import threading
import time
from functools import lru_cache

from app import config

log = logging.getLogger(__name__)

MODEL_SIZE, COMPUTE_TYPE = "base", "int8"
PAUSE_SECONDS = 2.0
FILLER_PROMPT = "Umm, let me think, like, hmm... Okay, here is what I, uh, mean, you know."
# Urdu: the same idea (fillers written down), in Urdu script, with English mixed in as people speak
URDU_FILLER_PROMPT = "اممم، میرا مطلب ہے، یعنی، اچھا تو... ہمم، basically یہ"

# Pace in words per minute: (upper bound, label, advice)
PACE = [(100, "too slow", "Speak a little faster; long gaps make answers sound unsure."),
        (120, "a bit slow", "Slightly slow. That's fine for hard questions; keep the flow going."),
        (160, "good", "Good, clear pace."),
        (180, "a bit fast", "Slightly fast. Slow down on key points so they land."),
        (10_000, "too fast", "Too fast. Take a breath between points; the listener needs time.")]
URDU_PACE = [(100, "too slow", "Thora tez bolein; lambay waqfay jawab ko ghair yaqeeni bana dete hain."),
             (120, "a bit slow", "Raftar thori dheemi hai. Mushkil sawal par theek hai, bas rawani barqarar rakhein."),
             (180, "good", "Achi, saaf raftar."),
             (200, "a bit fast", "Raftar thori tez hai. Aham baaton par ahista bolein taa ke baat samajh aaye."),
             (10_000, "too fast", "Bohat tez. Har point ke beech saans lein; sunne wale ko waqt chahiye.")]

FILLERS = {"um", "umm", "ummm", "uh", "uhh", "uhm", "er", "erm", "ah", "ahh", "hmm", "hm", "mm", "mmm", "eh"}
HABIT_PHRASES = ["you know", "i mean", "kind of", "sort of", "you see"]
HABIT_WORDS = {"basically", "actually", "literally", "honestly", "obviously", "totally"}
# Whisper writes Urdu speech in Urdu script and English words in English: both are listed
URDU_FILLERS = FILLERS | {"ام", "امم", "اممم", "اں", "آں", "ہمم", "ہممم"}
URDU_HABIT_WORDS = HABIT_WORDS | {"مطلب", "یعنی", "اچھا", "matlab", "yani", "yaani", "acha", "achha", "accha"}
URDU_HABIT_PHRASES = HABIT_PHRASES + ["پتا ہے", "پتہ ہے"]
GOOD = {"fillers_per_min": 3.0, "habits_per_min": 4.0}

# tips for each language: (no speech, fillers, habits, pauses, slow start, short answer)
TIPS = {
    "en": ("No speech was heard. Check that the microphone works and speak a little louder.",
           'You said "{top}" {times}. Pause silently instead; a short pause sounds confident.',
           '"{top}" came up {times}. Try to drop it.',
           "{n} long pauses. Plan your answer as 2-3 points before you start.",
           'You started speaking after {s:.0f} s. A short "Good question" buys time naturally.',
           "Very short answer. Add an example and a result to show what you did."),
    "ur": ("Koi awaaz sunai nahi di. Check karein ke microphone kaam kar raha hai, aur thori buland awaaz mein "
           "bolein.",
           'Aap ne "{top}" {times} kaha. Is ki jagah khamosh waqfa lein; chhota sa waqfa pur-aitmaad lagta hai.',
           '"{top}" {times} aaya. Isay kam karne ki koshish karein.',
           "{n} lambay waqfay. Jawab shuru karne se pehle 2-3 points soch lein.",
           'Aap ne {s:.0f} second baad bolna shuru kiya. "Acha sawal hai" kehna qudrati tor par waqt de deta hai.',
           "Jawab bohat chhota hai. Ek misaal aur nateeja shamil karein taa ke pata chale aap ne kya kiya."),
}

_lock = threading.Lock()


def model_size(language: str = "en") -> str:
    return config.WHISPER_MODEL_URDU if language == "ur" else MODEL_SIZE


@lru_cache(maxsize=2)
def get_model(size: str = MODEL_SIZE):
    from faster_whisper import WhisperModel
    t = time.time()
    model = WhisperModel(size, device="cpu", compute_type=COMPUTE_TYPE)
    log.info("Whisper %s model loaded in %.0f s", size, time.time() - t)
    return model


def make_prompt(role: str | None = None, terms: list[str] | None = None, language: str = "en") -> str:
    """Filler-style opener + topic words (kept short: Whisper reads at most ~200 tokens)."""
    urdu = language == "ur"
    parts = [URDU_FILLER_PROMPT if urdu else FILLER_PROMPT]
    if role:
        parts.append(f"یہ {role} کا انٹرویو ہے۔" if urdu else f"This is a job interview for a {role}.")
    if terms:
        parts.append(("" if urdu else "Words that may come up: ") + ", ".join(dict.fromkeys(terms))[:300] + ".")
    return " ".join(parts)


def transcribe(path: str, prompt: str | None = None, fast: bool = False, language: str = "en") -> dict:
    """{'text', 'words': [{'w', 'start', 'end'}], 'duration', 'language_probability', 'seconds_taken'}"""
    t = time.time()
    with _lock:                                     # one at a time: Whisper already uses every CPU core
        segments, info = get_model(model_size(language)).transcribe(
            path, language="ur" if language == "ur" else "en", word_timestamps=True, vad_filter=True,
            beam_size=1 if fast else 5, initial_prompt=prompt or make_prompt(language=language),
            condition_on_previous_text=False)
        words = [{"w": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)}
                 for s in segments for w in (s.words or []) if w.word.strip()]
    return {"text": " ".join(w["w"] for w in words), "words": words, "duration": round(info.duration, 2),
            "language_probability": round(info.language_probability, 2),
            "seconds_taken": round(time.time() - t, 1)}


# ---------------------------------------------------------------- metrics --
def _norm(word: str) -> str:
    """Lower-case letters only, in any script (English or Urdu), so "Um," == "um"."""
    return re.sub(r"[^\w']|[\d_]", "", word.lower())


def _pace(wpm: float, language: str = "en") -> tuple[str, str]:
    table = URDU_PACE if language == "ur" else PACE
    for top, label, advice in table:
        if wpm < top:
            return label, advice
    return table[-1][1], table[-1][2]


def _times(n: int, language: str = "en") -> str:
    if language == "ur":
        return "ek dafa" if n == 1 else f"{n} dafa"
    return "once" if n == 1 else f"{n} times"


def analyse(words: list[dict], duration: float, language: str = "en") -> dict:
    """Speaking metrics from timed words."""
    urdu = language == "ur"
    tip = TIPS["ur" if urdu else "en"]
    filler_set = URDU_FILLERS if urdu else FILLERS
    habit_words = URDU_HABIT_WORDS if urdu else HABIT_WORDS
    if not words:
        return {"word_count": 0, "wpm": 0, "pace": "no speech", "speaking_seconds": 0,
                "fillers": {}, "filler_count": 0, "habits": {}, "habit_count": 0, "pauses": [],
                "long_pauses": 0, "longest_pause": 0, "repeats": 0, "start_delay": None, "tips": [tip[0]]}
    norm = [_norm(w["w"]) for w in words]
    fillers, habits = {}, {}
    for n in norm:
        if n in filler_set:
            key = {"umm": "um", "ummm": "um", "uhh": "uh", "uhm": "um", "erm": "er", "ahh": "ah",
                   "hm": "hmm", "mmm": "mm", "امم": "ام", "اممم": "ام", "آں": "اں", "ہممم": "ہمم"}.get(n, n)
            fillers[key] = fillers.get(key, 0) + 1
        elif n in habit_words:
            habits[n] = habits.get(n, 0) + 1
    text = " " + " ".join(norm) + " "
    for phrase in (URDU_HABIT_PHRASES if urdu else HABIT_PHRASES):
        c = text.count(f" {phrase} ")
        if c:
            habits[phrase] = c
    # "like" only counts as a habit when it stands alone between commas ("it was, like, hard")
    raw = [w["w"].lower() for w in words]
    like = sum(1 for i, w in enumerate(raw) if _norm(w) == "like"
               and (w.endswith(",") or (i > 0 and raw[i - 1].endswith(","))))
    if like:
        habits["like"] = like
    repeats = sum(1 for a, b in zip(norm, norm[1:], strict=False) if a and a == b and a not in filler_set)

    content = [n for n in norm if n and n not in filler_set]
    speaking = max(0.1, words[-1]["end"] - words[0]["start"])
    wpm = round(len(content) / speaking * 60)
    pauses = [{"at": words[i]["end"], "seconds": round(words[i + 1]["start"] - words[i]["end"], 1)}
              for i in range(len(words) - 1) if words[i + 1]["start"] - words[i]["end"] >= PAUSE_SECONDS]
    minutes = speaking / 60
    n_fill, n_habit = sum(fillers.values()), sum(habits.values())
    label, advice = _pace(wpm, language)

    tips = [advice]
    # a rate needs at least 2 cases: one "uh" in a 15 s answer is not a habit
    if n_fill >= 2 and n_fill / minutes > GOOD["fillers_per_min"]:
        top = max(fillers, key=fillers.get)
        tips.append(tip[1].format(top=top, times=_times(fillers[top], language)))
    if n_habit >= 2 and n_habit / minutes > GOOD["habits_per_min"]:
        top = max(habits, key=habits.get)
        tips.append(tip[2].format(top=top, times=_times(habits[top], language)))
    if len(pauses) >= 2:
        tips.append(tip[3].format(n=len(pauses)))
    if words[0]["start"] > 4:
        tips.append(tip[4].format(s=words[0]["start"]))
    if speaking < 20 and len(content) < 40:
        tips.append(tip[5])
    return {
        "word_count": len(content), "wpm": wpm, "pace": label, "speaking_seconds": round(speaking, 1),
        "fillers": fillers, "filler_count": n_fill, "fillers_per_min": round(n_fill / minutes, 1),
        "habits": habits, "habit_count": n_habit, "habits_per_min": round(n_habit / minutes, 1),
        "pauses": pauses, "long_pauses": len(pauses),
        "longest_pause": max((p["seconds"] for p in pauses), default=0),
        "repeats": repeats, "start_delay": round(words[0]["start"], 1), "recording_seconds": round(duration, 1),
        "tips": tips,
    }


def process(path: str, role: str | None = None, terms: list[str] | None = None, fast: bool = False,
            language: str = "en") -> dict:
    """Transcribe one answer and measure it. fast=True (live interview): greedy decoding,
    about twice as fast, slightly less accurate."""
    tr = transcribe(path, make_prompt(role, terms, language), fast, language)
    return {"transcript": tr["text"], "words": tr["words"],
            "metrics": analyse(tr["words"], tr["duration"], language),
            "model": f"faster-whisper {model_size(language)} {COMPUTE_TYPE}", "seconds_taken": tr["seconds_taken"]}
