"""Speaking metrics from timed words (Day 17). Whisper itself is not run here."""
from app.services import speech


def _words(text, gap=0.4, pauses=None):
    """Words 0.3 s long, `gap` s apart; pauses = {index: extra seconds before that word}."""
    out, t = [], 0.0
    for i, w in enumerate(text.split()):
        t += (pauses or {}).get(i, 0)
        out.append({"w": w, "start": round(t, 2), "end": round(t + 0.3, 2)})
        t += 0.3 + gap - 0.3
    return out


def test_pace_fillers_habits_pauses_repeats():
    text = "Um, I built a pipeline, uh, with Docker and, you know, it was, like, basically fast. I I think so."
    words = _words(text, pauses={8: 3.0})
    m = speech.analyse(words, 20)
    assert m["fillers"] == {"um": 1, "uh": 1}
    assert m["habits"] == {"you know": 1, "like": 1, "basically": 1}
    assert m["long_pauses"] == 1 and m["pauses"][0]["seconds"] >= 3
    assert m["repeats"] == 1 and m["word_count"] == len(text.split()) - 2
    assert m["wpm"] > 0 and m["pace"] in {"too slow", "a bit slow", "good", "a bit fast", "too fast"}


def test_like_as_a_normal_word_is_not_a_habit():
    m = speech.analyse(_words("I would like to learn Kubernetes"), 5)
    assert "like" not in m["habits"]


def test_pace_labels_and_tips():
    fast = speech.analyse(_words(" ".join(["word"] * 120), gap=0.25), 30)   # 4 words/s = 240 wpm
    assert fast["pace"] == "too fast" and "Too fast" in fast["tips"][0]
    slow = speech.analyse(_words(" ".join(["word"] * 20), gap=1.0), 30)
    assert slow["pace"] == "too slow"
    many = speech.analyse(_words("um so um this uh is um what uh I do"), 10)
    assert any('"um"' in t for t in many["tips"])


def test_no_speech():
    m = speech.analyse([], 5)
    assert m["word_count"] == 0 and "microphone" in m["tips"][0]


def test_prompt_has_fillers_role_and_terms():
    p = speech.make_prompt("DevOps Engineer", ["Kubernetes", "AWS", "Kubernetes"])
    assert "uh" in p and "DevOps Engineer" in p and p.count("Kubernetes") == 1
