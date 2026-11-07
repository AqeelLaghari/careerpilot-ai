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
