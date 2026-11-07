"""Step 3 of the Resume Intelligence pipeline: the ATS scorecard.

HYBRID ATS DESIGN (see ROADMAP.md):
  Layer 1: RULES (this file): how real ATS parsers read a file, plus
           recruiter/career-office best practice. Deterministic, explainable.
  Layer 2: KEYWORDS learned from real job postings (Day 8-9, career agent)
  Layer 3: SEMANTIC match with Sentence-BERT (Day 9, career agent)

Layer 1 → "readability" score out of 100, in 5 categories:
  Parseability 30 | Sections 20 | Contact 10 | Content quality 25 | Length & skills 15

Every check returns points, a message and a concrete fix, so users (and the
FYP panel) can see exactly why points were lost.
"""
import re

ATS_VERSION = "ats-layer1-v1"

# ----------------------------------------------------------- reference data --
ACTION_VERBS = set("""
accelerated achieved acquired adapted addressed administered advised advocated analyzed analysed
applied architected arranged assembled assessed assisted audited authored automated balanced
boosted briefed budgeted built calculated campaigned captured catalogued chaired championed
clarified coached collaborated collected compiled completed composed computed conceived conceptualized
conducted configured consolidated constructed consulted contributed controlled converted coordinated
created cultivated customized cut debugged decreased defined delivered demonstrated deployed designed
detected developed devised diagnosed directed discovered documented doubled drafted drove earned
edited educated eliminated enabled engineered enhanced established evaluated examined executed
expanded expedited experimented facilitated finalized forecasted formulated founded generated grew
guided handled headed helped identified implemented improved increased influenced initiated innovated
inspected installed instructed integrated interviewed introduced invented investigated launched led
lectured leveraged maintained managed mapped marketed maximized measured mentored merged migrated
minimized modeled modelled modernized monitored motivated negotiated operated optimized orchestrated
organized organised oversaw partnered performed piloted pioneered planned prepared presented
prioritized processed produced programmed promoted proposed prototyped provided published
quantified raised ran rebuilt recommended reconciled recruited redesigned reduced refactored
refined registered remodeled reorganized replaced reported represented researched resolved
restructured revamped reviewed revised scaled scheduled scripted secured selected served
shaped simplified solved spearheaded standardized streamlined strengthened structured supervised
supported surpassed taught tested tracked trained transformed translated tripled troubleshot
tuned unified updated upgraded utilized validated verified visualized won wrote delivering designing
building developing leading managing creating implementing teaching mentoring automating deploying
""".split())
WEAK_STARTS = ("responsible for", "worked on", "duties included", "involved in", "tasked with",
               "in charge of", "helped with", "assisted with", "participated in")
ADVERBS = {"successfully", "effectively", "independently", "actively", "personally", "jointly"}
FIRST_PERSON_RE = re.compile(r"\b(I|me|my|mine|myself)\b")
NUMBER_RE = re.compile(r"\d|%|\$|\bPKR\b|\bRs\.?\b|\bk\b|\bmillion\b|\bthousand\b", re.I)

SAFE_FONT_TOKENS = ("arial", "calibri", "helvetica", "times", "georgia", "garamond", "cambria",
                    "verdana", "tahoma", "roboto", "opensans", "lato", "liberation", "dejavu", "segoe",
                    "carlito", "sourcesans", "noto", "trebuchet", "bookantiqua", "palatino", "century",
                    "inter", "montserrat", "raleway", "poppins", "aptos", "ptsans", "ptserif", "merriweather")
IGNORED_FONT_TOKENS = ("symbol", "wingding", "fontawesome", "icon", "dingbat", "zapf", "materialicons")
LATEX_FONT_RE = re.compile(r"^(cm|lm|sf)[a-z]*\d*$")

SOFT_CATEGORY = "soft_skills"


# ------------------------------------------------------------------ helpers --
def _check(cid: str, label: str, points: float, max_points: float, message: str, fix: str = "") -> dict:
    points = round(max(0.0, min(points, max_points)), 1)
    lost = max_points - points
    return {
        "id": cid, "label": label, "points": points, "max_points": max_points,
        "passed": lost < 0.01, "message": message, "fix": fix if lost >= 0.01 else "",
        "severity": "high" if lost >= 5 else "medium" if lost >= 2 else "low" if lost > 0 else "none",
    }


def _category(cid: str, name: str, checks: list[dict]) -> dict:
    return {
        "id": cid, "name": name, "checks": checks,
        "score": round(sum(c["points"] for c in checks), 1),
        "max": sum(c["max_points"] for c in checks),
    }


def _is_action_verb(word: str) -> bool:
    if word in ACTION_VERBS:
        return True
    if word.endswith("ing") and len(word) > 5:  # Supporting → supported, Managing → managed
        stem = word[:-3]
        return any(f in ACTION_VERBS for f in (stem + "ed", stem + "d", stem + "ied", stem[:-1] + "ed"))
    return False


def _starts_with_action_verb(bullet: str) -> bool:
    words = re.findall(r"[A-Za-z]+", bullet.lower())[:2]
    if not words:
        return False
    if words[0] in ADVERBS and len(words) > 1:
        return _is_action_verb(words[1])
    return _is_action_verb(words[0])


def _collect_bullets(entities: dict) -> list[str]:
    bullets = [b for job in entities.get("experience", []) for b in job.get("bullets", [])]
    bullets += [d for p in entities.get("projects", []) for d in p.get("description", [])]
    return [b.strip() for b in bullets if len(b.split()) >= 3]


def _clean_font(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.split("+")[-1].lower())


# ------------------------------------------------------------- categories --
def _parseability(layout: dict) -> list[dict]:
    checks = []
    checks.append(_check(
        "not_scanned", "Text is machine-readable", 0 if layout["is_scanned"] else 10, 10,
        "The PDF is a scanned image, so an ATS can't read any text in it." if layout["is_scanned"]
        else "The PDF contains real text that an ATS can read.",
        "Export your resume directly from Word or Google Docs as PDF. Don't scan or photograph it."))

    cols = layout["columns"]
    checks.append(_check(
        "single_column", "Single-column layout", 5 if cols == 1 else 1, 5,
        "Single-column layout: the safest choice for ATS parsing." if cols == 1
        else "Two-column layout detected. Many ATS parsers read across columns and mix up your text.",
        "Use a single-column layout, or keep the second column only for short items like contact details."))

    tables = layout["tables"]
    checks.append(_check(
        "no_tables", "No tables", 5 if tables == 0 else 0, 5,
        "No tables found." if tables == 0
        else f"{tables} table(s) found. ATS parsers often skip or scramble text inside tables.",
        "Replace tables with plain text lines and bullet points."))

    imgs = layout["images"]
    checks.append(_check(
        "no_images", "No images or graphics", 3 if imgs == 0 else 1 if imgs == 1 else 0, 3,
        "No images found." if imgs == 0
        else f"{imgs} image(s) found (photo, icons or charts). An ATS ignores images, and any text inside them is lost.",
        "Remove the photo, icons and skill-level bars. Write everything as plain text."))

    fonts = [_clean_font(f) for f in layout.get("font_families", [])]
    fonts = [f for f in fonts if f and not any(t in f for t in IGNORED_FONT_TOKENS)]
    unsafe = [f for f in fonts if not (any(t in f for t in SAFE_FONT_TOKENS) or LATEX_FONT_RE.match(f))]
    fam_ok = len(set(fonts)) <= 3
    font_pts = 3 if (not unsafe and fam_ok) else 1.5 if (len(unsafe) <= 1 and fam_ok) else 0
    checks.append(_check(
        "standard_fonts", "Standard, consistent fonts", font_pts, 3,
        "Standard fonts used." if font_pts == 3
        else f"Uncommon or too many fonts: {', '.join(sorted(set(unsafe)) or sorted(set(fonts)))}.",
        "Use one or two standard fonts such as Calibri, Arial, Georgia or Times New Roman."))

    size = layout.get("body_font_size") or 0
    size_pts = 4 if 10 <= size <= 12.5 else 2 if 9 <= size < 10 or 12.5 < size <= 14 else 0
    checks.append(_check(
        "font_size", "Readable font size", size_pts, 4,
        f"Body text size is about {size:g} pt." + ("" if size_pts == 4 else " The recommended size is 10–12 pt."),
        "Set body text to 10–12 pt and headings to 12–16 pt."))
    return checks


def _sections(sections: dict, entities: dict) -> list[dict]:
    has = lambda s: bool(sections.get(s, "").strip())  # noqa: E731
    checks = []
    if has("experience"):
        exp_pts, exp_msg = 6, "Experience section found."
    elif entities.get("projects"):
        exp_pts, exp_msg = 3, "No Experience section, but projects are listed. That's fine for students."
    else:
        exp_pts, exp_msg = 0, "No Experience or Projects section found."
    checks.append(_check("has_experience", "Experience section", exp_pts, 6, exp_msg,
                         "Add an 'Experience' section. Internships, freelance and volunteer work count. "
                         "If you have none, add a 'Projects' section."))
    checks.append(_check("has_education", "Education section", 5 if has("education") else 0, 5,
                         "Education section found." if has("education") else "No Education section found.",
                         "Add an 'Education' section with degree, university and graduation year."))
    checks.append(_check("has_skills", "Skills section", 5 if has("skills") else 0, 5,
                         "Skills section found." if has("skills")
                         else "No dedicated Skills section. An ATS looks for one to match keywords.",
                         "Add a 'Skills' section listing your tools and technologies, grouped by type."))
    checks.append(_check("has_summary", "Summary", 2 if has("summary") else 0, 2,
                         "Summary found." if has("summary") else "No summary or profile section.",
                         "Add a 2–3 line summary at the top: your role, key skills and what you're looking for."))
    extra = has("projects") or has("certifications")
    checks.append(_check("has_projects_or_certs", "Projects or certifications", 2 if extra else 0, 2,
                         "Projects or certifications listed." if extra else "No Projects or Certifications section.",
                         "Add a 'Projects' or 'Certifications' section to show practical skills."))
    return checks


def _contact(contact: dict, entities: dict) -> list[dict]:
    return [
        _check("email", "Email address", 4 if contact.get("email") else 0, 4,
               f"Email found: {contact['email']}" if contact.get("email") else "No email address found.",
               "Add a professional email address at the top."),
        _check("phone", "Phone number", 3 if contact.get("phone") else 0, 3,
               "Phone number found." if contact.get("phone") else "No phone number found.",
               "Add your phone number with country code, e.g. +92 300 1234567."),
        _check("linkedin", "LinkedIn profile", 2 if contact.get("linkedin") else 0, 2,
               "LinkedIn profile found." if contact.get("linkedin") else "No LinkedIn URL found.",
               "Add your LinkedIn URL (linkedin.com/in/your-name). Recruiters check it."),
        _check("location", "Location", 1 if entities.get("location") else 0, 1,
               f"Location found: {entities['location']}" if entities.get("location") else "No city or location found.",
               "Add your city and country, e.g. 'Karachi, Pakistan'."),
    ]


def _content(entities: dict) -> list[dict]:
    bullets = _collect_bullets(entities)
    n = len(bullets)
    if n == 0:
        none = "No bullet points found in your experience or projects."
        fix = "Describe each job and project with 3–5 bullet points that start with an action verb."
        return [
            _check("bullets_used", "Uses bullet points", 0, 3, none, fix),
            _check("action_verbs", "Bullets start with action verbs", 0, 8, none, fix),
            _check("quantified", "Achievements are quantified", 0, 7, none, fix),
            _check("bullet_length", "Bullet length", 0, 3, none, fix),
            _check("no_first_person", "No first-person pronouns", 2, 2, "No pronouns found."),
            _check("entries_complete", "Job entries have title and company", 0, 2, none, fix),
        ]

    checks = [_check("bullets_used", "Uses bullet points", 3 if n >= 3 else 1.5, 3,
                     f"{n} bullet points found.", "Use at least 3 bullet points per job or project.")]

    weak = [b for b in bullets if not _starts_with_action_verb(b)]
    ratio = 1 - len(weak) / n
    weak_examples = [b for b in weak if b.lower().startswith(WEAK_STARTS)] or weak
    example = (" Rewrite these: " + " | ".join(f'"{b[:70]}…"' for b in weak_examples[:3])) if weak_examples else ""
    checks.append(_check(
        "action_verbs", "Bullets start with action verbs", 8 * min(1, ratio / 0.9), 8,
        f"{n - len(weak)} of {n} bullets start with a strong action verb.",
        f"Start every bullet with a verb like Built, Led, Automated or Reduced.{example}"))

    quantified = [b for b in bullets if NUMBER_RE.search(b)]
    q_ratio = len(quantified) / n
    checks.append(_check(
        "quantified", "Achievements are quantified", 7 * min(1, q_ratio / 0.6), 7,
        f"{len(quantified)} of {n} bullets include numbers or measurable results.",
        "Add numbers that show impact, e.g. 'cut deployment time by 40%' or 'trained 30 students'."))

    avg = sum(len(b.split()) for b in bullets) / n
    too_long = [b for b in bullets if len(b.split()) > 35]
    len_pts = 3 if 8 <= avg <= 28 and not too_long else 1.5 if 5 <= avg <= 35 else 0
    checks.append(_check(
        "bullet_length", "Bullet length", len_pts, 3,
        f"Bullets average {avg:.0f} words." + (f" {len(too_long)} are longer than 35 words." if too_long else ""),
        "Keep each bullet to 1–2 lines (about 10–25 words)."))

    fp = sum(len(FIRST_PERSON_RE.findall(b)) for b in bullets)
    checks.append(_check(
        "no_first_person", "No first-person pronouns", 2 if fp <= 1 else 1 if fp <= 4 else 0, 2,
        "No first-person pronouns in bullets." if fp <= 1 else f"'I', 'me' or 'my' appears {fp} times in bullets.",
        "Drop pronouns: write 'Built an API…', not 'I built an API…'."))

    jobs = entities.get("experience", [])
    complete = [j for j in jobs if j.get("title") and j.get("company")]
    checks.append(_check(
        "entries_complete", "Job entries have title and company",
        2 if not jobs or len(complete) == len(jobs) else 1, 2,
        f"{len(complete)} of {len(jobs)} jobs show both a title and a company." if jobs else "No job entries to check.",
        "Write each job as 'Job Title, Company' on one line, with the dates on the right."))
    return checks


def _length_and_skills(layout: dict, entities: dict) -> list[dict]:
    words, pages = layout["word_count"], layout["pages"]
    w_pts = 5 if 300 <= words <= 900 else 3 if 200 <= words < 300 or 900 < words <= 1200 else 1
    checks = [
        _check("word_count", "Length (word count)", w_pts, 5,
               f"About {words} words.",
               "Aim for 300–900 words. Add detail to your experience and projects." if words < 300
               else "Aim for 300–900 words. Cut older or less relevant items."),
        _check("page_count", "Page count", 2 if pages <= 2 else 1 if pages == 3 else 0, 2,
               f"{pages} page(s).", "Keep it to 1 page as a student, or 2 pages with several years of experience."),
    ]

    hard = [s for s in entities.get("skills", []) if s["category"] != SOFT_CATEGORY]
    k = len(hard)
    checks.append(_check(
        "skill_count", "Number of technical skills", 5 if k >= 10 else 3 if k >= 6 else 1 if k >= 3 else 0, 5,
        f"{k} technical or professional skills recognised.",
        "List more of the specific tools and technologies you've used (at least 10)."))

    listed = [s for s in hard if "skills" in s["sections"]]
    if listed:
        evidenced = [s for s in listed if set(s["sections"]) & {"experience", "projects"}]
        ratio = len(evidenced) / len(listed)
        missing = [s["name"] for s in listed if s not in evidenced][:5]
        checks.append(_check(
            "skills_evidenced", "Listed skills are backed by experience", 3 * min(1, ratio / 0.4), 3,
            f"{len(evidenced)} of {len(listed)} skills in your Skills section also appear in your experience or projects.",
            "Show where you used your listed skills, e.g. mention "
            + ", ".join(missing) + " in a job or project bullet." if missing else ""))
    else:
        used = [s for s in hard if set(s["sections"]) & {"experience", "projects"}]
        checks.append(_check(
            "skills_evidenced", "Listed skills are backed by experience", 1.5 if used else 0, 3,
            "There's no Skills section to compare against your experience.",
            "Add a Skills section, and make sure those skills also appear in your job or project bullets."))
    return checks


# -------------------------------------------------------------------- main --
def score_resume(parsed: dict, entities: dict) -> dict:
    layout, sections = parsed["layout"], parsed["sections"]
    categories = [
        _category("parseability", "ATS parseability", _parseability(layout)),
        _category("sections", "Standard sections", _sections(sections, entities)),
        _category("contact", "Contact details", _contact(parsed["contact"], entities)),
        _category("content", "Content quality", _content(entities)),
        _category("length_skills", "Length & skills", _length_and_skills(layout, entities)),
    ]
    score = round(sum(c["score"] for c in categories))
    if layout["is_scanned"]:
        score = min(score, 15)  # nothing else matters if the ATS can't read the text

    all_checks = [c for cat in categories for c in cat["checks"]]
    issues = sorted((c for c in all_checks if not c["passed"]),
                    key=lambda c: -(c["max_points"] - c["points"]))
    return {
        "version": ATS_VERSION,
        "readability_score": score,
        "grade": "Excellent" if score >= 85 else "Good" if score >= 70 else "Needs work" if score >= 50 else "Poor",
        "categories": categories,
        "top_fixes": [{"label": c["label"], "fix": c["fix"], "severity": c["severity"],
                       "points_available": round(c["max_points"] - c["points"], 1)} for c in issues[:6]],
        "strengths": [c["label"] for c in all_checks if c["passed"]],
        # Layers 2 + 3 are filled by the Career Guide Agent once a target role is chosen (Day 9)
        "role_match": None,
    }
