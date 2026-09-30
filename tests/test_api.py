import io

import pymupdf as fitz


def make_pdf(text):
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def test_pages_load(client):
    home = client.get("/")
    assert home.status_code == 200
    assert home.headers["X-Content-Type-Options"] == "nosniff"
    assert home.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in home.headers["Content-Security-Policy"]
    assert client.get("/dashboard").status_code == 200


def test_demo_uses_algorithms_and_creates_history(client):
    response = client.post("/api/demo")
    assert response.status_code == 201
    result = response.get_json()
    assert 0 <= result["resume_score"] <= 100
    assert result["detected_skills"]
    assert result["job_match"]["job_skills"]

    history = client.get("/api/history").get_json()["analyses"]
    assert len(history) == 1
    assert history[0]["id"] == result["id"]
    assert client.get(f"/results/{result['id']}").status_code == 200


def test_real_pdf_upload_and_job_match(client):
    resume = "alex@example.com Python Flask SQL Git PROJECTS Built API"
    response = client.post(
        "/api/analyze-resume",
        data={
            "resume": (io.BytesIO(make_pdf(resume)), "resume.pdf"),
            "job_description": "Python Flask Docker Git",
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    data = response.get_json()
    assert {"Python", "Flask", "SQL", "Git"} <= set(data["detected_skills"])
    assert data["job_match"]["keyword_score"] == 75
    assert 0 <= data["job_match"]["semantic_score"] <= 100
    assert data["job_match"]["missing_skills"] == ["Docker"]


def test_invalid_and_missing_uploads_are_rejected(client):
    missing = client.post("/api/analyze-resume", data={})
    assert missing.status_code == 400
    invalid = client.post(
        "/api/analyze-resume",
        data={"resume": (io.BytesIO(b"hello"), "resume.txt")},
        content_type="multipart/form-data",
    )
    assert invalid.status_code == 415


def test_match_job_validates_empty_description(client):
    result = client.post("/api/demo").get_json()
    response = client.post("/api/match-job", json={"analysis_id": result["id"], "job_description": ""})
    assert response.status_code == 400


def test_api_unsupported_method_is_json_405(client):
    response = client.get("/api/demo")
    assert response.status_code == 405
    assert response.is_json
    assert response.get_json()["error"] == "Method not allowed for this endpoint."
