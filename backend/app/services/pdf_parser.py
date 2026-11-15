"""Step 1 of the Resume Intelligence pipeline: PDF → clean, ordered text.

PyMuPDF reads every text line with its position, font size and boldness.
pdfplumber detects tables (ATS systems often garble these) and is a fallback
reader when PyMuPDF finds little text.

Output: ordered text, section split, contact details and a layout report.
The ATS scorer (Day 6) uses the layout report.
"""
import io
import re
import statistics

import pdfplumber
import pymupdf

MAX_PDF_BYTES = 5 * 1024 * 1024  # 5 MB


class PDFError(ValueError):
    """Raised for files we can't read (not a PDF, corrupt, locked, too big)."""


# ---------------------------------------------------------------- headings --
SECTION_HEADINGS = {
    "summary": ["summary", "professional summary", "profile", "about me", "about", "objective",
                "career objective", "professional profile", "personal statement", "career summary",
                "executive summary", "summary of qualifications",
                "career profile", "professional overview", "introduction"],
    "experience": ["experience", "work experience", "professional experience", "employment",
                   "employment history", "work history", "internships", "internship",
                   "internship experience", "relevant experience", "career history", "professional background",
                   "positions held", "work", "teaching experience", "clinical experience", "field experience",
                   "industry experience", "employment record", "job history"],
    "education": ["education", "academic background", "academics", "educational background",
                  "education and qualifications", "academic qualifications", "qualifications",
                  "academic history", "educational qualifications", "academic record", "education history"],
    "skills": ["skills", "technical skills", "core skills", "key skills", "skills and tools",
               "competencies", "core competencies", "technologies", "tools and technologies",
               "technical expertise", "skill set", "skills and abilities", "soft skills",
               "areas of expertise", "it skills", "computer skills", "professional skills", "technical proficiencies",
               "expertise", "key competencies", "tools", "strengths", "technical skills and tools"],
    "projects": ["projects", "academic projects", "personal projects", "key projects",
                 "selected projects", "project experience", "final year project", "portfolio",
                 "major projects", "university projects", "fyp", "capstone project"],
    "certifications": ["certifications", "certificates", "licenses and certifications",
                       "courses", "training", "certifications and courses", "online courses",
                       "trainings", "workshops", "seminars", "workshops and seminars", "professional development",
                       "courses and certifications", "licenses"],
    "achievements": ["achievements", "awards", "honors", "honours", "awards and achievements",
                     "accomplishments", "awards and honors", "key achievements",
                     "honors and awards", "scholarships", "awards and scholarships"],
    "languages": ["languages", "language"],
    "interests": ["interests", "hobbies", "hobbies and interests"],
    "publications": ["publications", "research", "research experience", "conferences",
                     "research interests", "papers"],
    "volunteer": ["volunteer", "volunteering", "volunteer experience", "extracurricular activities",
                  "extra curricular activities", "extracurriculars", "leadership",
                  "leadership and activities", "activities",
                  "memberships", "affiliations", "professional memberships", "societies", "community service"],
    "references": ["references", "referees"],
    "personal": ["personal information", "personal details", "personal data", "personal profile",
                 "personal info", "contact", "contact information", "contact details"],
}
# Singular forms ("ACHIEVEMENT", "REFERENCE", "PROJECT") are common on templates
SINGULARS = {"achievement": "achievements", "award": "achievements", "reference": "references",
             "project": "projects", "certification": "certifications", "certificate": "certifications",
             "skill": "skills", "publication": "publications", "hobby": "interests", "interest": "interests",
             "activity": "volunteer", "key achievement": "achievements", "academic project": "projects",
             "personal project": "projects", "work experiences": "experience", "experiences": "experience",
             "educations": "education", "course": "certifications", "honor": "achievements", "accomplishment": "achievements"}
_HEADING_LOOKUP = {h: canon for canon, names in SECTION_HEADINGS.items() for h in names}
_HEADING_LOOKUP.update({k: v for k, v in SINGULARS.items() if k not in _HEADING_LOOKUP})
# "T E C H N I C A L S K I L L S" collapses to "technicalskills", so we also look up without spaces
_HEADING_NOSPACE = {h.replace(" ", ""): canon for h, canon in _HEADING_LOOKUP.items()}


def _normalize_heading(text: str) -> str:
    t = text.strip()
    # "E X P E R I E N C E" → "EXPERIENCE"
    tokens = t.split()
    if len(tokens) >= 4 and all(len(tok) == 1 for tok in tokens):
        t = "".join(tokens)
    t = t.lower().replace("&", " and ")
    t = re.sub(r"[^a-z ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def detect_heading(text: str) -> str | None:
    """Return the canonical section name if this line is a section heading."""
    if len(text) > 60:
        return None
    norm = _normalize_heading(text)
    if len(norm.split()) > 6:
        return None
    return _HEADING_LOOKUP.get(norm) or _HEADING_NOSPACE.get(norm.replace(" ", ""))


# ----------------------------------------------------------------- contact --
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s\-().]{8,}\d)")
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/[\w\-%.]+/?", re.I)
GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w\-]+/?", re.I)
URL_RE = re.compile(r"https?://[^\s,;|]+", re.I)


def extract_contact(text: str, links: list[str]) -> dict:
    blob = text + "\n" + "\n".join(links)
    phones = []
    for m in PHONE_RE.findall(text):
        digits = re.sub(r"\D", "", m)
        if 10 <= len(digits) <= 15 and not re.fullmatch(r"(19|20)\d{2}\D+(19|20)\d{2}", m.strip()):
            phones.append(m.strip())
    linkedin = LINKEDIN_RE.search(blob)
    github = GITHUB_RE.search(blob)
    emails = EMAIL_RE.findall(blob.replace("mailto:", " "))
    others = [u for u in set(URL_RE.findall(blob))
              if "linkedin.com" not in u.lower() and "github.com" not in u.lower()]
    return {
        "email": emails[0] if emails else None,
        "phone": phones[0] if phones else None,
        "linkedin": linkedin.group(0) if linkedin else None,
        "github": github.group(0) if github else None,
        "websites": sorted(others)[:5],
    }


# ------------------------------------------------------------------ layout --
ZERO_WIDTH_RE = re.compile(r"[​‌‍⁠﻿­]")
# Word/Canva bullets often come from Symbol/Wingdings fonts as private-use characters
BULLET_GLYPHS = "▪■●◦‣➢►❖➔✓✔∙◆◇⁃"
_BULLET_GLYPH_RE = re.compile(f"^[{BULLET_GLYPHS}]\\s*")


def _clean_text(text: str) -> str:
    text = ZERO_WIDTH_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = _BULLET_GLYPH_RE.sub("• ", text)          # odd bullet glyphs → "• "
    return re.sub(r"(?<=\w)//(?=\w)", "/", text)     # "CI//CD" → "CI/CD" (URLs keep "https://")


def _attach_lone_bullets(lines: list[dict]) -> list[dict]:
    """Some PDFs draw the bullet '•' as a separate line next to its text. Glue it on."""
    bullets = [ln for ln in lines if ln["text"] in ("•", "-", "–", "*", "o")
               and ln["x1"] - ln["x0"] < 12]
    if not bullets:
        return lines
    drop = set()
    for b in bullets:
        near = [ln for ln in lines if ln is not b and ln["page"] == b["page"]
                and ln["x0"] > b["x0"] and ln["x0"] - b["x1"] < 25 and abs(ln["y0"] - b["y0"]) <= 6]
        if near:
            target = min(near, key=lambda ln: (abs(ln["y0"] - b["y0"]), ln["x0"]))
            if not target["text"].startswith("•"):
                target["text"] = "• " + target["text"]
            target["x0"] = min(target["x0"], b["x0"])
            drop.add(id(b))
    return [ln for ln in lines if id(ln) not in drop]


def _read_lines(doc) -> tuple[list[dict], int, list[str], set[str]]:
    """Every non-empty text line with page, position, size, bold."""
    lines, images, links, fonts = [], 0, [], set()
    for pno, page in enumerate(doc):
        images += len(page.get_images())
        links += [lk["uri"] for lk in page.get_links() if lk.get("uri")]
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                spans = [s for s in line["spans"] if ZERO_WIDTH_RE.sub("", s["text"]).strip()]
                if not spans:
                    continue
                text = _clean_text("".join(s["text"] for s in line["spans"]))
                if not text:
                    continue
                for s in spans:
                    fonts.add(re.sub(r"[-,].*$", "", s["font"]))  # "Calibri-Bold" → "Calibri"
                x0, y0, x1, y1 = line["bbox"]
                lines.append({
                    "text": text, "page": pno, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                    "size": round(max(s["size"] for s in spans), 1),
                    "bold": any((s["flags"] & 16) or "bold" in s["font"].lower() for s in spans),
                    "page_width": page.rect.width,
                })
    return _attach_lone_bullets(lines), images, links, fonts


# ----------------------------------------------------------------- columns --
# How column detection works:
# A "gutter" is a vertical line x = g that text does not cross. For each candidate g
# we cut the page into horizontal bands at every line that DOES cross g (titles,
# full-width paragraphs). A band is two-column if it has real content on both sides
# of g. We pick the g whose two-column bands cover the most lines. This handles
# full two-column CVs (Canva templates) and CVs where only one part is side by side
# (e.g. EDUCATION | LANGUAGES at the bottom).

def _bands(page_lines: list[dict], g: float) -> list[tuple[bool, list[dict]]]:
    """Split lines into bands at lines crossing x=g. Returns [(is_two_column, lines)]."""
    out, band = [], []
    for ln in sorted(page_lines, key=lambda l: (l["y0"], l["x0"])):
        if ln["x0"] < g - 1 and ln["x1"] > g + 1:   # crosses the gutter → separator
            if band:
                out.append(band)
                band = []
            out.append([ln])
        else:
            band.append(ln)
    if band:
        out.append(band)
    result = []
    for b in out:
        # The two-column part starts where BOTH sides have text; lines above that
        # (e.g. a normal single-column CV above an EDUCATION | LANGUAGES strip) stay single.
        left_y = [ln["y0"] for ln in b if ln["x1"] <= g + 1]
        right_y = [ln["y0"] for ln in b if ln["x0"] >= g - 1]
        if left_y and right_y:
            start = max(min(left_y), min(right_y)) - 2
            prefix = [ln for ln in b if ln["y0"] < start]
            if prefix:
                result.append((False, prefix))
                b = [ln for ln in b if ln["y0"] >= start]
        result.append((_band_is_two_column(b, g), b))
    return result


def _band_is_two_column(band: list[dict], g: float) -> bool:
    left = [ln for ln in band if ln["x1"] <= g + 1]
    right = [ln for ln in band if ln["x0"] >= g - 1]
    if len(left) < 3 or len(right) < 3:
        return False
    # Right-aligned dates/locations of a normal CV are few and short; a real column
    # either starts with a section heading or holds a fair share of the text.
    right_chars = sum(len(ln["text"]) for ln in right)
    total_chars = right_chars + sum(len(ln["text"]) for ln in left)
    has_heading = any(detect_heading(ln["text"]) for ln in right)
    return has_heading or (len(right) >= 5 and right_chars >= 0.2 * total_chars)


def _best_gutter(page_lines: list[dict]) -> tuple[float | None, list[tuple[bool, list[dict]]]]:
    if len(page_lines) < 6:
        return None, []
    w = page_lines[0]["page_width"]
    best, best_cover, best_bands = None, 0, []
    for g in range(int(0.2 * w), int(0.75 * w), 3):
        bands = _bands(page_lines, g)
        cover = sum(len(b) for two, b in bands if two)
        if cover > best_cover:
            best, best_cover, best_bands = g, cover, bands
    return best, best_bands


def _is_two_column(page_lines: list[dict]) -> bool:
    """True if most of the page is laid out in two columns."""
    g, bands = _best_gutter(page_lines)
    if g is None:
        return False
    return sum(len(b) for two, b in bands if two) >= 0.4 * len(page_lines)


def _merge_rows(lines: list[dict]) -> list[dict]:
    """Join lines on the same row (e.g. 'Intern, ABC Corp' + 'Jun 2023 – Aug 2023')."""
    rows: list[dict] = []
    for ln in sorted(lines, key=lambda l: (round(l["y0"]), l["x0"])):
        if rows and abs(rows[-1]["y0"] - ln["y0"]) <= 3:
            prev = rows[-1]
            prev["text"] += "  " + ln["text"]
            prev["x1"] = max(prev["x1"], ln["x1"])
            prev["bold"] = prev["bold"] or ln["bold"]
            prev["size"] = max(prev["size"], ln["size"])
        else:
            rows.append(dict(ln))
    return rows


def _reading_order(lines: list[dict]) -> tuple[list[dict], int]:
    """Put lines in human reading order. Returns (ordered lines, columns: 1 or 2)."""
    ordered, two_col_lines = [], 0
    for pno in sorted({ln["page"] for ln in lines}):
        page_lines = [ln for ln in lines if ln["page"] == pno]
        g, bands = _best_gutter(page_lines)
        if g is None:
            ordered += _merge_rows(page_lines)
            continue
        two_col_lines += sum(len(b) for two, b in bands if two)
        pending: list[dict] = []   # consecutive single-column lines, merged into rows together
        for two, band in bands:
            if two:
                ordered += _merge_rows(pending)
                pending = []
                ordered += _merge_rows([ln for ln in band if ln["x1"] <= g + 1])   # left column
                ordered += _merge_rows([ln for ln in band if ln["x1"] > g + 1])    # right column
            else:
                pending += band
        ordered += _merge_rows(pending)
    # Report "2 columns" (an ATS risk) only if a big part of the CV is side by side,
    # not for one small EDUCATION | LANGUAGES strip at the bottom.
    max_cols = 2 if lines and two_col_lines >= 0.5 * len(lines) else 1
    return ordered, max_cols


def _is_styled(ln: dict, body_size: float) -> bool:
    """Headings usually stand out: bold, bigger, ALL CAPS or ending with ':'."""
    if "size" not in ln:          # pdfplumber fallback lines carry no style info
        return True
    letters = re.sub(r"[^A-Za-z]", "", ln["text"])
    return (ln["bold"] or ln["size"] >= body_size + 1 or ln["text"].rstrip().endswith(":")
            or (len(letters) >= 3 and letters.isupper()))


def split_sections(lines: list[dict]) -> tuple[dict[str, str], list[str]]:
    """Group lines under the section headings. Text before the first heading
    goes to 'header' (usually name + contact). Returns (sections, headings found).

    If the CV styles its headings (bold/bigger/caps), a plain line such as
    'Technical skills' inside a skills list is NOT treated as a heading."""
    sizes = [ln["size"] for ln in lines if "size" in ln]
    body = statistics.median(sizes) if sizes else 0
    candidates = [ln for ln in lines if detect_heading(ln["text"])]
    styled_only = sum(_is_styled(ln, body) for ln in candidates) >= 2

    sections: dict[str, list[str]] = {"header": []}
    found: list[str] = []
    current = "header"
    for ln in lines:
        canon = detect_heading(ln["text"])
        if canon and styled_only and not _is_styled(ln, body):
            canon = None
        if canon:
            current = canon
            found.append(ln["text"])
            sections.setdefault(canon, [])
        else:
            sections.setdefault(current, []).append(ln["text"])
    return {k: "\n".join(v) for k, v in sections.items() if v or k != "header"}, found


def _count_tables(data: bytes) -> tuple[int, str]:
    """pdfplumber: number of tables, plus its own text (used as a fallback)."""
    tables, text = 0, []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages[:4]:
                tables += len(page.find_tables())
                text.append(page.extract_text() or "")
    except Exception:
        pass
    return tables, "\n".join(text)


# -------------------------------------------------------------------- main --
def extract_pdf(data: bytes) -> dict:
    """Parse a resume PDF. Raises PDFError if the file can't be read."""
    if len(data) > MAX_PDF_BYTES:
        raise PDFError("File is larger than 5 MB.")
    if not data.lstrip()[:5] == b"%PDF-":
        raise PDFError("This is not a PDF file.")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise PDFError("Could not open the PDF. It may be corrupted.") from None
    if doc.needs_pass:
        raise PDFError("The PDF is password-protected.")

    with doc:
        page_count = doc.page_count
        raw_lines, images, links, fonts = _read_lines(doc)

    ordered, columns = _reading_order(raw_lines)
    text = "\n".join(ln["text"] for ln in ordered)
    tables, plumber_text = _count_tables(data)

    used_fallback = False
    if len(text.strip()) < 50 and len(plumber_text.strip()) > len(text.strip()):
        text, used_fallback = plumber_text, True
        ordered = [{"text": t.strip()} for t in plumber_text.splitlines() if t.strip()]

    sections, headings = split_sections(ordered)
    sizes = [ln["size"] for ln in raw_lines] or [0]
    return {
        "text": text,
        "sections": sections,
        "headings_found": headings,
        "contact": extract_contact(text, links),
        "layout": {
            "pages": page_count,
            "columns": columns,
            "images": images,
            "tables": tables,
            "font_families": sorted(fonts),
            "body_font_size": statistics.median(sizes),
            "word_count": len(text.split()),
            "is_scanned": len(text.strip()) < 100,
            "used_pdfplumber_fallback": used_fallback,
        },
    }
