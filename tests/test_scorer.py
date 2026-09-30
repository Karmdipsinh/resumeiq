import pytest

from services.resume_scorer import score_resume
from services.skill_extractor import extract_skills

FULL_RESUME = """
Alex Kim
alex@example.com | +1 555 123 4567 | github.com/alex

PROFESSIONAL SUMMARY
Backend developer building tested and reliable web services for product teams.

SKILLS
Python, Flask, SQL, PostgreSQL, Git, Docker, HTML, CSS

EDUCATION
Bachelor of Technology, Example University

PROJECTS
- Built a Flask API used by 100 users.
- Created a SQL reporting tool.

EXPERIENCE
Software Intern
- Implemented API features and improved test coverage by 20%.

CERTIFICATIONS
Python Certificate
"""


def test_score_is_deterministic_and_bounded():
    skills = extract_skills(FULL_RESUME)
    first = score_resume(FULL_RESUME, skills)
    second = score_resume(FULL_RESUME, skills)
    assert first == second
    assert 0 <= first["total_score"] <= 100
    assert sum(first["breakdown"].values()) == first["total_score"]


def test_complete_resume_scores_higher_than_short_resume():
    complete = score_resume(FULL_RESUME, extract_skills(FULL_RESUME))
    short = score_resume("Alex Kim\nPython", extract_skills("Python"))
    assert complete["total_score"] > short["total_score"]
    assert any("very short" in item.lower() for item in short["weaknesses"])


def test_empty_resume_returns_zero_and_guidance():
    result = score_resume("", {})
    assert result["total_score"] == 0
    assert result["weaknesses"]
    assert result["suggestions"]


@pytest.mark.parametrize(
    "text",
    [
        "SUMMARY\nSKILLS\nEDUCATION\nPROJECTS\nEXPERIENCE\nCERTIFICATIONS",
        " ".join(["zxqv blorf qqq"] * 100),
        "SUMMARY\n\nSKILLS\n\nEDUCATION\n\nPROJECTS\n\nEXPERIENCE\n",
    ],
)
def test_empty_structure_and_gibberish_score_poorly(text):
    assert score_resume(text, extract_skills(text))["total_score"] <= 10


def test_repeated_keyword_stuffing_is_penalized():
    spam = "SKILLS\n" + ("Python Docker AWS SQL Git React Java " * 100)
    result = score_resume(spam, extract_skills(spam))
    assert result["total_score"] <= 15
    assert any("repetitive" in weakness for weakness in result["weaknesses"])


def test_realistic_student_resume_beats_adversarial_content():
    student = """Asha Rao
asha@example.com | github.com/asharao
Education
B.Tech Computer Science, Example University, 2022-2026
Skills
Python, SQL, Git, Flask
Projects
- Built a Flask inventory app with SQL for a student club.
- Improved report generation time by 30% for 40 users.
Internship Experience
Software Intern, Example Labs | 2025
- Implemented tested API features and created documentation.
"""
    spam = "SKILLS\n" + ("Python Docker AWS SQL Git React Java " * 100)
    assert score_resume(student, extract_skills(student))["total_score"] > score_resume(spam, extract_skills(spam))["total_score"]


def test_heading_aliases_do_not_dramatically_change_score():
    standard = """Education
B.Tech Computer Science, Example University
Skills
Python, SQL, Git
Projects
- Built a Python inventory app with SQL for a student club.
"""
    renamed = standard.replace("Education", "Academic Background").replace("Skills", "Tools").replace("Projects", "Selected Work")
    first = score_resume(standard, extract_skills(standard))["total_score"]
    second = score_resume(renamed, extract_skills(renamed))["total_score"]
    assert abs(first - second) <= 3


def test_stuffed_resume_does_not_outscore_quality_resume():
    quality = FULL_RESUME + "\n- Optimized API latency by 35% for 200 users.\n"
    stuffed = """Jordan Lee
jordan@example.com | +1 555 222 3333
SUMMARY
Achieved built created delivered developed implemented improved increased led managed.
SKILLS
Python Java JavaScript TypeScript Go Rust Kotlin Swift Ruby PHP SQL NoSQL MySQL PostgreSQL
MongoDB Redis AWS Azure Docker Kubernetes Terraform Jenkins React Angular Vue Flask Django
EXPERIENCE
Developer 2024
Built created developed implemented every scalable innovative solution technology platform.
PROJECTS
Created built managed delivered optimized technical systems using every listed technology.
"""
    quality_score = score_resume(quality, extract_skills(quality))["total_score"]
    stuffed_score = score_resume(stuffed, extract_skills(stuffed))["total_score"]
    assert stuffed_score < quality_score


def test_many_skills_without_evidence_receive_limited_credit():
    text = "Skills\nPython Java JavaScript TypeScript SQL Docker Kubernetes AWS React Flask Git Linux"
    result = score_resume(text, extract_skills(text))
    assert result["total_score"] <= 15
    assert result["breakdown"]["projects"] == 0
    assert result["breakdown"]["experience"] == 0


def test_strong_prose_resume_receives_content_evidence_without_headings():
    prose = """Maya Shah | maya@example.com | +1 555 444 7788 | github.com/mayashah
Maya is a software engineer with 6 years of experience delivering reliable customer services.
She worked at Example Labs from 2020 to present and led a team that developed Python and Flask APIs,
reducing response time by 35% for 500 users. She designed a PostgreSQL reporting platform and
implemented automated tests that reduced release defects by 20%. She also built a Docker-based
inventory application for a community organization and maintained its Git deployment workflow.
Maya earned a Bachelor of Technology from Example University in 2020.
"""
    result = score_resume(prose, extract_skills(prose))
    assert result["total_score"] >= 60
    assert result["breakdown"]["projects"] > 0
    assert result["breakdown"]["experience"] > 0
    assert result["breakdown"]["education"] > 0


def test_sophisticated_keyword_stuffing_remains_below_evidenced_prose():
    prose = FULL_RESUME + "\n- Optimized API throughput by 35% for 200 users.\n"
    stuffing = """Taylor Smith | taylor@example.com
Technology leader with innovative scalable strategic solutions and results.
Python Java JavaScript TypeScript Go Rust SQL NoSQL MySQL PostgreSQL MongoDB Redis
AWS Azure Docker Kubernetes Terraform Jenkins React Angular Vue Flask Django Git Linux
Built developed implemented optimized delivered managed engineered launched every modern
platform system service application database dashboard tool and cloud solution in 2024.
"""
    quality_score = score_resume(prose, extract_skills(prose))["total_score"]
    stuffed = score_resume(stuffing, extract_skills(stuffing))
    assert stuffed["total_score"] < quality_score
    assert stuffed["total_score"] < 60
