
import pymupdf as fitz
import pytest

from services.resume_parser import (
    ResumeParseError,
    clean_text,
    extract_pdf_text,
    extract_resume_text,
)


def test_extracts_text_from_every_pdf_page(tmp_path):
    path = tmp_path / "resume.pdf"
    document = fitz.open()
    page_one = document.new_page()
    page_one.insert_text((72, 72), "Asha Patel - Python Developer")
    page_two = document.new_page()
    page_two.insert_text((72, 72), "Projects - Flask API")
    document.save(path)
    document.close()

    text = extract_pdf_text(path)
    assert "Asha Patel" in text
    assert "Flask API" in text


def test_rejects_fake_pdf(tmp_path):
    path = tmp_path / "fake.pdf"
    path.write_text("not a pdf", encoding="utf-8")
    with pytest.raises(ResumeParseError, match="valid PDF"):
        extract_resume_text(path)


def test_empty_pdf_has_friendly_error(tmp_path):
    path = tmp_path / "empty.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()
    with pytest.raises(ResumeParseError, match="Unable to extract"):
        extract_pdf_text(path)


def test_clean_text_removes_repeated_spaces_and_blank_lines():
    assert clean_text("Python    Flask\n\n\nSQL") == "Python Flask\nSQL"
