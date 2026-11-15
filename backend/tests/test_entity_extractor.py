from app.services.entity_extractor import (
    extract_education,
    extract_entities,
    extract_experience,
    find_skills,
    total_experience_months,
)


def test_skills_basic_and_aliases():
    s = find_skills("Built APIs with node.js, ReactJS and PostgreSQL. Strong in CI/CD and C++.")
    assert {"Node.js", "React", "PostgreSQL", "CI/CD", "C++"} <= set(s)
    assert s["React"]["category"] == "web_frontend"


def test_slash_separated_skills():
    assert {"Python", "Django", "SQL"} <= set(find_skills("Python/Django/SQL developer"))


def test_ambiguous_words_not_matched():
    s = find_skills("I excel at teamwork and did the rest of the work in R&D. Let's go to the office.")
    assert "Microsoft Excel" not in s
    assert "REST APIs" not in s
    assert "R" not in s
    assert "Go" not in s
    assert "Teamwork" in s


def test_ambiguous_words_matched_in_list():
    s = find_skills("Languages: Python, R, Go, Java")
    assert {"R", "Go", "Python", "Java"} <= set(s)


def test_experience_entries():
    text = (
        "DevOps Developer Faculty  July 2026 – Present\n"
        "Techzone Learning · Karachi, Pakistan\n"
        "•  Delivering DevOps training on CI/CD.\n"
        "DevOps Engineer  February 2026 – July 2026\n"
        "360XpertSolutions · Karachi\n"
        "•  Managed Docker and Kubernetes deployments\n"
        "   across three environments.\n"
    )
    jobs = extract_experience(text)
    assert len(jobs) == 2
    assert jobs[0]["title"] == "DevOps Developer Faculty"
    assert jobs[0]["company"] == "Techzone Learning"
    assert jobs[0]["current"] is True
    assert jobs[1]["months"] == 6
    assert jobs[1]["bullets"][0].endswith("across three environments.")
    # Feb-Jul and Jul-now overlap in July → July counted once
    assert total_experience_months(jobs) == jobs[1]["months"] + jobs[0]["months"] - 1


def test_title_company_same_line():
    jobs = extract_experience("Backend Intern, TechCorp Karachi  Jun 2024 - Aug 2024")
    assert jobs[0]["title"] == "Backend Intern"
    assert jobs[0]["company"] == "TechCorp Karachi"
    assert jobs[0]["months"] == 3


def test_education():
    text = (
        "BSE – Bachelor of Software Engineering · Bahria University, Karachi  Expected Jun 2027\n"
        "CGPA: 3.45/4.0\n"
        "Intermediate (Pre-Engineering), Adamjee Government Science College  2021 - 2023  88%\n"
    )
    edu = extract_education(text)
    assert edu[0]["degree_level"] == "Bachelors"
    assert edu[0]["field"] == "Software Engineering"
    assert "Bahria University" in edu[0]["institution"]
    assert edu[0]["expected"] is True and edu[0]["end_year"] == 2027
    assert edu[0]["cgpa"] == 3.45
    assert edu[1]["degree_level"] == "Intermediate"
    assert edu[1]["percentage"] == 88.0


def test_full_entities_no_llm(monkeypatch):
    monkeypatch.setattr("app.services.llm.available", lambda: False)
    sections = {
        "header": "Abdul Mannan Butt\nDevOps Engineer & Educator\nme@gmail.com | +92 322 5588095 | Karachi, Pakistan",
        "skills": "Python, Docker, Kubernetes, Terraform, AWS, Git",
        "experience": "DevOps Engineer  Feb 2026 – Jul 2026\n360XpertSolutions\n• Used Docker daily",
        "education": "BS Computer Science, NED University  2020 - 2024",
        "projects": "Distributed Task Manager  2026\n• RabbitMQ, Redis, MongoDB, Docker",
        "languages": "English, Urdu",
    }
    e = extract_entities(sections, "\n".join(sections.values()))
    assert e["name"] == "Abdul Mannan Butt"
    assert e["headline"] == "DevOps Engineer & Educator"
    assert "Karachi" in e["location"]
    docker = next(s for s in e["skills"] if s["name"] == "Docker")
    assert docker["mentions"] == 3 and set(docker["sections"]) == {"skills", "experience", "projects"}
    assert e["projects"][0]["title"] == "Distributed Task Manager"
    assert "RabbitMQ" in e["projects"][0]["skills"]
    assert e["languages"] == ["English", "Urdu"]
    assert e["total_experience_months"] == 6
    assert e["extraction_method"] == "spacy+rules"


def test_project_wrapped_lines_not_titles():
    from app.services.entity_extractor import extract_projects
    text = (
        "Distributed Task Manager  2026\n"
        "•  3 microservices, Nginx LB, RabbitMQ. GitHub Actions + Trivy CI/CD in <90s. Prometheus\n"
        "+ Grafana monitoring.\n"
        "E-Commerce Platform on AWS (Team Project)  2026\n"
        "•  Built with Node.js and PostgreSQL, no\n"
        "response-time trends & auto-generated suggestions.\n"
    )
    projects = extract_projects(text)
    assert [p["title"] for p in projects] == ["Distributed Task Manager", "E-Commerce Platform on AWS (Team Project)"]
    assert "Grafana" in projects[0]["skills"]


# ---- fixes from the 10-CV batch test (Day 7 checkpoint) ----
def test_experience_single_year_header():
    text = ("Fauji Fertilizer Company (FFC) | IT Department Intern (2025)\n"
            "• Analyzed departmental workflows and reporting systems.\n"
            "Indus Hospital – Karachi | Volunteer Team Leader (2021)\n"
            "• Led a 3-member team coordinating patient outreach.")
    jobs = extract_experience(text)
    assert len(jobs) == 2
    assert jobs[0]["start"] == "2025" and jobs[0]["months"] is None
    assert len(jobs[1]["bullets"]) == 1


def test_experience_no_dates_with_wrapped_bullets():
    text = ("National Bank of Pakistan (NBP) - IT Intern | Head Office, Karachi | 6-Week Internship\n"
            "• Rotated through the ADC and MIS units, gaining practical\n"
            "exposure to banking IT operations.\n"
            "• Developed a Bank Operations Desk Portal using C# and SQL Server.")
    jobs = extract_experience(text)
    assert len(jobs) == 1
    assert len(jobs[0]["bullets"]) == 2 and "exposure" in jobs[0]["bullets"][0]


def test_experience_dates_on_next_line():
    text = ("Software Engineer | Systems Ltd\n"
            "Jan 2022 - Present\n"
            "• Built payment services.")
    jobs = extract_experience(text)
    assert len(jobs) == 1 and jobs[0]["title"] == "Software Engineer" and jobs[0]["current"]


def test_single_word_name():
    from app.services.entity_extractor import extract_name_headline_location
    name, headline, _ = extract_name_headline_location("AQEEL\nData Analytics and AI\nKarachi, Pakistan")
    assert name == "AQEEL" and headline == "Data Analytics and AI"


def test_non_tech_domain_skills():
    found = find_skills("SEO, Google Ads, Bookkeeping, AutoCAD, Lesson Planning, Recruitment, Patient Care, Typography",
                        in_skills_section=True)
    assert {"Google Ads", "Bookkeeping", "AutoCAD", "Lesson Planning", "Recruitment", "Patient Care", "Typography"} <= set(found)


def test_company_first_title_second_is_swapped():
    from app.services.entity_extractor import _split_title_company
    assert _split_title_company("Fauji Fertilizer Company (FFC) | IT Department Intern") == \
        ("IT Department Intern", "Fauji Fertilizer Company (FFC)")
    assert _split_title_company("Indus Hospital – Karachi | Volunteer Team Leader")[0] == "Volunteer Team Leader"
    # "Org - Role | place": the pair hides before the first " | "
    assert _split_title_company("National Bank of Pakistan (NBP) - IT Intern | Head Office, Karachi") == \
        ("IT Intern", "National Bank of Pakistan (NBP)")
    # normal order is kept
    assert _split_title_company("Backend Intern | Systems Ltd") == ("Backend Intern", "Systems Ltd")
    assert _split_title_company("Software Engineer - Backend | Systems Ltd")[0] == "Software Engineer - Backend"
