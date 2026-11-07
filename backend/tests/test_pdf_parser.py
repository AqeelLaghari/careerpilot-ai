import pytest

from app.services.pdf_parser import PDFError, detect_heading, extract_pdf


def test_sections_found(single_column_pdf):
    r = extract_pdf(single_column_pdf)
    assert {"summary", "experience", "education", "skills"} <= set(r["sections"])
    assert "FastAPI" in r["sections"]["skills"]
    assert "Ali Raza" in r["sections"]["header"]


def test_same_row_merged(single_column_pdf):
    r = extract_pdf(single_column_pdf)
    assert "Backend Intern, TechCorp Karachi  Jun 2024 - Aug 2024" in r["sections"]["experience"]


def test_contact(single_column_pdf):
    c = extract_pdf(single_column_pdf)["contact"]
    assert c["email"] == "ali.raza@gmail.com"
    assert c["phone"].replace(" ", "") == "+923001234567"
    assert "linkedin.com/in/aliraza" in c["linkedin"]


def test_layout_single(single_column_pdf):
    lay = extract_pdf(single_column_pdf)["layout"]
    assert lay["columns"] == 1 and lay["pages"] == 1 and not lay["is_scanned"]


def test_two_column_reading_order(two_column_pdf):
    r = extract_pdf(two_column_pdf)
    assert r["layout"]["columns"] == 2
    # columns must not be interleaved: all skills lines stay together
    assert "TensorFlow" in r["sections"]["skills"]
    assert "Data Science Intern" in r["sections"]["experience"]
    assert "TensorFlow" not in r["sections"]["experience"]


@pytest.mark.parametrize("line,expected", [
    ("WORK EXPERIENCE", "experience"),
    ("Skills & Tools", "skills"),
    ("E D U C A T I O N", "education"),
    ("Projects:", "projects"),
    ("I worked on many projects in Python", None),
])
def test_detect_heading(line, expected):
    assert detect_heading(line) == expected


def test_rejects_non_pdf():
    with pytest.raises(PDFError):
        extract_pdf(b"hello, I am not a pdf")


def test_spaced_multiword_heading():
    assert detect_heading("T E C H N I C A L S K I L L S") == "skills"


@pytest.mark.parametrize("line,expected", [
    ("PERSONAL INFORMATION", "personal"),
    ("Career History", "experience"),
    ("Areas of Expertise", "skills"),
    ("Workshops & Seminars", "certifications"),
    ("Teaching Experience", "experience"),
    ("Professional Memberships", "volunteer"),
])
def test_more_domain_headings(line, expected):
    assert detect_heading(line) == expected


# ---- fixes from the 10-CV batch test (Day 7 checkpoint) ----
from tests.conftest import _make_pdf  # noqa: E402


def test_canva_two_column_with_full_width_header():
    """Narrow left sidebar + right column starting at ~37% of the width, and a
    centred name/title that spans both columns (typical Canva template)."""
    rows = [(150, 60, "Alexander Brown", 28, "hebo"), (210, 85, "Marketing Specialist", 14)]
    rows += [(20, 140, "Contact", 16, "hebo"), (30, 165, "+92 300 1234567", 9),
             (30, 180, "alex@example.com", 9), (20, 230, "Skills", 16, "hebo"),
             (30, 255, "Communication", 9), (30, 270, "Time management", 9), (30, 285, "Technical skills", 9),
             (30, 300, "Research", 9), (30, 315, "Creativity", 9)]
    rows += [(221, 140, "Summary", 16, "hebo"),
             (221, 165, "Marketing specialist with eight years of campaign experience.", 9),
             (221, 230, "Experience", 16, "hebo"), (221, 255, "Marketing Strategist  2017 - 2020", 9),
             (221, 270, "Ran SEO and Google Ads campaigns for retail brands.", 9),
             (221, 285, "Grew organic traffic by 40 percent in one year.", 9),
             (221, 330, "Education", 16, "hebo"), (221, 355, "Bachelor of Business Administration", 9)]
    out = extract_pdf(_make_pdf(rows))
    assert out["layout"]["columns"] == 2
    assert set(out["sections"]) >= {"personal", "skills", "summary", "experience", "education"}
    # plain "Technical skills" / "Research" lines are skill items, not headings
    assert "Research" in out["sections"]["skills"] and "publications" not in out["sections"]


def test_partial_two_column_strip_is_single_column():
    """Normal CV with only EDUCATION | LANGUAGES side by side at the bottom."""
    rows = [(50, 60, "Hafid Ziti", 20), (50, 100, "EXPERIENCE", 12, "hebo")]
    rows += [(50, 120 + 14 * i, f"Built feature number {i} of the web application with React and tests", 10)
             for i in range(12)]
    rows += [(50, 320, "EDUCATION", 12, "hebo"), (50, 340, "2018 - MSc Computer Science", 9),
             (50, 354, "Grenoble Alpes University, France", 9), (50, 368, "2016 - BSc Computer Science", 9),
             (360, 320, "LANGUAGES", 12, "hebo"), (360, 340, "French - Native", 9), (360, 354, "English - Professional", 9)]
    out = extract_pdf(_make_pdf(rows))
    assert out["layout"]["columns"] == 1
    assert "education" in out["sections"] and "languages" in out["sections"]
    assert "English" in out["sections"]["languages"] and "English" not in out["sections"]["education"]


def test_symbol_font_bullets_and_zero_width_chars():
    from app.services.pdf_parser import _clean_text
    assert _clean_text(" Built APIs") == "• Built APIs"
    assert _clean_text("●​ Led a team") == "• Led a team"
    assert _clean_text("CI/​CD pipelines") == "CI/CD pipelines"


@pytest.mark.parametrize("line,expected", [
    ("ACHIEVEMENT", "achievements"), ("REFERENCE", "references"), ("Project", "projects"),
])
def test_singular_headings(line, expected):
    assert detect_heading(line) == expected
