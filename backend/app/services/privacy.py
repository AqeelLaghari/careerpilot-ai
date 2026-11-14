"""Remove personal details from text before it is sent to Gemini.

Spoken answers can contain the user's name, email, phone number, city or the companies they
worked at. The project rule: none of these go to an outside AI service. Before a transcript
is put in a prompt, they are replaced with placeholders like [name] or [company]; the AI
still understands the answer ("I worked at [company] as an intern").
"""
import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
# phone numbers: 10+ digits, allowing spaces, dashes, brackets and a leading +
PHONE = re.compile(r"\+?\d[\d\s\-()]{8,}\d")
NOTE = ("Words in [square brackets] were removed for privacy. Never say or guess them; say "
        "'your company', 'your university' or just 'you' instead.")


def terms(entities: dict | None) -> list[dict]:
    """[{"p": placeholder, "w": word}, ...] from the CV: name parts, location, company names.
    (Dicts, not pairs: Firestore can't store lists inside lists.)"""
    e = entities or {}
    out = []
    for part in re.split(r"\s+", str(e.get("name") or "")):
        part = part.strip(".,")
        if len(part) >= 3:
            out.append(["[name]", part])
    loc = str(e.get("location") or "").strip()
    for part in re.split(r"[,/|]", loc):
        if len(part.strip()) >= 3:
            out.append(["[place]", part.strip()])
    for job in e.get("experience") or []:
        company = str(job.get("company") or "").strip()
        if len(company) >= 3:
            out.append(["[company]", company])
    # longest first, so "Acme Labs" is replaced before "Acme"
    unique = sorted({(p, w) for p, w in out}, key=lambda t: -len(t[1]))
    return [{"p": p, "w": w} for p, w in unique]


def scrub(text: str, private: list | None) -> str:
    """Replace emails, phone numbers and the user's own private words in text."""
    if not text:
        return text or ""
    text = EMAIL.sub("[email]", text)
    text = PHONE.sub("[phone]", text)
    for t in private or []:
        text = re.sub(rf"(?<!\w){re.escape(t['w'])}(?!\w)", t["p"], text, flags=re.I)
    return text
