"""Step 2 of the Resume Intelligence pipeline: sections → structured entities.

spaCy pipeline = en_core_web_sm (statistical NER: PERSON, ORG, GPE, DATE)
               + an EntityRuler holding about 450 skills / 630 spellings from data/skills.json
Rule-based extractors handle education, experience, projects, languages
and certifications. If the rules find too little, Gemini fills only the gaps.
"""
import json
import re
import threading
from datetime import date
from functools import lru_cache

import spacy
from dateutil import parser as dateparser
from pydantic import BaseModel

from app.config import DATA_DIR
from app.services import llm
from app.services.pdf_parser import detect_heading

# Single words that are also ordinary English words or names. They only
# count when written with the exact capitalisation from skills.json.
CASE_SENSITIVE = {
    "REST", "Node", "Rails", "Lambda", "Shell", "Spark", "Unity", "Swift", "Rust", "Dart",
    "Sketch", "Chef", "Puppet", "Oracle", "Chroma", "Apache", "Excel", "Jest", "Mocha", "Cucumber",
    "Postman", "Cypress", "Playwright", "Illustrator", "Blender", "Waterfall", "Transformers",
    "Gemini", "Whisper", "SAS", "SAP", "DOM", "Vite", "Sales", "Kafka", "Helm", "Looker", "Prisma",
}
LIST_CONTEXT = {",", "/", "|", "(", ")", "and", "&", ";", ":", "•", "·"}
BULLET_RE = re.compile(r"^\s*[•\-\*▪●◦‣–o]\s+")


def _prep(text: str) -> str:
    """Put spaces around separators so 'Python/Django|SQL' tokenizes cleanly."""
    text = re.sub(r"(?<=\w)/(?=\w)", " / ", text)
    return re.sub(r"\s*([|•·])\s*", r" \1 ", text)


# ------------------------------------------------------------- spaCy model --
# The skill list = data/skills.json (the base list, hand-checked) + skills the app learned
# from live job postings (market_learning.py, confirmed by Gemini, removable by an admin).
# Learned skills are swapped in while the server runs: no restart, no redeploy.
_learned: list[dict] = []                 # [{"name", "category", "aliases"}]
_built: dict = {}                         # "nlp", "matchers" (built lazily, swapped on reload)
_build_lock = threading.Lock()
_version = 0


@lru_cache(maxsize=1)
def _base_vocab() -> dict:
    return json.loads((DATA_DIR / "skills.json").read_text(encoding="utf-8"))


def _canon(entry: str) -> str:
    return entry.lstrip("!").split("|")[0]


def _merged_vocab(learned: list[dict]) -> dict[str, list[str]]:
    vocab = {cat: list(lst) for cat, lst in _base_vocab().items() if not cat.startswith("_")}
    where = {_canon(e).lower(): (cat, i) for cat, lst in vocab.items() for i, e in enumerate(lst)}
    for s in learned:
        name = str(s.get("name", "")).strip()
        if not name or "|" in name:
            continue
        aliases = [a.strip() for a in s.get("aliases") or [] if a and a.strip() and "|" not in a]
        if name.lower() in where:                       # a new spelling of a skill we know
            cat, i = where[name.lower()]
            have = {a.lower() for a in vocab[cat][i].lstrip("!").split("|")}
            vocab[cat][i] += "".join("|" + a for a in aliases if a.lower() not in have)
        elif s.get("category") in vocab:                # a brand-new skill
            vocab[s["category"]].append("|".join(dict.fromkeys([name, *aliases])))
            where[name.lower()] = (s["category"], len(vocab[s["category"]]) - 1)
    return vocab


def skill_vocab() -> dict[str, list[str]]:
    """{category: ['Canonical|alias', ...]} including learned skills."""
    if "vocab" not in _built:
        _ensure_built()
    return _built["vocab"]


def vocab_version() -> int:
    """Changes every time learned skills are reloaded (for caches elsewhere)."""
    return _version


def _build(learned: list[dict]) -> dict:
    from spacy.matcher import PhraseMatcher
    vocab = _merged_vocab(learned)
    nlp = spacy.load("en_core_web_sm", disable=["lemmatizer"])
    ruler = nlp.add_pipe("entity_ruler", before="ner", config={"phrase_matcher_attr": None})
    lower, exact = PhraseMatcher(nlp.vocab, attr="LOWER"), PhraseMatcher(nlp.vocab, attr="ORTH")
    patterns = []
    for category, entries in vocab.items():
        for entry in entries:
            needs_context = entry.startswith("!")
            names = entry.lstrip("!").split("|")
            skill_id = f"{category}::{names[0]}" + ("::ctx" if needs_context else "")
            for alias in names:
                tokens = nlp.make_doc(_prep(alias))
                is_exact = needs_context or alias in CASE_SENSITIVE
                key = "ORTH" if is_exact else "LOWER"
                patterns.append({"label": "SKILL", "id": skill_id,
                                 "pattern": [{key: t.text if is_exact else t.lower_} for t in tokens if not t.is_space]})
                (exact if is_exact else lower).add(skill_id, [tokens])
    ruler.add_patterns(patterns)
    return {"nlp": nlp, "matchers": (nlp, lower, exact), "vocab": vocab}


def _ensure_built():
    with _build_lock:
        if "nlp" not in _built:
            _built.update(_build(_learned))


def set_learned_skills(learned: list[dict]):
    """Load a new list of learned skills. The new detector is built first and then
    swapped in, so requests running meanwhile keep using the old one."""
    global _learned, _version
    learned = [dict(s) for s in learned]
    if learned == _learned and "nlp" in _built:
        return
    new = _build(learned)
    with _build_lock:
        _learned = learned
        _built.clear()
        _built.update(new)
        _version += 1


def get_nlp():
    if "nlp" not in _built:
        _ensure_built()
    return _built["nlp"]


def _has_list_context(ent) -> bool:
    doc = ent.doc
    prev = doc[ent.start - 1].text if ent.start > 0 else ""
    nxt = doc[ent.end].text if ent.end < len(doc) else ""
    if nxt in {"&", "'s"}:  # "R&D", "C's"
        return False
    return prev in LIST_CONTEXT or nxt in LIST_CONTEXT


def find_skills(text: str, in_skills_section: bool = False) -> dict[str, dict]:
    """Return {canonical: {category, mentions}} for skills in text."""
    found: dict[str, dict] = {}
    for ent in get_nlp()(_prep(text)).ents:
        if ent.label_ != "SKILL":
            continue
        category, canonical, *flag = ent.ent_id_.split("::")
        if flag and not (in_skills_section or _has_list_context(ent)):
            continue
        item = found.setdefault(canonical, {"category": category, "mentions": 0})
        item["mentions"] += 1
    return found


def _phrase_matchers():
    """Same skills as the EntityRuler, but as spaCy PhraseMatchers (one case-insensitive,
    one exact-case). Much faster for exact phrases; used for bulk job postings."""
    if "matchers" not in _built:
        _ensure_built()
    return _built["matchers"]


def find_skills_batch(texts, batch_size: int = 256):
    """Fast version for thousands of job postings: tokenizer + PhraseMatcher only
    (no tagger/parser/NER). Yields one {canonical: category} dict per text."""
    from spacy.util import filter_spans
    nlp, lower, exact = _phrase_matchers()
    for doc in nlp.tokenizer.pipe((_prep(t) for t in texts), batch_size=batch_size):
        matches = list(lower(doc)) + list(exact(doc))
        spans = [doc[s:e] for _, s, e in matches]
        ids = {(s, e): nlp.vocab.strings[m] for m, s, e in matches}
        found = {}
        for span in filter_spans(spans):      # longest match wins, like the EntityRuler
            category, canonical, *flag = ids[(span.start, span.end)].split("::")
            if flag and not _has_list_context(span):
                continue
            found[canonical] = category
        yield found


# ------------------------------------------------------------------- dates --
MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|"
         r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
DATE = rf"(?:{MONTH},?\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
PRESENT = r"(?:Present|Current|Currently|Now|Ongoing|Till\s+Date|To\s+Date|Date)"
RANGE_RE = re.compile(rf"({DATE})\s*(?:–|—|-|to|until|till)\s*({DATE}|{PRESENT})", re.I)
YEAR_RE = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")


def _to_date(s: str) -> date | None:
    s = s.strip()
    if re.fullmatch(PRESENT, s, re.I):
        return date.today()
    try:
        if re.fullmatch(r"\d{4}", s):
            return date(int(s), 1, 1)
        return dateparser.parse(s, default=dateparser.parse("2000-01-01")).date()
    except (ValueError, OverflowError):
        return None


def _months_between(a: date, b: date) -> int:
    return max(0, (b.year - a.year) * 12 + (b.month - a.month) + 1)


# --------------------------------------------------------------- education --
DEGREE_PATTERNS = [
    ("PhD", re.compile(r"\b(Ph\.?\s?D|Doctorate|Doctor of Philosophy)\b", re.I)),
    ("Masters", re.compile(r"\b(MBA|M\.?Phil|MSc|M\.Sc|MSCS|MS(?=\s+(in|of|-)\b)|M\.S\.|M\.?Tech|ME(?=\s+in\b)|Master'?s?)\b")),
    ("Bachelors", re.compile(r"\b(BSc|B\.Sc|BSCS|BSSE|BSIT|BSE|BS|B\.S\.|BE|B\.E\.|B\.?Tech|BBA|BCS|Bachelor'?s?)\b")),
    ("Intermediate", re.compile(r"\b(F\.?Sc|FSc|ICS|I\.Com|HSSC|Intermediate|A[\s-]?Levels?)\b", re.I)),
    ("Matriculation", re.compile(r"\b(Matric(?:ulation)?|SSC|O[\s-]?Levels?)\b", re.I)),
]
INSTITUTION_RE = re.compile(
    r"((?:[A-Z][\w.&'-]*\s+){0,5}(?:University|Institute|College|School|Academy|Polytechnic)"
    r"(?:\s+of\s+(?:[A-Z][\w.&'-]*\s?){1,4})?(?:,?\s+[A-Z][a-z]+)?)"
    r"|\b(NUST|LUMS|IBA|FAST(?:-NUCES)?|NUCES|NED|COMSATS|GIKI|SZABIST|UET|PIEAS|KU|SSUET|PAF-KIET)\b"
)
FIELD_RE = re.compile(r"\b(?:of|in)\s+([A-Z][A-Za-z &]+?)(?=\s*(?:[,·|–\-(]|\bfrom\b|\bat\b|$))")
CGPA_RE = re.compile(r"\b(?:C?GPA)\s*[:\-]?\s*([0-4]\.\d{1,2})(?:\s*/\s*4(?:\.0+)?)?", re.I)
PERCENT_RE = re.compile(r"\b(\d{2}(?:\.\d+)?)\s*%")


def extract_education(text: str) -> list[dict]:
    entries: list[dict] = []
    for line in text.splitlines():
        clean = BULLET_RE.sub("", line).strip()
        if not clean:
            continue
        level = next((lvl for lvl, rx in DEGREE_PATTERNS if rx.search(clean)), None)
        inst = INSTITUTION_RE.search(clean)
        if level or (inst and not entries):
            field = FIELD_RE.search(clean)
            years = YEAR_RE.findall(clean)
            entries.append({
                "degree_level": level,
                "degree": clean.split("·")[0].split(" - ")[0].strip()[:120] if level else None,
                "field": field.group(1).strip() if field else None,
                "institution": (inst.group(0).strip(" ,") if inst else None),
                "start_year": int(years[0]) if len(years) > 1 else None,
                "end_year": int(years[-1]) if years else None,
                "expected": bool(re.search(r"\bexpected\b|\bin progress\b|\bongoing\b", clean, re.I)),
                "cgpa": None, "percentage": None,
            })
            cur = entries[-1]
        elif entries:
            cur = entries[-1]
            if not cur["institution"] and inst:
                cur["institution"] = inst.group(0).strip(" ,")
            if not cur["end_year"] and (y := YEAR_RE.findall(clean)):
                cur["end_year"] = int(y[-1])
        else:
            continue
        if (g := CGPA_RE.search(clean)) and not cur["cgpa"]:
            cur["cgpa"] = float(g.group(1))
        if (p := PERCENT_RE.search(clean)) and not cur["percentage"]:
            cur["percentage"] = float(p.group(1))
    return entries


# -------------------------------------------------------------- experience --
ORG_WORDS_RE = re.compile(
    r"\b(company|ltd|limited|inc|llc|corp|corporation|pvt|private|group|bank|hospital|university|"
    r"college|institute|school|technologies|technology|solutions|systems|services|consulting|labs|"
    r"agency|foundation|organization|organisation|ministry|authority|enterprises|industries)\b|\([A-Z]{2,6}\)", re.I)
ROLE_WORDS_RE = re.compile(
    r"\b(intern|internship|engineer|developer|manager|analyst|leader|lead|officer|designer|assistant|"
    r"consultant|specialist|associate|executive|coordinator|administrator|architect|scientist|"
    r"technician|teacher|lecturer|nurse|accountant|volunteer|trainee|director|head|supervisor)\b", re.I)


def _split_title_company(text: str) -> tuple[str, str | None]:
    for sep in (" at ", " @ ", " | ", " · ", " — ", " – ", " - ", ", "):
        if sep in text:
            a, b = (x.strip() for x in text.split(sep, 1))
            if sep not in (" at ", " @ "):
                # "National Bank of Pakistan (NBP) - IT Intern | Karachi": the org/role pair is inside `a`
                for inner in (" — ", " – ", " - "):
                    if inner in a:
                        a1, a2 = (x.strip() for x in a.split(inner, 1))
                        if ORG_WORDS_RE.search(a1) and ROLE_WORDS_RE.search(a2) and not ROLE_WORDS_RE.search(a1):
                            return a2, a1
                        break
            # "Fauji Fertilizer Company (FFC) | IT Intern" → title first, company second
            if sep not in (" at ", " @ ") and ORG_WORDS_RE.search(a) and ROLE_WORDS_RE.search(b) \
                    and not ROLE_WORDS_RE.search(a):
                a, b = b, a
            return a, b
    return text.strip(), None


SINGLE_DATE_RE = re.compile(rf"\(?\s*({DATE}|{PRESENT})\s*\)?\s*$", re.I)
_HEADER_SEPS = (" | ", " - ", " – ", " — ", " at ", " @ ")


def _looks_like_job_header(line: str) -> bool:
    """'Fauji Fertilizer (FFC) | IT Intern (2025)' or 'NBP - IT Intern | Karachi':
    a short, capitalised, non-sentence line with a separator or a trailing year."""
    return (len(line.split()) <= 20 and line[0].isupper() and not line.endswith((".", ",", ";"))
            and (any(sep in line for sep in _HEADER_SEPS) or bool(SINGLE_DATE_RE.search(line))))


def _new_entry(title, company, start_s, end_s, single: bool = False) -> dict:
    start, end = (_to_date(start_s) if start_s else None), (_to_date(end_s) if end_s else None)
    return {
        "title": title or None, "company": company, "start": start_s, "end": end_s,
        "current": bool(end_s and re.fullmatch(PRESENT, end_s.strip(), re.I)),
        "months": _months_between(start, end) if start and end and not single else None,
        "bullets": [], "_start": start, "_end": end,
    }


def extract_experience(text: str) -> list[dict]:
    """A line with a date range starts a new job entry. A short header-like line
    ('Company | Role (2025)', 'Company - Role') also starts one when it comes
    first or right after the previous job's bullets."""
    entries: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        is_bullet = bool(BULLET_RE.match(stripped))
        rng = None if is_bullet else RANGE_RE.search(stripped)
        if (not rng and not is_bullet and (not entries or entries[-1]["bullets"])
                and _looks_like_job_header(stripped)):
            single = SINGLE_DATE_RE.search(stripped)
            head = stripped[:single.start()] if single else stripped
            title, company = _split_title_company(head.strip(" ,|·–-()"))
            when = single.group(1) if single else None
            entries.append(_new_entry(title, company, when, when, single=True))
            continue
        if rng:
            head = (stripped[:rng.start()] + stripped[rng.end():]).strip(" ,|·–-()")
            title, company = _split_title_company(head) if head else ("", None)
            last = entries[-1] if entries else None
            if last and not last["bullets"] and not last["start"] and not head:
                # 'Role | Company' line, then the dates on the next line → same job
                entries[-1] = _new_entry(last["title"], last["company"], rng.group(1), rng.group(2))
            else:
                entries.append(_new_entry(title, company, rng.group(1), rng.group(2)))
        elif entries:
            cur = entries[-1]
            if is_bullet:
                cur["bullets"].append(BULLET_RE.sub("", stripped))
            elif not cur["bullets"] and cur["company"] is None:
                cur["company"] = stripped.split("·")[0].strip()
            elif not cur["bullets"] and not cur["title"]:
                cur["title"] = stripped
            elif cur["bullets"]:
                cur["bullets"][-1] += " " + stripped  # wrapped bullet line
    return entries


def total_experience_months(entries: list[dict]) -> int:
    """Count each calendar month once, so overlapping jobs aren't double counted."""
    months: set[tuple[int, int]] = set()
    for e in entries:
        a, b = e.get("_start"), e.get("_end")
        if not a or not b or b < a:
            continue
        y, m = a.year, a.month
        while (y, m) <= (b.year, b.month):
            months.add((y, m))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return len(months)


# ---------------------------------------------------------------- projects --
def _looks_like_title(line: str) -> bool:
    """Project titles are short, start with a capital/digit and aren't sentences.
    Wrapped bullet text ('+ Grafana monitoring.', 'response-time trends…') is not."""
    return (len(line.split()) <= 12 and (line[0].isupper() or line[0].isdigit())
            and not line.rstrip().endswith((".", ",", ";")))


def _clean_title(line: str) -> str:
    title = re.sub(r"\(?\s*\b(19|20)\d{2}\b\s*\)?", " ", line)  # drop years like "2026" / "(2026)"
    title = re.sub(r"\s+", " ", title).strip(" |·–-")
    if title.count("(") > title.count(")"):
        title += ")"
    return title[:100]


def extract_projects(text: str) -> list[dict]:
    projects: list[dict] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if BULLET_RE.match(s):
            if projects:
                projects[-1]["description"].append(BULLET_RE.sub("", s))
        elif not projects or _looks_like_title(s):
            projects.append({"title": _clean_title(s), "description": []})
        elif projects[-1]["description"]:
            projects[-1]["description"][-1] += " " + s  # wrapped line of the previous bullet
        else:
            projects[-1]["description"].append(s)
    for p in projects:
        p["skills"] = sorted(find_skills(p["title"] + "\n" + "\n".join(p["description"])))
    return projects


# ------------------------------------------------------------- misc fields --
LANGUAGES = ["English", "Urdu", "Punjabi", "Sindhi", "Pashto", "Balochi", "Saraiki", "Arabic", "French",
             "German", "Chinese", "Mandarin", "Spanish", "Turkish", "Persian", "Hindi", "Japanese", "Korean",
             "Italian", "Russian", "Portuguese"]
LANG_RE = re.compile(r"\b(" + "|".join(LANGUAGES) + r")\b")
NAME_RE = re.compile(r"^[A-Z][a-zA-Z.'-]+(?:\s+[A-Z][a-zA-Z.'-]+){1,3}$")
PK_CITIES = ["Karachi", "Lahore", "Islamabad", "Rawalpindi", "Faisalabad", "Multan", "Peshawar", "Quetta",
             "Hyderabad", "Sialkot", "Gujranwala", "Sukkur"]


def extract_name_headline_location(header: str) -> tuple[str | None, str | None, str | None]:
    lines = [l.strip() for l in header.splitlines() if l.strip()]
    name = next((l for l in lines[:3] if NAME_RE.match(l)), None)
    # A one-word name ("AQEEL") on the very first line
    if not name and lines and re.fullmatch(r"[A-Z][A-Za-z'-]{2,20}", lines[0]) and not detect_heading(lines[0]):
        name = lines[0]
    headline = None
    if name:
        idx = lines.index(name)
        if idx + 1 < len(lines):
            cand = lines[idx + 1]
            if not re.search(r"[@\d|]|linkedin|github|http", cand, re.I) and len(cand.split()) <= 10:
                headline = cand
    doc = get_nlp()(header)
    if not name:
        name = next((e.text for e in doc.ents if e.label_ == "PERSON"), None)
    gpes = []
    for e in doc.ents:
        if e.label_ == "GPE" and e.text not in gpes:
            gpes.append(e.text)
    location = ", ".join(gpes[:2]) or next((c for c in PK_CITIES if c in header), None)
    return name, headline, location


def extract_languages(sections: dict[str, str]) -> list[str]:
    text = sections.get("languages", "")
    text += "\n" + "\n".join(l for l in "\n".join(sections.values()).splitlines() if "language" in l.lower())
    return sorted(set(LANG_RE.findall(text)))


def _lines(text: str, limit: int = 15) -> list[str]:
    return [BULLET_RE.sub("", l).strip() for l in text.splitlines() if l.strip()][:limit]


# --------------------------------------------------------- Gemini fallback --
class _LLMJob(BaseModel):
    title: str
    company: str
    start: str
    end: str
    bullets: list[str]


class _LLMEdu(BaseModel):
    degree: str
    field: str
    institution: str
    end_year: int


class _LLMResume(BaseModel):
    name: str
    skills: list[str]
    experience: list[_LLMJob]
    education: list[_LLMEdu]


def _llm_fill(text: str) -> dict | None:
    prompt = (
        "Extract structured data from this resume. Use empty strings or empty lists "
        "for anything not present. Do not invent information.\n\nRESUME:\n" + text[:12000]
    )
    return llm.generate_json(prompt, _LLMResume, tier="fast")


# -------------------------------------------------------------------- main --
def extract_entities(sections: dict[str, str], full_text: str) -> dict:
    skills: dict[str, dict] = {}
    for sec_name, sec_text in sections.items():
        for name, info in find_skills(sec_text, in_skills_section=(sec_name == "skills")).items():
            item = skills.setdefault(name, {"name": name, "category": info["category"],
                                            "mentions": 0, "sections": []})
            item["mentions"] += info["mentions"]
            item["sections"].append(sec_name)

    name, headline, location = extract_name_headline_location(sections.get("header", ""))
    education = extract_education(sections.get("education", ""))
    experience = extract_experience(sections.get("experience", ""))
    total_months = total_experience_months(experience)

    # Gemini fills ONLY what the rules missed
    llm_used: list[str] = []
    needs = {
        "name": not name,
        "skills": len(skills) < 3,
        "experience": "experience" in sections and not experience,
        "education": "education" in sections and not education,
    }
    if any(needs.values()) and (data := _llm_fill(full_text)):
        if needs["name"] and data.get("name"):
            name, llm_used = data["name"], llm_used + ["name"]
        if needs["skills"]:
            for s in data.get("skills", []):
                hit = find_skills(s, in_skills_section=True)
                canon, info = next(iter(hit.items())) if hit else (s.strip(), {"category": "other"})
                skills.setdefault(canon, {"name": canon, "category": info["category"],
                                          "mentions": 1, "sections": ["llm"]})
            llm_used.append("skills")
        if needs["experience"] and data.get("experience"):
            experience = [{**j, "current": bool(re.fullmatch(PRESENT, j["end"], re.I)), "months": None}
                          for j in data["experience"]]
            llm_used.append("experience")
        if needs["education"] and data.get("education"):
            education = [{"degree_level": None, "degree": e["degree"], "field": e["field"],
                          "institution": e["institution"], "end_year": e["end_year"] or None,
                          "start_year": None, "expected": False, "cgpa": None, "percentage": None}
                         for e in data["education"]]
            llm_used.append("education")

    for e in experience:  # internal date objects aren't JSON/Firestore friendly
        e.pop("_start", None)
        e.pop("_end", None)

    return {
        "name": name,
        "headline": headline,
        "location": location,
        "skills": sorted(skills.values(), key=lambda s: (-s["mentions"], s["name"])),
        "education": education,
        "experience": experience,
        "total_experience_months": total_months,
        "projects": extract_projects(sections.get("projects", "")),
        "certifications": _lines(sections.get("certifications", "")),
        "achievements": _lines(sections.get("achievements", "")),
        "languages": extract_languages(sections),
        "extraction_method": "spacy+rules" + ("+gemini" if llm_used else ""),
        "llm_filled": llm_used,
    }
