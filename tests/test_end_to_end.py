import io
from pathlib import Path

import pymupdf as fitz
from docx import Document


def make_pdf(text="", pages=1):
    document = fitz.open()
    for page_number in range(pages):
        page = document.new_page()
        if text:
            page.insert_text((72, 72), f"{text} page {page_number + 1}")
    data = document.tobytes()
    document.close()
    return data


def make_docx(*paragraphs):
    stream = io.BytesIO()
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(stream)
    stream.seek(0)
    return stream


def test_complete_docx_flow_and_saved_result(client):
    response = client.post(
        "/api/analyze-resume",
        data={
            "resume": (
                make_docx(
                    "Riya Das | riya@example.com | +91 98765 43210",
                    "SUMMARY",
                    "Python developer building reliable services.",
                    "SKILLS",
                    "Python Flask SQL Git Docker",
                    "PROJECTS",
                    "Built a Flask API for 50 users.",
                ),
                "riya-resume.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            "job_description": "Python Flask SQL Git AWS",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    analysis = response.get_json()
    assert analysis["resume_filename"] == "riya-resume.docx"
    assert {"Python", "Flask", "SQL", "Git", "Docker"} <= set(analysis["detected_skills"])
    assert analysis["job_match"]["keyword_score"] == 80
    assert analysis["job_match"]["missing_skills"] == ["AWS"]

    detail = client.get(f"/api/history/{analysis['id']}")
    result_page = client.get(f"/results/{analysis['id']}")
    assert detail.status_code == 200
    assert detail.get_json()["job_match"]["keyword_score"] == 80
    assert result_page.status_code == 200
    assert b"riya-resume.docx" in result_page.data
    assert b"Job skill comparison" in result_page.data


def test_resume_can_be_analyzed_then_matched_and_updated(client):
    analysis_response = client.post(
        "/api/analyze-resume",
        data={
            "resume": (
                io.BytesIO(make_pdf("dev@example.com Python Flask Git")),
                "developer.pdf",
                "application/pdf",
            )
        },
        content_type="multipart/form-data",
    )
    assert analysis_response.status_code == 201
    analysis = analysis_response.get_json()
    assert analysis["job_match"] is None

    first_match = client.post(
        "/api/match-job",
        json={"analysis_id": analysis["id"], "job_description": "Python Flask Docker Git"},
    )
    assert first_match.status_code == 201
    assert first_match.get_json()["job_match"]["keyword_score"] == 75

    updated_match = client.post(
        "/api/match-job",
        json={"analysis_id": analysis["id"], "job_description": "Python Git"},
    )
    assert updated_match.status_code == 201
    assert updated_match.get_json()["job_match"]["keyword_score"] == 100

    persisted = client.get(f"/api/history/{analysis['id']}").get_json()
    assert persisted["job_match"]["keyword_score"] == 100
    assert persisted["job_match"]["missing_skills"] == []
    assert len(client.get("/api/history").get_json()["analyses"]) == 1


def test_corrupt_and_textless_pdfs_are_rejected_and_removed(app, client):
    upload_dir = Path(app.config["UPLOAD_FOLDER"])
    corrupt = client.post(
        "/api/analyze-resume",
        data={"resume": (io.BytesIO(b"%PDF-not-really"), "broken.pdf", "application/pdf")},
        content_type="multipart/form-data",
    )
    assert corrupt.status_code == 422
    assert "corrupted" in corrupt.get_json()["error"].lower()
    assert list(upload_dir.iterdir()) == []

    empty = client.post(
        "/api/analyze-resume",
        data={"resume": (io.BytesIO(make_pdf()), "empty.pdf", "application/pdf")},
        content_type="multipart/form-data",
    )
    assert empty.status_code == 422
    assert "text-based resume" in empty.get_json()["error"]
    assert list(upload_dir.iterdir()) == []


def test_mime_mismatch_and_oversized_upload_are_rejected(app, client):
    upload_dir = Path(app.config["UPLOAD_FOLDER"])
    wrong_mime = client.post(
        "/api/analyze-resume",
        data={"resume": (io.BytesIO(make_pdf("Python")), "resume.pdf", "text/plain")},
        content_type="multipart/form-data",
    )
    assert wrong_mime.status_code == 415
    assert "does not match" in wrong_mime.get_json()["error"]

    too_large = client.post(
        "/api/analyze-resume",
        data={"resume": (io.BytesIO(b"x" * (5 * 1024 * 1024 + 1)), "large.pdf", "application/pdf")},
        content_type="multipart/form-data",
    )
    assert too_large.status_code == 413
    assert "5 MB" in too_large.get_json()["error"]
    assert list(upload_dir.iterdir()) == []


def test_successful_upload_is_deleted_after_processing(app, client):
    response = client.post(
        "/api/analyze-resume",
        data={
            "resume": (
                io.BytesIO(make_pdf("person@example.com Python SQL")),
                "My Resume 2026.pdf",
                "application/pdf",
            )
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    files = list(Path(app.config["UPLOAD_FOLDER"]).iterdir())
    assert files == []


def test_error_routes_and_static_assets(client):
    assert client.get("/static/css/style.css").status_code == 200
    assert client.get("/static/js/app.js").status_code == 200

    missing_api = client.get("/api/history/999999")
    missing_page = client.get("/results/999999")
    unknown_api = client.get("/api/not-a-route")
    assert missing_api.status_code == 404
    assert missing_api.is_json
    assert missing_page.status_code == 404
    assert b"Analysis not found" in missing_page.data
    assert unknown_api.status_code == 404
    assert unknown_api.is_json


def test_match_job_rejects_missing_or_unknown_analysis(client):
    no_id = client.post("/api/match-job", json={"job_description": "Python"})
    invalid = client.post(
        "/api/match-job",
        json={"analysis_id": 999999, "job_description": "Python"},
    )
    assert no_id.status_code == 400
    assert invalid.status_code == 400


def test_history_limit_is_bounded_and_validated(client):
    for _ in range(3):
        assert client.post("/api/demo").status_code == 201
    assert len(client.get("/api/history?limit=2").get_json()["analyses"]) == 2
    assert len(client.get("/api/history?limit=0").get_json()["analyses"]) == 1
    assert len(client.get("/api/history?limit=500").get_json()["analyses"]) == 3


def test_same_resume_and_job_produce_identical_match_through_both_endpoints(client):
    job = """Requirements
Python, Flask, SQL
Preferred
Docker
Responsibilities
Build reliable APIs for customers.
"""
    response = client.post(
        "/api/analyze-resume",
        data={
            "resume": (make_docx(
                "Sam Dev | sam@example.com",
                "Skills", "Python Flask SQL Git",
                "Projects", "Built reliable Flask APIs with SQL for 100 customers.",
            ), "sam.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            "job_description": job,
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    uploaded = response.get_json()
    later = client.post("/api/match-job", json={"analysis_id": uploaded["id"], "job_description": job})
    assert later.status_code == 201
    fields = ("keyword_score", "semantic_score", "final_match_score", "matched_skills", "missing_skills")
    assert {field: uploaded["job_match"][field] for field in fields} == {
        field: later.get_json()["job_match"][field] for field in fields
    }
    detail = client.get(f"/api/history/{uploaded['id']}").get_json()
    assert len(detail["job_matches"]) == 2
