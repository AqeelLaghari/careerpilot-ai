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
                "career objective", "professional profile", "personal statement"],
    "experience": ["experience", "work experience", "professional experience", "employment",
                   "employment history", "work history", "internships", "internship",
                   "internship experience", "relevant experience"],
    "education": ["education", "academic background", "academics", "educational background",
                  "education and qualifications", "academic qualifications", "qualifications"],
    "skills": ["skills", "technical skills", "core skills", "key skills", "skills and tools",
               "competencies", "core competencies", "technologies", "tools and technologies",
               "technical expertise", "skill set", "skills and abilities", "soft skills"],
    "projects": ["projects", "academic projects", "personal projects", "key projects",
                 "selected projects", "project experience", "final year project"],
    "certifications": ["certifications", "certificates", "licenses and certifications",
                       "courses", "training", "certifications and courses", "online courses"],
    "achievements": ["achievements", "awards", "honors", "honours", "awards and achievements",
                     "accomplishments", "awards and honors"],
    "languages": ["languages", "language"],
    "interests": ["interests", "hobbies", "hobbies and interests"],
    "publications": ["publications", "research", "research experience"],
    "volunteer": ["volunteer", "volunteering", "volunteer experience", "extracurricular activities",
                  "extra curricular activities", "extracurriculars", "leadership",
                  "leadership and activities", "activities"],
    "references": ["references"],
}
_HEADING_LOOKUP = {h: canon for canon, names in SECTION_HEADINGS.items() for h in names}
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
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                text = re.sub(r"\s+", " ", "".join(s["text"] for s in line["spans"])).strip()
                for s in spans:
                    fonts.add(re.sub(r"[-,].*$", "", s["font"]))  # "Calibri-Bold" → "Calibri"
                x0, y0, x1, y1 = line["bbox"]
                lines.append({
                    "text": text, "page": pno, "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                    "size": round(max(s["size"] for s in spans), 1),
                    "bold": any((s["flags"] & 16) or "bold" in s["font"].lower() for s in spans),
                    "page_width": page.rect.width,
                })
    return lines, images, links, fonts


def _is_two_column(page_lines: list[dict]) -> bool:
    """Two-column if several long lines start in the right half of the page.
    (Right-aligned dates on a normal resume are short, so they don't count.)"""
    if not page_lines:
        return False
    w = page_lines[0]["page_width"]
    long_right = [ln for ln in page_lines if ln["x0"] > 0.38 * w and (ln["x1"] - ln["x0"]) > 0.22 * w]
    long_left_narrow = [ln for ln in page_lines if ln["x0"] < 0.3 * w and ln["x1"] < 0.62 * w
                        and (ln["x1"] - ln["x0"]) > 0.12 * w]
    return len(long_right) >= 5 and len(long_left_narrow) >= 5


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
    """Put lines in human reading order. Returns (ordered lines, max columns)."""
    ordered, max_cols = [], 1
    for pno in sorted({ln["page"] for ln in lines}):
        page_lines = [ln for ln in lines if ln["page"] == pno]
        if _is_two_column(page_lines):
            max_cols = 2
            split = 0.38 * page_lines[0]["page_width"]
            left = [ln for ln in page_lines if ln["x0"] < split]
            right = [ln for ln in page_lines if ln["x0"] >= split]
            ordered += _merge_rows(left) + _merge_rows(right)
        else:
            ordered += _merge_rows(page_lines)
    return ordered, max_cols


def split_sections(lines: list[dict]) -> tuple[dict[str, str], list[str]]:
    """Group lines under the section headings. Text before the first heading
    goes to 'header' (usually name + contact). Returns (sections, headings found)."""
    sections: dict[str, list[str]] = {"header": []}
    found: list[str] = []
    current = "header"
    for ln in lines:
        canon = detect_heading(ln["text"])
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
        raise PDFError("Could not open the PDF. It may be corrupted.")
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
