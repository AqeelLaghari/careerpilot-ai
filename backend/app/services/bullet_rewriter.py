"""AI bullet rewriter (Day 24): turn a weak CV bullet into stronger versions.

Only runs when the user clicks "Improve" on one bullet (never in bulk), using the fast
Gemini tier. Before the bullet is sent, the user's name, companies, university, city,
emails and phone numbers are replaced with placeholders (privacy.scrub) and put back in
the answer. Gemini is told never to invent numbers: where a number would help it writes
"X", so the user fills in the real figure. If Gemini is unavailable, simple rules rewrite
the start of the bullet instead.
"""
import re

from pydantic import BaseModel

from app.services import llm, privacy
from app.services.ats_scorer import (
    ACTION_VERBS,
    FIRST_PERSON_RE,
    NUMBER_RE,
    WEAK_STARTS,
    _collect_bullets,
    _starts_with_action_verb,
)

MAX_BULLET = 400
LONG_BULLET = 35               # words (same limit as the ATS check)

# the rules fallback: a strong verb for each weak opening
REPLACE_START = {"responsible for": "Managed", "worked on": "Developed", "duties included": "Handled",
                 "involved in": "Contributed to", "tasked with": "Delivered", "in charge of": "Led",
                 "helped with": "Supported", "assisted with": "Supported", "participated in": "Contributed to"}
IRREGULAR = {"building": "Built", "leading": "Led", "teaching": "Taught", "writing": "Wrote", "running": "Ran",
             "making": "Made", "doing": "Did", "giving": "Gave", "setting": "Set", "cutting": "Cut",
             "drawing": "Drew", "selling": "Sold", "speaking": "Spoke", "taking": "Took", "bringing": "Brought",
             "holding": "Held", "winning": "Won", "keeping": "Kept", "sending": "Sent", "meeting": "Met"}


class _Rewrite(BaseModel):
    versions: list[str]
    tip: str


def review(entities: dict | None) -> list[dict]:
    """Every bullet in the CV's experience and projects, with what makes it weak."""
    out = []
    for text in _collect_bullets(entities or {}):
        issues = []
        if not _starts_with_action_verb(text):
            issues.append("Doesn't start with an action verb")
        if not NUMBER_RE.search(text):
            issues.append("No number or measurable result")
        if len(text.split()) > LONG_BULLET:
            issues.append("Too long")
        if FIRST_PERSON_RE.search(text):
            issues.append("Uses I / my")
        out.append({"text": text, "issues": issues, "weak": bool(issues)})
    return out


def _past_tense(word: str) -> str | None:
    w = word.lower()
    if w in IRREGULAR:
        return IRREGULAR[w]
    if w.endswith("ing") and len(w) > 5:
        stem = w[:-3]                                  # managing -> manag, planning -> plann
        for cand in (stem + "ed", stem[:-1] + "ied"):  # managed, planned / studying -> studied
            if cand in ACTION_VERBS:
                return cand.capitalize()
        return (stem[:-1] + "ied" if stem.endswith("y") else stem + "ed").capitalize()   # coding -> coded
    return None


def rule_rewrite(bullet: str) -> dict:
    """Fix the opening (weak phrase or '-ing' word -> past-tense action verb), drop first-person
    words, and remind the user to add a number."""
    text = " ".join(bullet.split()).strip(" .;-•")
    text = re.sub(r"^(I|We)\s+((was|were|am|have been|had been)\s+)?", "", text, flags=re.I)
    low = text.lower()
    start = next((s for s in WEAK_STARTS if low.startswith(s)), None)
    if start:
        rest = text[len(start):].strip()
        first, _, tail = rest.partition(" ")
        verb = _past_tense(first)
        text = f"{verb} {tail}".strip() if verb else f"{REPLACE_START[start]} {rest}"
    else:
        first, _, tail = text.partition(" ")
        verb = _past_tense(first)
        if verb:
            text = f"{verb} {tail}".strip()
    text = re.sub(r"\b(my|our)\b\s*", "the ", text, flags=re.I)
    text = re.sub(r"\s+", " ", re.sub(r"\b(I|me|myself)\b", "", text)).strip()
    text = text[:1].upper() + text[1:]
    tip = ("Add a real number to show the impact, e.g. 'for 200+ users' or 'cut load time by 30%'."
           if not NUMBER_RE.search(text) else "Keep it to one or two lines.")
    return {"versions": [text], "tip": tip, "source": "rules"}


def _restore(text: str, original: str, private: list) -> str:
    """Put the user's own words back where the placeholders are, when it's clear which word
    each placeholder stood for (one word per placeholder in this bullet)."""
    found: dict[str, set[str]] = {}
    for t in private:
        m = re.search(rf"(?<!\w){re.escape(t['w'])}(?!\w)", original, flags=re.I)
        if m:
            found.setdefault(t["p"], set()).add(m.group(0))
    for placeholder, words in found.items():
        if len(words) == 1:
            text = text.replace(placeholder, next(iter(words)))
    return text


def _prompt(bullet: str, role: str | None) -> str:
    target = f" for a {role} role" if role else ""
    return f"""You improve CV bullet points{target}. Rewrite the bullet below in 3 different ways.

Rules:
- Start with a strong past-tense action verb (Built, Led, Automated, Reduced...). No "I", "my" or "we".
- Keep every fact from the original. Never invent tools, results or numbers.
- Where a number would show impact but none is given, write X (e.g. "for X users", "by X%") so the
  candidate can fill in the real figure.
- 12 to 25 words each, one sentence, no full stop at the end.
- {privacy.NOTE} Keep any [placeholder] exactly as written.

Also give one short tip (under 20 words) on what would make this bullet even stronger.

Bullet: {bullet}"""


def rewrite(bullet: str, role: str | None = None, private: list | None = None) -> dict:
    """{"versions": [...], "tip": str, "source": "ai" | "rules"}"""
    bullet = " ".join((bullet or "").split())[:MAX_BULLET]
    if len(bullet.split()) < 2:
        raise ValueError("Paste a full bullet point (at least a few words).")
    private = private or []
    safe = privacy.scrub(bullet, private)
    out = llm.generate_json(_prompt(safe, role), _Rewrite, tier="fast", temperature=0.4, timeout=15, quick=True)
    if out:
        seen, versions = {bullet.lower()}, []
        for v in out.get("versions") or []:
            v = _restore(" ".join(str(v).split()).strip(" .;"), bullet, private)
            if 3 <= len(v.split()) <= 60 and v.lower() not in seen:
                seen.add(v.lower())
                versions.append(v)
        if versions:
            tip = " ".join(str(out.get("tip") or "").split())[:200]
            return {"versions": versions[:3], "tip": _restore(tip, bullet, private), "source": "ai"}
    return rule_rewrite(bullet)
