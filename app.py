"""ResumeIQ Flask application and small SQLite repository layer."""

import json
import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request, session
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from config import MAX_JOB_DESCRIPTION_CHARS, MAX_UPLOAD_BYTES
from services.job_matcher import match_job
from services.resume_parser import ResumeParseError, extract_resume_text
from services.resume_scorer import score_resume
from services.semantic_matcher import semantic_profile
from services.skill_extractor import extract_skills, flatten_skills

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DATABASE_PATH = BASE_DIR / "database" / "app.db"
ALLOWED_EXTENSIONS = {".pdf", ".docx"}
ALLOWED_MIME_TYPES = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/octet-stream", "application/zip"},
}


def resolve_secret_key(test_config=None) -> str:
    """Return an explicitly authorized secret or fail closed."""
    configured = (test_config or {}).get("SECRET_KEY") or os.environ.get("SECRET_KEY")
    if configured:
        return configured
    if (test_config or {}).get("TESTING"):
        return "resumeiq-isolated-test-key"
    environment = os.environ.get("RESUMEIQ_ENV", "").casefold()
    if environment in {"development", "local"}:
        return "resumeiq-explicit-development-key-not-for-deployment"
    raise RuntimeError(
        "SECRET_KEY is required. Set it in the environment, or explicitly set "
        "RESUMEIQ_ENV=development for local-only use."
    )


def create_app(test_config=None) -> Flask:
    """Create and configure the application."""
    secret_key = resolve_secret_key(test_config)
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES, UPLOAD_FOLDER=str(UPLOAD_DIR),
                      DATABASE=str(DATABASE_PATH), SECRET_KEY=secret_key,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
    if test_config:
        app.config.update(test_config)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    init_database(app.config["DATABASE"])

    @app.before_request
    def establish_owner_and_check_origin():
        session.setdefault("owner_id", uuid.uuid4().hex)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("Origin")
            if origin and urlsplit(origin).netloc != request.host:
                return api_error("Cross-origin state-changing requests are not allowed.", 403)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; font-src https://fonts.gstatic.com; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        return response

    @app.get("/")
    def index():
        resume_text = (BASE_DIR / "data" / "demo_resume.txt").read_text(encoding="utf-8")
        job_text = (BASE_DIR / "data" / "demo_job.txt").read_text(encoding="utf-8")
        skills = extract_skills(resume_text)
        preview = {"resume": score_resume(resume_text, skills), "skills": flatten_skills(skills),
                   "match": match_job(flatten_skills(skills), job_text, resume_text)}
        return render_template("index.html", demo_preview=preview)

    @app.get("/dashboard")
    def dashboard():
        return render_template("dashboard.html")

    @app.get("/results/<analysis_id>")
    def result_page(analysis_id):
        record = get_analysis(app.config["DATABASE"], analysis_id, session["owner_id"])
        return (render_template("result.html", analysis=record), 200 if record else 404)

    @app.post("/api/analyze-resume")
    def analyze_resume_api():
        upload = request.files.get("resume")
        if not upload or not upload.filename:
            return api_error("Please choose a PDF or DOCX resume.", 400)
        original_filename = upload.filename
        extension = Path(original_filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            return api_error("Only PDF and DOCX files are supported.", 415)
        if upload.mimetype not in ALLOWED_MIME_TYPES[extension]:
            return api_error("The uploaded file type does not match its extension.", 415)
        job_description = request.form.get("job_description", "")
        if not isinstance(job_description, str) or len(job_description) > MAX_JOB_DESCRIPTION_CHARS:
            return api_error(f"Job descriptions must be at most {MAX_JOB_DESCRIPTION_CHARS:,} characters.", 422)
        stored_path = Path(app.config["UPLOAD_FOLDER"]) / f"{uuid.uuid4().hex}{extension}"
        try:
            upload.save(stored_path)
            resume_text = extract_resume_text(stored_path)
            display_name = Path(original_filename.replace("\\", "/")).name[:255] or f"resume{extension}"
            record = run_analysis(app.config["DATABASE"], display_name, resume_text,
                                  job_description.strip(), session["owner_id"])
            return jsonify({"message": "Analysis complete.", **public_analysis(record)}), 201
        except ResumeParseError as exc:
            return api_error(str(exc), 422)
        except Exception:
            app.logger.exception("Unexpected resume analysis error")
            return api_error("We could not analyze this resume. Please try another file.", 500)
        finally:
            stored_path.unlink(missing_ok=True)

    @app.post("/api/match-job")
    def match_job_api():
        payload, error = json_object_payload()
        if error:
            return error
        analysis_id = payload.get("analysis_id")
        description = payload.get("job_description")
        if not isinstance(analysis_id, str) or not analysis_id:
            return api_error("A valid analysis ID is required.", 400)
        if not isinstance(description, str) or not description.strip():
            return api_error("Please enter a job description.", 400)
        if len(description) > MAX_JOB_DESCRIPTION_CHARS:
            return api_error(f"Job descriptions must be at most {MAX_JOB_DESCRIPTION_CHARS:,} characters.", 422)
        record = get_analysis(app.config["DATABASE"], analysis_id, session["owner_id"])
        if not record:
            return api_error("Analysis not found.", 404)
        job_result = match_job(record["detected_skills"], description, record["semantic_profile"])
        save_job_match(app.config["DATABASE"], record["database_id"], description, job_result)
        return jsonify({"analysis_id": analysis_id, "job_match": job_result}), 201

    @app.post("/api/demo")
    def demo_api():
        resume_text = (BASE_DIR / "data" / "demo_resume.txt").read_text(encoding="utf-8")
        job_text = (BASE_DIR / "data" / "demo_job.txt").read_text(encoding="utf-8")
        record = run_analysis(app.config["DATABASE"], "synthetic-demo-resume.txt", resume_text, job_text, session["owner_id"])
        return jsonify({"message": "Demo analysis complete.", **public_analysis(record)}), 201

    @app.get("/api/history")
    def history_api():
        requested_limit = request.args.get("limit", 20, type=int)
        limit = min(max(20 if requested_limit is None else requested_limit, 1), 100)
        return jsonify({"analyses": list_history(app.config["DATABASE"], session["owner_id"], limit)})

    @app.get("/api/history/<analysis_id>")
    def history_detail_api(analysis_id):
        record = get_analysis(app.config["DATABASE"], analysis_id, session["owner_id"])
        return jsonify(public_analysis(record)) if record else api_error("Analysis not found.", 404)

    @app.delete("/api/history/<analysis_id>")
    def delete_history_api(analysis_id):
        deleted = delete_analysis(app.config["DATABASE"], analysis_id, session["owner_id"])
        return (jsonify({"message": "Analysis deleted."}), 200) if deleted else api_error("Analysis not found.", 404)

    @app.errorhandler(RequestEntityTooLarge)
    def file_too_large(_error): return api_error("The file is too large. Maximum size is 5 MB.", 413)

    @app.errorhandler(BadRequest)
    def bad_request(_error): return api_error("The request body is malformed.", 400)

    @app.errorhandler(404)
    def not_found(_error):
        return api_error("Resource not found.", 404) if request.path.startswith("/api/") else (render_template("result.html", analysis=None), 404)

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return api_error("Method not allowed for this endpoint.", 405) if request.path.startswith("/api/") else ("Method Not Allowed", 405)
    return app


def api_error(message: str, status: int): return jsonify({"error": message}), status


def json_object_payload():
    if not request.is_json:
        return None, api_error("A JSON object is required.", 415)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, api_error("The JSON body must be an object.", 400)
    return payload, None


@contextmanager
def connect_db(database_path):
    """Yield a row-aware SQLite connection and always close it."""
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def create_schema(db) -> None:
    """Create the current tables when starting from an empty database."""
    db.execute("""CREATE TABLE IF NOT EXISTS analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT, public_id TEXT UNIQUE, owner_id TEXT,
        resume_filename TEXT NOT NULL, resume_score INTEGER NOT NULL, detected_skills TEXT NOT NULL,
        semantic_profile TEXT NOT NULL DEFAULT '{}', score_breakdown TEXT NOT NULL, strengths TEXT NOT NULL,
        weaknesses TEXT NOT NULL, suggestions TEXT NOT NULL, created_at TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS job_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id INTEGER NOT NULL, job_description TEXT NOT NULL,
        match_percentage INTEGER NOT NULL, keyword_score INTEGER NOT NULL DEFAULT 0,
        semantic_score INTEGER NOT NULL DEFAULT 0, matching_skills TEXT NOT NULL, missing_skills TEXT NOT NULL,
        job_skills TEXT NOT NULL, required_skills TEXT NOT NULL DEFAULT '[]', preferred_skills TEXT NOT NULL DEFAULT '[]',
        general_skills TEXT NOT NULL DEFAULT '[]', recommendations TEXT NOT NULL, explanation TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL, FOREIGN KEY (analysis_id) REFERENCES analyses(id) ON DELETE CASCADE)""")


def migrate_schema(db) -> None:
    """Add analysis fields and isolate incompatible legacy match tables."""
    columns = {row[1] for row in db.execute("PRAGMA table_info(analyses)")}
    for name, definition in (
        ("public_id", "TEXT"), ("owner_id", "TEXT"),
        ("semantic_profile", "TEXT NOT NULL DEFAULT '{}'"),
    ):
        if name not in columns:
            db.execute(f"ALTER TABLE analyses ADD COLUMN {name} {definition}")
    existing_sql = (db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='job_matches'"
    ).fetchone() or [""])[0] or ""
    required = {"keyword_score", "semantic_score", "required_skills", "preferred_skills", "general_skills", "explanation"}
    existing = {row[1] for row in db.execute("PRAGMA table_info(job_matches)")} if existing_sql else set()
    if existing_sql and ("UNIQUE" in existing_sql.upper() or not required <= existing):
        db.execute("ALTER TABLE job_matches RENAME TO job_matches_legacy")
        create_schema(db)


def backfill_legacy_data(db) -> None:
    """Backfill identifiers and copy rows from the original one-match schema."""
    for row in db.execute("SELECT id FROM analyses WHERE public_id IS NULL").fetchall():
        db.execute(
            "UPDATE analyses SET public_id=?, owner_id=COALESCE(owner_id, 'legacy') WHERE id=?",
            (uuid.uuid4().hex, row["id"]),
        )
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='job_matches_legacy'").fetchone():
        db.execute("""INSERT INTO job_matches (id,analysis_id,job_description,match_percentage,keyword_score,semantic_score,
            matching_skills,missing_skills,job_skills,required_skills,preferred_skills,general_skills,recommendations,explanation,created_at)
            SELECT id,analysis_id,job_description,match_percentage,match_percentage,0,matching_skills,missing_skills,job_skills,
            '[]','[]',job_skills,recommendations,'Migrated keyword-only result.',created_at FROM job_matches_legacy""")
        db.execute("DROP TABLE job_matches_legacy")


def create_indexes(db) -> None:
    db.execute("CREATE INDEX IF NOT EXISTS idx_analyses_owner_created ON analyses(owner_id, id DESC)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_job_matches_analysis ON job_matches(analysis_id, id DESC)")


def init_database(database_path) -> None:
    """Create, migrate, and backfill the database in explicit stages."""
    with connect_db(database_path) as db:
        create_schema(db)
        migrate_schema(db)
        backfill_legacy_data(db)
        create_indexes(db)


def run_analysis(database_path, filename: str, resume_text: str, job_description: str, owner_id: str) -> dict:
    skills_grouped = extract_skills(resume_text)
    resume_result = score_resume(resume_text, skills_grouped)
    profile = semantic_profile(resume_text)
    created_at, public_id = datetime.now(timezone.utc).isoformat(timespec="seconds"), uuid.uuid4().hex
    with connect_db(database_path) as db:
        cursor = db.execute("""INSERT INTO analyses (public_id,owner_id,resume_filename,resume_score,detected_skills,
            semantic_profile,score_breakdown,strengths,weaknesses,suggestions,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (public_id, owner_id, filename, resume_result["total_score"], json.dumps(skills_grouped), json.dumps(profile),
             json.dumps(resume_result["breakdown"]), json.dumps(resume_result["strengths"]),
             json.dumps(resume_result["weaknesses"]), json.dumps(resume_result["suggestions"]), created_at))
        internal_id = cursor.lastrowid
    if job_description:
        save_job_match(database_path, internal_id, job_description,
                       match_job(flatten_skills(skills_grouped), job_description, profile))
    return get_analysis(database_path, public_id, owner_id)


def save_job_match(database_path, analysis_id: int, description: str, result: dict) -> None:
    with connect_db(database_path) as db:
        db.execute("""INSERT INTO job_matches (analysis_id,job_description,match_percentage,keyword_score,semantic_score,
            matching_skills,missing_skills,job_skills,required_skills,preferred_skills,general_skills,recommendations,explanation,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (analysis_id, description, result["final_match_score"],
            result["keyword_score"], result["semantic_score"], json.dumps(result["matched_skills"]),
            json.dumps(result["missing_skills"]), json.dumps(result["job_skills"]), json.dumps(result["required_skills"]),
            json.dumps(result["preferred_skills"]), json.dumps(result["general_skills"]), json.dumps(result["recommendations"]),
            result["explanation"], datetime.now(timezone.utc).isoformat(timespec="seconds")))


def _loads(value, fallback):
    try: return json.loads(value) if value is not None else fallback
    except (TypeError, json.JSONDecodeError): return fallback


def public_analysis(record: dict) -> dict:
    """Remove the private relational key from API responses."""
    return {key: value for key, value in record.items() if key not in {"database_id", "semantic_profile"}}


def get_analysis(database_path, public_id: str, owner_id: str):
    with connect_db(database_path) as db:
        row = db.execute("SELECT * FROM analyses WHERE public_id=? AND owner_id=?", (public_id, owner_id)).fetchone()
        match_rows = [] if not row else db.execute(
            """SELECT job_description,match_percentage,keyword_score,semantic_score,matching_skills,
            missing_skills,job_skills,required_skills,preferred_skills,general_skills,recommendations,
            explanation,created_at FROM job_matches WHERE analysis_id=? ORDER BY id DESC""",
            (row["id"],),
        ).fetchall()
    if not row:
        return None
    grouped = _loads(row["detected_skills"], {})

    def serialize_match(match_row):
        return {
            "final_match_score": match_row["match_percentage"], "match_percentage": match_row["match_percentage"],
            "keyword_score": match_row["keyword_score"], "semantic_score": match_row["semantic_score"],
            "matched_skills": _loads(match_row["matching_skills"], []),
            "missing_skills": _loads(match_row["missing_skills"], []),
            "job_skills": _loads(match_row["job_skills"], []),
            "required_skills": _loads(match_row["required_skills"], []),
            "preferred_skills": _loads(match_row["preferred_skills"], []),
            "general_skills": _loads(match_row["general_skills"], []),
            "recommendations": _loads(match_row["recommendations"], []),
            "explanation": match_row["explanation"], "job_description": match_row["job_description"],
            "created_at": match_row["created_at"],
        }

    matches = [serialize_match(match_row) for match_row in match_rows]
    return {"id": row["public_id"], "database_id": row["id"], "resume_filename": row["resume_filename"],
            "resume_score": row["resume_score"], "score_label": "Resume Structure & Content Score",
            "detected_skills": flatten_skills(grouped), "skills_by_category": grouped,
            "semantic_profile": _loads(row["semantic_profile"], {}),
            "score_breakdown": _loads(row["score_breakdown"], {}), "strengths": _loads(row["strengths"], []),
            "weaknesses": _loads(row["weaknesses"], []), "suggestions": _loads(row["suggestions"], []),
            "created_at": row["created_at"], "job_match": matches[0] if matches else None,
            "job_matches": matches}


def list_history(database_path, owner_id: str, limit=20):
    with connect_db(database_path) as db:
        rows = db.execute("""SELECT a.public_id AS id,a.resume_filename,a.resume_score,a.created_at,
            (SELECT match_percentage FROM job_matches WHERE analysis_id=a.id ORDER BY id DESC LIMIT 1) match_percentage,
            (SELECT COUNT(*) FROM job_matches WHERE analysis_id=a.id) match_count FROM analyses a
            WHERE a.owner_id=? ORDER BY a.id DESC LIMIT ?""", (owner_id, limit)).fetchall()
    return [dict(row) for row in rows]


def delete_analysis(database_path, public_id: str, owner_id: str) -> bool:
    with connect_db(database_path) as db:
        cursor = db.execute("DELETE FROM analyses WHERE public_id=? AND owner_id=?", (public_id, owner_id))
    return cursor.rowcount == 1


app = create_app()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run()
