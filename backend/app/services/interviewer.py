"""The live interviewer's brain (Day 20): what to say next in a real, spoken interview.

The interview follows an AGENDA made from the user's CV (Day 15 plan), in the order a real
interviewer uses:
    opening      greeting + "tell me about yourself: who you are, your studies, your experience"
    background   follow-up on studies / experience, based on what they said
    project      their own project or job from the CV
    technical    skills the role needs that they have
    gap          a skill the role needs that they lack (fair, rewards honesty)
    behavioural  teamwork, mistakes, deadlines (STAR)
    situational  an on-the-job scenario
    closing      "do you have any questions for me?" then a professional goodbye

After every answer Gemini (fast tier, short time budget) reads the conversation and decides:
follow up on this answer, move to the next topic, or wrap up, and writes a short natural
reaction + the next question. RULES always win over Gemini:
  - at most MAX_FOLLOW_UPS follow-ups per topic; no follow-up when time is short
  - wrap up when the time is nearly used or every topic is covered
  - an empty answer is asked again once ("Sorry, I didn't catch that"), then we move on
If Gemini is slow or down, the planned question for the next topic is used, so the
interview never stops.
"""
import random
import time
from functools import lru_cache

from pydantic import BaseModel, create_model

from app.services import llm, privacy

MAX_FOLLOW_UPS = 2
WRAP_UP_SECONDS = 75          # less time left than this: start closing
FOLLOW_UP_MIN_SECONDS = 120   # no follow-ups when less time than this is left
GEMINI_BUDGET = 6             # seconds; the user is waiting
GEMINI_HEDGE = 3.0            # s; Gemini usually answers in ~1.5 s: later than this, ask again in parallel
TOPICS_FOR = {5: 4, 10: 7, 15: 10}      # agenda size (plus opening/background) per interview length

REACTIONS = ["Thank you.", "Okay, thanks for that.", "Alright.", "Got it, thank you.", "I see, thanks.",
             "That's helpful, thank you.", "Okay."]


PREFIXES = {"muhammad", "mohammad", "muhammed", "mohammed", "mohd", "md", "m", "syed", "sayed", "syeda", "mr",
            "mrs", "ms", "miss", "dr", "engr", "hafiz", "rana", "malik", "ch", "chaudhry"}
NOT_A_NAME = {"resume", "cv", "curriculum", "vitae", "profile", "summary", "contact"}


def _title(text: str) -> str:
    """'BAHRIA UNIVERSITY KARACHI' -> 'Bahria University Karachi' (short acronyms like NED stay)."""
    if not text.isupper():
        return text
    out = []
    for w in text.split():
        if w in ("OF", "AND", "THE", "FOR"):
            out.append(w.lower())
        elif w.isalpha() and len(w) <= 4:          # NED, IBA, FAST, NUST, UET: keep as acronyms
            out.append(w)
        else:
            out.append(w.capitalize())
    return " ".join(out)


def candidate_info(entities: dict | None, year: int | None = None, answers: dict | None = None,
                   account: dict | None = None) -> dict:
    """CV details, overridden by what the user typed in their account profile (Day 23)."""
    out = _from_cv(entities, year, answers)
    a = account or {}
    if a.get("full_name"):
        cv_only = _from_cv({"name": a["full_name"]}, year)
        out.update({k: cv_only[k] for k in ("first_name", "full_name") if k in cv_only})
    if a.get("university"):
        out["university"] = a["university"]
        out.pop("subject", None)
        if a.get("degree"):
            out["subject"] = a["degree"]
    elif a.get("degree"):
        out["subject"] = a["degree"]
    if a.get("status") in ("student", "graduate", "professional") and out.get("university"):
        out["studying"] = a["status"] == "student"
    return out


def _from_cv(entities: dict | None, year: int | None = None, answers: dict | None = None) -> dict:
    """What a real interviewer would know from the CV before the call: the first name to
    use, the university, the subject and whether they are still studying. These are used in
    the interviewer's own (fixed) sentences and as Whisper hints; never sent to Gemini."""
    e = entities or {}
    out: dict = {}
    parts = [p.strip(".,") for p in str(e.get("name") or "").split()]
    if 1 <= len(parts) <= 5 and all(p.replace("-", "").replace("'", "").isalpha() for p in parts) \
            and not any(p.lower() in NOT_A_NAME for p in parts):
        names = [p for p in parts if p.lower() not in PREFIXES] or parts
        out["first_name"] = names[0].capitalize() if names[0].isupper() or names[0].islower() else names[0]
        out["full_name"] = " ".join(parts)
    # the most recent university-level education with a named institution
    order = {"PhD": 3, "Masters": 2, "Bachelors": 1}
    edu = [x for x in e.get("education") or [] if x.get("institution")]
    if edu:
        best = max(edu, key=lambda x: (order.get(x.get("degree_level"), 0), x.get("end_year") or 0))
        out["university"] = _title(str(best["institution"]).strip())[:80]
        if best.get("field"):
            out["subject"] = _title(str(best["field"]).strip())[:60]
        year = year or time.localtime().tm_year

        def val(k):
            return ((answers or {}).get(k) or {}).get("value")

        if best.get("expected") or best.get("end_year"):
            out["studying"] = bool(best.get("expected") or best["end_year"] >= year)
        elif val("career_stage") or val("graduation_year"):          # no years on the CV: the questionnaire
            grad = val("graduation_year")
            out["studying"] = val("career_stage") == "student" or (isinstance(grad, (int, float)) and grad >= year)
        else:
            out["studying"] = None                                    # unknown: neutral wording
    return out


def opening_text(role: str, who: dict | None = None) -> str:
    """The first thing the interviewer says. With the CV details it greets the candidate by
    name and mentions their university, like a real interviewer who has read the CV."""
    who = who or {}
    name = who.get("first_name")
    uni, subject = who.get("university"), who.get("subject")
    hello = f"Hello {name}, and thank you for joining." if name else "Hello, and thank you for joining."
    intro = (f"{hello} I'll be your interviewer today for the {role} position. "
             "This will feel like a normal conversation, so just answer naturally. ")
    if not uni:
        return intro + ("To start, could you tell me a little about yourself: who you are, where you're studying "
                        "or studied, and what experience you have so far?")
    what = f"{subject} at {uni}" if subject else f"at {uni}"
    if who.get("studying") is None:                 # the CV has no years: don't guess
        degree = f"your {subject} degree at {uni}" if subject else f"your studies at {uni}"
        return intro + (f"I can see {degree} on your CV. To start, could you tell me a little about yourself: "
                        "what you've learned during your studies, what interests you most, and what experience "
                        "you have so far?")
    if who.get("studying"):
        return intro + (f"I can see from your CV that you're studying {what}. To start, could you tell me a "
                        "little about yourself: what you've been learning there, what interests you most, and "
                        "what experience you have so far?")
    return intro + (f"I can see from your CV that you studied {what}. To start, could you tell me a little "
                    "about yourself: what you learned during your studies, what you enjoyed most, and what "
                    "experience you have so far?")


BACKGROUND_QUESTION = ("Could you tell me a bit more about your studies and any work, internship or project "
                       "experience? What did you enjoy most, and what did you learn from it?")
CANDIDATE_QUESTIONS = "We're almost at the end. Before we finish, do you have any questions for me?"
GOODBYE = ("Thank you very much for your time today. It was good talking to you. "
           "That's the end of the interview; your feedback report is being prepared now.")
REPEAT = "Sorry, I didn't quite catch that. Could you say that again?"
NO_ANSWER_REPLY = "That's a good question; the team will share the details in the next round."


# ------------------------------------------------------------------ Urdu (Day 27) --
# Everything the interviewer says in Urdu comes in three forms:
#   text   Urdu script        what an Urdu voice reads (Edge, Android)
#   roman  Roman Urdu         the subtitles
#   hindi  Devanagari         what a Hindi voice reads when the device has no Urdu voice
#                             (Chrome on a computer): spoken, it sounds the same
# The interviewer's own wording is gender-neutral (no "samajh gaya / gayi"), because the
# user chooses a female or a male voice, and it speaks to the candidate as "aap".
LANGUAGES = ("en", "ur")
URDU = {
    "background": ("کیا آپ اپنی پڑھائی اور کسی کام، انٹرن شپ یا پروجیکٹ کے تجربے کے بارے میں تھوڑا اور بتا سکتے "
                   "ہیں؟ آپ کو سب سے زیادہ کیا اچھا لگا، اور آپ نے اس سے کیا سیکھا؟",
                   "Kya aap apni parhai aur kisi kaam, internship ya project ke tajurbe ke baare mein thora aur bata "
                   "sakte hain? Aap ko sab se zyada kya acha laga, aur aap ne us se kya seekha?",
                   "क्या आप अपनी पढ़ाई और किसी काम, इंटर्नशिप या प्रोजेक्ट के तजुर्बे के बारे में थोड़ा और बता सकते "
                   "हैं? आपको सबसे ज़्यादा क्या अच्छा लगा, और आपने उससे क्या सीखा?"),
    "candidate_questions": ("ہم انٹرویو کے آخر میں ہیں۔ ختم کرنے سے پہلے، کیا آپ مجھ سے کوئی سوال پوچھنا چاہیں گے؟",
                            "Hum interview ke aakhir mein hain. Khatam karne se pehle, kya aap mujh se koi sawal "
                            "poochna chahenge?",
                            "हम इंटरव्यू के आख़िर में हैं। ख़त्म करने से पहले, क्या आप मुझसे कोई सवाल पूछना चाहेंगे?"),
    "goodbye": ("آج اپنا وقت دینے کا بہت شکریہ۔ آپ سے بات کر کے اچھا لگا۔ انٹرویو یہاں ختم ہوتا ہے، اور آپ کی "
                "فیڈبیک رپورٹ تیار ہو رہی ہے۔",
                "Aaj apna waqt dene ka bohat shukriya. Aap se baat kar ke acha laga. Interview yahan khatam hota "
                "hai, aur aap ki feedback report tayyar ho rahi hai.",
                "आज अपना वक़्त देने का बहुत शुक्रिया। आपसे बात करके अच्छा लगा। इंटरव्यू यहाँ ख़त्म होता है, और आपकी "
                "फ़ीडबैक रिपोर्ट तैयार हो रही है।"),
    "repeat": ("معاف کیجیے، آواز ٹھیک سے نہیں آئی۔ کیا آپ دوبارہ بتا سکتے ہیں؟",
               "Maaf kijiye, awaaz theek se nahi aayi. Kya aap dobara bata sakte hain?",
               "माफ़ कीजिए, आवाज़ ठीक से नहीं आई। क्या आप दोबारा बता सकते हैं?"),
    "no_answer_reply": ("اچھا سوال ہے؛ ٹیم اگلے راؤنڈ میں تفصیلات بتا دے گی۔",
                        "Acha sawal hai; team agle round mein tafseelat bata degi.",
                        "अच्छा सवाल है; टीम अगले राउंड में तफ़सीलात बता देगी।"),
}
URDU_REACTIONS = [("ٹھیک ہے۔", "Theek hai.", "ठीक है।"), ("شکریہ۔", "Shukriya.", "शुक्रिया।"),
                  ("اچھا، شکریہ۔", "Acha, shukriya.", "अच्छा, शुक्रिया।"),
                  ("ٹھیک ہے، بتانے کا شکریہ۔", "Theek hai, batane ka shukriya.", "ठीक है, बताने का शुक्रिया।"),
                  ("جی، اچھا۔", "Ji, acha.", "जी, अच्छा।")]
# Urdu phrases that judge an answer (never spoken during the interview), in both scripts
URDU_VERDICTS = ("ghalat", "galat", "sahi hai", "sahih", "durust", "bilkul theek", "theek kaha", "shabash",
                 "zabardast", "behtareen", "kamaal", "غلط", "صحیح", "درست", "بالکل ٹھیک", "ٹھیک کہا", "شاباش",
                 "زبردست", "بہترین", "کمال", "ग़लत", "गलत", "सही", "दुरुस्त", "शाबाश", "ज़बरदस्त", "बेहतरीन", "कमाल")


def _urdu_opening(role: str, who: dict | None) -> tuple[str, str, str]:
    """The Urdu greeting + "tell me about yourself", like opening_text()."""
    who = who or {}
    name = who.get("first_name")
    uni, subject = who.get("university"), who.get("subject")
    n = f" {name}" if name else ""
    hello = (f"السلام علیکم{n}، انٹرویو میں شامل ہونے کا شکریہ۔ آج کا انٹرویو {role} کی پوزیشن کے لیے ہے۔ یہ ایک "
             "عام گفتگو کی طرح ہوگا، اس لیے آرام سے اور قدرتی انداز میں جواب دیں۔",
             f"Assalam o Alaikum{n}, interview mein shamil hone ka shukriya. Aaj ka interview {role} ki position "
             "ke liye hai. Yeh ek aam guftagu ki tarah hoga, is liye aaram se aur qudrati andaaz mein jawab dein.",
             f"अस्सलाम ओ अलैकुम{n}, इंटरव्यू में शामिल होने का शुक्रिया। आज का इंटरव्यू {role} की पोज़िशन के लिए "
             "है। यह एक आम गुफ़्तगू की तरह होगा, इस लिए आराम से और क़ुदरती अंदाज़ में जवाब दें।")
    start = ("شروع کرنے کے لیے، اپنے بارے میں تھوڑا بتائیں: ", "Shuru karne ke liye, apne baare mein thora batayein: ",
             "शुरू करने के लिए, अपने बारे में थोड़ा बताइए: ")
    exp = ("اور اب تک آپ کا کیا تجربہ ہے؟", "aur ab tak aap ka kya tajurba hai?", "और अब तक आपका क्या तजुर्बा है?")
    if not uni:
        ask = ("آپ کون ہیں، کہاں پڑھ رہے ہیں یا پڑھا ہے، ", "aap kaun hain, kahan parh rahe hain ya parha hai, ",
               "आप कौन हैं, कहाँ पढ़ रहे हैं या पढ़ा है, ")
        cv = ("", "", "")
    else:
        sub = (f"{subject} ", f"{subject} ", f"{subject} ") if subject else ("", "", "")
        if who.get("studying") is None:
            cv = (f"آپ کی CV میں {uni} سے {sub[0]}تعلیم لکھی ہے۔ ", f"Aap ki CV mein {uni} se {sub[1]}taleem likhi hai. ",
                  f"आपकी CV में {uni} से {sub[2]}तालीम लिखी है। ")
        elif who.get("studying"):
            cv = (f"آپ کی CV کے مطابق آپ {uni} میں {sub[0]}پڑھ رہے ہیں۔ ",
                  f"Aap ki CV ke mutabiq aap {uni} mein {sub[1]}parh rahe hain. ",
                  f"आपकी CV के मुताबिक़ आप {uni} में {sub[2]}पढ़ रहे हैं। ")
        else:
            cv = (f"آپ کی CV کے مطابق آپ نے {uni} سے {sub[0]}پڑھا ہے۔ ",
                  f"Aap ki CV ke mutabiq aap ne {uni} se {sub[1]}parha hai. ",
                  f"आपकी CV के मुताबिक़ आपने {uni} से {sub[2]}पढ़ा है। ")
        ask = ("آپ نے پڑھائی میں کیا سیکھا، آپ کو سب سے زیادہ کس چیز میں دلچسپی ہے، ",
               "aap ne parhai mein kya seekha, aap ko sab se zyada kis cheez mein dilchaspi hai, ",
               "आपने पढ़ाई में क्या सीखा, आपको सबसे ज़्यादा किस चीज़ में दिलचस्पी है, ")
    return tuple(f"{hello[i]} {cv[i]}{start[i]}{ask[i]}{exp[i]}" for i in range(3))


def _line(kind: str, parts, topic_id, source: str, extra: dict | None = None) -> dict:
    """One thing the interviewer says. parts: an English string, or an Urdu (text, roman, hindi)."""
    if isinstance(parts, str):
        out = {"kind": kind, "text": parts}
    else:
        out = {"kind": kind, "text": parts[0], "roman": parts[1], "hindi": parts[2]}
    return out | {"topic_id": topic_id, "source": source} | (extra or {})


def _urdu(live: dict) -> bool:
    return live.get("language") == "ur"


# The voice the app found for an Urdu interview: "ur" (an Urdu voice reads Urdu script), "hi" (a Hindi
# voice reads Devanagari) or "none" (subtitles only). Gemini then writes only Roman Urdu (the subtitles)
# + the one script that voice reads: fewer words to write = a faster next question.
VOICES = ("ur", "hi", "none")


def _scripts(live: dict) -> tuple[str, ...]:
    """The forms Gemini writes besides Roman Urdu: "text" (Urdu script) and/or "hindi" (Devanagari).
    Unknown voice (an older app): both."""
    return {"ur": ("text",), "hi": ("hindi",), "none": ()}.get(live.get("voice"), ("text", "hindi"))


def _key(key: str, form: str) -> str:
    """The JSON field of one form: "question" (Urdu script), "question_roman", "question_hindi"."""
    return key if form == "text" else f"{key}_{form}"


@lru_cache(maxsize=None)
def _urdu_schema(base: type, keys: tuple[str, ...], scripts: tuple[str, ...]) -> type:
    """base + every key in Roman Urdu and in the scripts this voice needs."""
    fields = {_key(k, f): (str, ...) for k in keys for f in ("roman", *scripts)}
    return create_model(f"{base.__name__}Urdu_{'_'.join(scripts) or 'roman'}", __base__=base, **fields)


def _forms_text(keys: str, scripts: tuple[str, ...]) -> str:
    """Prompt text: which fields to write in which script. keys like "`reaction` / `question`"."""
    names = [k.strip(" `") for k in keys.split("/")]
    out = " / ".join(f"`{n}_roman`" for n in names) + " in Roman Urdu (e.g. 'Aap ne is mein kya kiya?')"
    if "text" in scripts:
        out += "; the SAME sentences in Urdu script as " + " / ".join(f"`{n}`" for n in names)
    if "hindi" in scripts:
        out += "; the SAME sentences in Devanagari (for a Hindi voice) as " + " / ".join(f"`{n}_hindi`"
                                                                                       for n in names)
    return out


def _join3(*parts) -> tuple[str, str, str]:
    """_join for (text, roman, hindi) tuples."""
    return tuple(_join(*(p[i] for p in parts if p)) for i in range(3))


def _planned(topic: dict, live: dict):
    """The planned question of a topic, in the interview's language. In Urdu: the translation made
    when the interview was created, else the English question (better than silence)."""
    if topic["id"] == "background":
        return URDU["background"] if _urdu(live) else BACKGROUND_QUESTION
    q = topic.get("question") or BACKGROUND_QUESTION
    if not _urdu(live):
        return q
    tr = topic.get("urdu")
    return (tr["text"], tr["roman"], tr["hindi"]) if tr else (q, q, q)


class _QuestionId(BaseModel):
    id: str


@lru_cache(maxsize=None)
def _questions_schema(scripts: tuple[str, ...]) -> type:
    """{questions: [{id, roman, (text), (hindi)}]}: text = Urdu script, hindi = Devanagari."""
    one = create_model(f"_UrduQuestion_{'_'.join(scripts) or 'roman'}", __base__=_QuestionId,
                       **{f: (str, ...) for f in ("roman", *scripts)})
    return create_model(f"_UrduQuestions_{'_'.join(scripts) or 'roman'}", questions=(list[one], ...))


def translate_agenda(live: dict) -> None:
    """Urdu interview: translate every planned question once, when the interview is created
    (ONE Gemini call), so the rule fallback can still ask in Urdu. Questions it can't
    translate stay in English."""
    private = live.get("private")
    todo = [t for t in live["agenda"] if t.get("question") and t["id"] != "background"]
    if not todo:
        return
    scripts = _scripts(live)
    lines = "\n".join(f"{t['id']}: {privacy.scrub(t['question'], private)}" for t in todo)
    extra = ("text (the same sentence in Urdu script)" if "text" in scripts else "",
             "hindi (the same spoken sentence in Devanagari, for a Hindi text-to-speech voice)"
             if "hindi" in scripts else "")
    extra = " and ".join(x for x in extra if x)
    out = llm.generate_json(
        "Translate these job-interview questions into natural, polite spoken Urdu, as a Pakistani "
        "interviewer would say them (address the candidate as 'aap'; keep technical terms, tool names and "
        "the role in English, as people do in Pakistan). For each give: roman (Roman Urdu, e.g. 'Aap ne is "
        f"project mein kya kiya?'){' and ' + extra if extra else ''}. Keep the ids. "
        f"{privacy.NOTE}\n\n{lines}",
        _questions_schema(scripts), tier="fast", temperature=0.2, timeout=25)
    by_id = {q.get("id"): q for q in (out or {}).get("questions", [])}
    for t in todo:
        q = by_id.get(t["id"]) or {}
        forms = {f: str(q.get(f) or "").strip()[:400] for f in ("roman", *scripts)}
        if all(forms.values()) and not any("[" in v for v in forms.values()):
            # a form the voice doesn't read is the Roman Urdu (never spoken, only stored)
            t["urdu"] = {k: forms.get(k, forms["roman"]) for k in ("text", "roman", "hindi")}


# ---------------------------------------------------------------- agenda --
def build_agenda(questions: list[dict], minutes: int) -> list[dict]:
    """Topics in interview order from the planned questions (Day 15)."""
    n = TOPICS_FOR.get(minutes, 7)
    body = [q for q in questions if q["type"] != "intro"][:n]
    agenda = [{"id": "opening", "type": "intro", "question": None, "key_points": [], "skill": None, "project": None},
              {"id": "background", "type": "background", "question": BACKGROUND_QUESTION, "skill": None, "project": None,
               "key_points": ["Clear summary of studies (degree, where, what stood out)",
                              "Relevant work, internship or project experience",
                              "What they learned and why it matters for the role"]}]
    agenda += [{k: q.get(k) for k in ("id", "type", "question", "key_points", "skill", "project")} for q in body]
    for t in agenda:
        t.update(status="pending", follow_ups=0)
    return agenda


def remaining_seconds(live: dict, now: float | None = None) -> float:
    started = live.get("started_at") or (now or time.time())
    return live["minutes"] * 60 - ((now or time.time()) - started)


def _pending(live: dict) -> list[dict]:
    return [t for t in live["agenda"] if t["status"] == "pending"]


def _current(live: dict) -> dict | None:
    return next((t for t in live["agenda"] if t["status"] == "current"), None)


# ---------------------------------------------------------------- Gemini --
class _Next(BaseModel):
    check: str           # mistake | vague | fine   (Gemini's silent check of the last answer)
    note: str            # the suspected mistake / missing detail, for the report (never spoken)
    action: str          # follow_up | next_topic | wrap_up
    reaction: str        # short natural reaction to the answer
    question: str        # what to ask now
    topic_id: str


# A real first-round interviewer never says an answer is wrong (or right) during the interview:
# it probes instead ("Are you sure?", "How is that different from ...?"). These words must
# never be spoken, whatever Gemini writes.
# Phrases that say an answer is wrong or right. Questions may still use words like "mistake",
# "what went wrong" or "what exactly" (normal interview questions), so only whole verdicts are listed.
VERDICTS = ("that's wrong", "that is wrong", "you're wrong", "you are wrong", "is wrong", "was wrong",
            "incorrect", "not correct", "isn't correct", "not quite right", "isn't right", "not true",
            "inaccurate", "that's correct", "that is correct", "you're right", "you are right", "that's right",
            "that is right", "great answer", "good answer", "excellent answer", "perfect answer", "well done",
            "spot on")
# A reaction is a short acknowledgement: anything that sounds like grading is replaced.
REACTION_EXTRA = ("wrong", "mistake", "mistaken", "correct", "exactly", "perfect", "excellent", "great",
                  "brilliant", "impressive", "actually", "in fact", "not quite")


def _has(text: str, phrases) -> bool:
    low = " ".join(text.lower().replace("’", "'").split())
    return any(p in low for p in phrases)


def _clean_reaction(text: str | None) -> str:
    """A neutral reaction: Gemini's if it doesn't judge the answer, else a plain one."""
    text = (text or "").strip()
    if not text or _has(text, VERDICTS + REACTION_EXTRA) or len(text.split()) > 12 or "[" in text:
        return random.choice(REACTIONS)
    return text


def _clean_question(text: str | None) -> str:
    """Drop any sentence that gives a verdict on the answer; '' if no real question is left."""
    import re
    text = (text or "").strip()
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    # a sentence with a verdict, or with a privacy placeholder like [company], is never spoken
    kept = [s for s in sentences if not _has(s, VERDICTS) and "[" not in s]
    if not kept:
        return ""
    if len(kept) < len(sentences) and not kept[-1].rstrip().endswith("?"):
        return ""                      # what is left after removing the verdict is not a question
    return " ".join(kept)


def _history(live: dict, limit: int = 8) -> str:
    """The recent conversation for the prompt, with personal details removed (privacy.py)."""
    private = live.get("private")
    lines = []
    for turn in live["turns"][-limit:]:
        lines.append(f"Interviewer: {privacy.scrub(turn['text'], private)}")
        ans = (turn.get("answer") or {}).get("transcript")
        if ans is not None:
            lines.append(f"Candidate: {privacy.scrub(ans[:700], private) or '(said nothing)'}")
    return "\n".join(lines)


def _prompt(live: dict, remaining: float) -> str:
    cur = _current(live)
    topics = "\n".join(
        f"- {t['id']} [{t['status']}] {t['type']}"
        + (f" (skill: {t['skill']})" if t.get("skill") else "")
        + (f" (their work: {t['project']})" if t.get("project") else "")
        + (f": planned question: {t['question']}" if t.get("question") else "")
        for t in live["agenda"])
    return (
        f"You are a calm, professional human interviewer running a live spoken interview for a "
        f"{live['role']} position ({live['level']} level), like a real first-round interview: polite, "
        f"neutral, attentive, not harsh. About {max(0, int(remaining // 60))} min "
        f"{int(remaining % 60)} s are left.\n"
        "FIRST, silently check the candidate's LAST answer and set `check`:\n"
        "- mistake: it contains a clear technical or factual error (e.g. 'Docker is a virtual machine', "
        "'HTTP is stateful'). Only when you are sure. The answer is speech-to-text, so a single odd word "
        "may just be misheard: that is NOT a mistake. Personal claims (their projects, jobs, grades, team "
        "size) can't be checked: never a mistake.\n"
        "- vague: no specifics (what THEY did, how, the result, an example).\n"
        "- fine: otherwise.\n"
        "Put in `note` one short sentence on the error or missing detail (for the written report, never "
        "spoken); empty if fine.\n"
        "THEN decide what to say next:\n"
        "- follow_up: stay on the same topic and probe. If check is mistake, ALWAYS follow up (when "
        "follow-ups are left) with a gentle probing question that lets them notice and fix it themselves, "
        "like a real interviewer: 'Are you sure about that?', 'How is a container different from a virtual "
        "machine?', 'Can you walk me through that step again?', 'What would happen if ...?'. NEVER say or "
        "hint that the answer is wrong or right, never give the correct answer, never argue or lecture. If "
        "check is vague, ask for the specific part (what you did, how, the result). You may also follow up on "
        "an interesting detail. If you already probed this same point and they kept their answer, don't "
        "probe it again: move on. "
        f"(Follow-ups used on this topic: {cur['follow_ups'] if cur else 0} of {MAX_FOLLOW_UPS}.)\n"
        "- next_topic: move to the next pending topic in the list. Rephrase its planned question naturally, "
        "and link it to what they said when it fits.\n"
        "- wrap_up: only when time is nearly over.\n"
        "Write `reaction`: a short neutral acknowledgement (max 10 words, e.g. 'Okay.', 'I see.', 'Alright, "
        "thank you.'). It must NOT judge the answer: no 'correct', 'exactly', 'great', 'wrong', 'actually'. "
        "Write `question`: ONE clear spoken question ending with '?', max 2 sentences, no lists, no code. "
        + (_urdu_prompt(_scripts(live)) if _urdu(live) else "Use plain English.\n")
        + "Give `topic_id` of the topic the question belongs to.\n"
        f"{privacy.NOTE}\n"
        f"TOPICS (in order):\n{topics}\n"
        f"CONVERSATION SO FAR:\n{_history(live)}")


def _urdu_prompt(scripts: tuple[str, ...]) -> str:
    return (
        "LANGUAGE: this interview is in URDU. The candidate answers in Urdu or mixed Urdu-English (speech-to-text "
        "in Urdu script; English words may appear in Urdu letters). Write the reaction and question in natural "
        "spoken Urdu, as a Pakistani interviewer talks: polite, addressing them as 'aap', keeping technical "
        f"terms, tool names and the role in English. Write {_forms_text('reaction / question', scripts)} "
        "(the rules above for `reaction` and `question` apply to every form). "
        "Don't use gendered words about yourself (say 'Theek hai', 'Shukriya', not 'samajh gaya'). The reaction "
        "must not judge either: no 'sahi', 'ghalat', 'zabardast', 'shabash', 'behtareen'. Write `note` in "
        "English.\n")


class _Decision(BaseModel):
    check: str
    note: str
    action: str
    topic_id: str


def _ask_gemini(live: dict, remaining: float) -> dict | None:
    urdu = _urdu(live)
    schema = _urdu_schema(_Decision, ("reaction", "question"), _scripts(live)) if urdu else _Next
    return llm.generate_json(_prompt(live, remaining), schema, tier="fast", temperature=0.6,
                             timeout=GEMINI_BUDGET, quick=True, hedge_after=GEMINI_HEDGE)


def _urdu_parts(out: dict | None, key: str, scripts: tuple[str, ...] = ("text", "hindi")) -> tuple[str, str, str] | None:
    """Gemini's Urdu (text, roman, hindi) for "reaction", "question" or "reply"; None if a form is
    missing, contains a privacy placeholder, or judges the answer. A form the voice doesn't read
    (not in scripts) is the Roman Urdu."""
    got = {f: str((out or {}).get(_key(key, f)) or "").strip() for f in ("roman", *scripts)}
    parts = tuple(got.get(f, got["roman"]) for f in ("text", "roman", "hindi"))
    if not all(parts) or any("[" in p or _has(p, VERDICTS + URDU_VERDICTS) for p in parts):
        return None
    return parts


def _urdu_reaction(out: dict | None, scripts: tuple[str, ...] = ("text", "hindi")) -> tuple[str, str, str]:
    parts = _urdu_parts(out, "reaction", scripts)
    if parts is None or len(parts[1].split()) > 12 or _has(parts[1], REACTION_EXTRA):
        return random.choice(URDU_REACTIONS)
    return parts


def _urdu_question(out: dict | None, scripts: tuple[str, ...] = ("text", "hindi")) -> tuple[str, str, str] | None:
    parts = _urdu_parts(out, "question", scripts)
    return parts if parts and parts[1].rstrip().endswith("?") else None


# --------------------------------------------------------------- decide --
def decide(live: dict, now: float | None = None, use_gemini: bool = True) -> dict:
    """The next thing the interviewer says: {kind, text, topic_id, source}.
    kind: question | follow_up | repeat | candidate_questions | goodbye.
    Also updates the agenda statuses in `live`."""
    remaining = remaining_seconds(live, now)
    cur = _current(live)
    last = live["turns"][-1] if live["turns"] else None
    answer = ((last or {}).get("answer") or {}).get("transcript", "") or ""

    # the closing sequence: candidate questions -> goodbye
    if last and last["kind"] == "candidate_questions":
        return _goodbye(live, answer)
    if last and last["kind"] == "goodbye":
        return {"kind": "end", "text": "", "topic_id": None, "source": "rules"}

    urdu = _urdu(live)
    # nothing heard: ask once more, then move on
    if len(answer.split()) < 3 and last and last["kind"] != "repeat":
        return _line("repeat", URDU["repeat"] if urdu else REPEAT, last.get("topic_id"), "rules")

    pending = _pending(live)
    if remaining < WRAP_UP_SECONDS or (not pending and (cur is None or cur["follow_ups"] >= MAX_FOLLOW_UPS)):
        return _wrap_up(live)

    out = _ask_gemini(live, remaining) if use_gemini else None
    check = _check(out)
    if urdu:
        scripts = _scripts(live)
        reaction, question, join = _urdu_reaction(out, scripts), _urdu_question(out, scripts), _join3
    else:
        reaction = _clean_reaction((out or {}).get("reaction"))
        question, join = _clean_question((out or {}).get("question")), _join
    can_follow = cur is not None and cur["follow_ups"] < MAX_FOLLOW_UPS and remaining > FOLLOW_UP_MIN_SECONDS \
        and len(answer.split()) >= 3
    if out and out.get("action") == "follow_up" and can_follow and question:
        cur["follow_ups"] += 1
        return _line("follow_up", join(reaction, question), cur["id"], "gemini", check)
    if not pending:
        return _wrap_up(live) | check
    # next topic: Gemini's choice if it is a pending topic, else the next one in order
    nxt = next((t for t in pending if out and t["id"] == out.get("topic_id")), pending[0])
    _set_current(live, nxt)
    if out and out.get("action") == "next_topic" and question and out.get("topic_id") == nxt["id"]:
        return _line("question", join(reaction, question), nxt["id"], "gemini", check)
    return _line("question", join(reaction, _planned(nxt, live)), nxt["id"], "gemini+plan" if out else "plan",
                 check)


def _check(out: dict | None) -> dict:
    """Gemini's silent check of the last answer, kept for the report (Day 21): {} when fine/unknown."""
    check = str((out or {}).get("check", "")).strip().lower()
    if check not in ("mistake", "vague"):
        return {}
    return {"check": check, "note": str(out.get("note", "")).strip()[:200]}


def start(live: dict) -> dict:
    """The first thing the interviewer says."""
    _set_current(live, live["agenda"][0])
    opening = (_urdu_opening if _urdu(live) else opening_text)(live["role"], live.get("candidate"))
    return _line("question", opening, "opening", "rules")


def _set_current(live: dict, topic: dict):
    for t in live["agenda"]:
        if t["status"] == "current":
            t["status"] = "done"
    topic["status"] = "current"


def _wrap_up(live: dict) -> dict:
    cur = _current(live)
    if cur:
        cur["status"] = "done"
    if _urdu(live):
        return _line("candidate_questions", _join3(random.choice(URDU_REACTIONS), URDU["candidate_questions"]),
                     None, "rules")
    return _line("candidate_questions", _join(random.choice(REACTIONS), CANDIDATE_QUESTIONS), None, "rules")


class _Reply(BaseModel):
    reply: str




# "No questions, thank you" in English and Urdu: then the interviewer just says goodbye
NO_QUESTIONS = ("no question", "no, thank", "nothing", "کوئی سوال نہیں", "نہیں، شکریہ", "نہیں شکریہ", "جی نہیں",
                "koi sawal nahi", "nahi shukriya")


def _goodbye(live: dict, answer: str) -> dict:
    """Answer the candidate's question briefly (Gemini), then say goodbye."""
    urdu = _urdu(live)
    reply = None
    if len(answer.split()) >= 4 and not _has(answer, NO_QUESTIONS):
        scripts = _scripts(live)
        lang = (f"Reply in polite spoken Urdu (technical terms in English): write {_forms_text('reply', scripts)}. "
                if urdu else "")
        out = llm.generate_json(
            f"You are a friendly interviewer for a {live['role']} position at a typical company. At the end of "
            f"the interview the candidate asked: \"{privacy.scrub(answer[:500], live.get('private'))}\". Reply in "
            "at most 2 short spoken sentences, honest and general (you don't know this company's private "
            f"details; say the team will share specifics in the next round if needed). {lang}{privacy.NOTE}",
            _urdu_schema(BaseModel, ("reply",), scripts) if urdu else _Reply, tier="fast", temperature=0.5,
            timeout=GEMINI_BUDGET)
        if urdu:
            reply = _urdu_parts(out, "reply", scripts) or URDU["no_answer_reply"]
        else:
            reply = (out or {}).get("reply", "").strip()
            if not reply or "[" in reply:
                reply = NO_ANSWER_REPLY
    source = "gemini" if reply else "rules"
    if urdu:
        return _line("goodbye", _join3(reply, URDU["goodbye"]), None, source)
    return _line("goodbye", _join(reply, GOODBYE), None, source)


def _join(*parts) -> str:
    return " ".join(str(p).strip() for p in parts if p and str(p).strip())
