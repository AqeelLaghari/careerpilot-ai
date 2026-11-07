"""Builds small fake resume PDFs for the tests."""
import pymupdf
import pytest


def _make_pdf(rows: list[tuple]) -> bytes:
    """rows = (x, y, text, fontsize) or (x, y, text, fontsize, font) on one A4 page.
    font: "helv" (regular, default) or "hebo" (bold)."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text, size, *font in rows:
        page.insert_text((x, y), text, fontsize=size, fontname=font[0] if font else "helv")
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def single_column_pdf() -> bytes:
    rows = [
        (50, 60, "Ali Raza", 20),
        (50, 85, "ali.raza@gmail.com | +92 300 1234567 | linkedin.com/in/aliraza", 10),
        (50, 120, "SUMMARY", 13),
        (50, 140, "Software engineering student passionate about backend systems.", 10),
        (50, 175, "EXPERIENCE", 13),
        (50, 195, "Backend Intern, TechCorp Karachi", 10),
        (450, 195, "Jun 2024 - Aug 2024", 10),
        (50, 210, "Built REST APIs with FastAPI and PostgreSQL.", 10),
        (50, 245, "EDUCATION", 13),
        (50, 265, "BS Software Engineering, Bahria University", 10),
        (450, 265, "2022 - 2026", 10),
        (50, 300, "SKILLS", 13),
        (50, 320, "Python, FastAPI, SQL, Git, Docker, Flutter", 10),
    ]
    return _make_pdf(rows)


@pytest.fixture
def two_column_pdf() -> bytes:
    left = [
        (40, 60, "Sara Khan", 20),
        (40, 120, "SKILLS", 13),
        (40, 140, "Python and Machine Learning", 10),
        (40, 155, "TensorFlow and Keras models", 10),
        (40, 170, "SQL databases and analysis", 10),
        (40, 185, "Data visualization tools", 10),
        (40, 200, "Statistics and probability", 10),
        (40, 240, "LANGUAGES", 13),
        (40, 260, "English and Urdu fluent", 10),
    ]
    right = [
        (260, 120, "EXPERIENCE", 13),
        (260, 140, "Data Science Intern at Analytics Pvt Ltd Karachi", 10),
        (260, 155, "Built churn prediction model with 87 percent accuracy", 10),
        (260, 170, "Cleaned and analysed sales datasets using pandas", 10),
        (260, 185, "Presented weekly dashboards to the management team", 10),
        (260, 225, "EDUCATION", 13),
        (260, 245, "BS Computer Science from NED University Karachi", 10),
        (260, 260, "Graduated with distinction and a CGPA of 3.7", 10),
    ]
    return _make_pdf(left + right)
