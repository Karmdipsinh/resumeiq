# ResumeIQ — Explainable Resume Analyzer & Job Matcher

ResumeIQ uses rule-based skill extraction, explainable heuristic scoring, and classical TF-IDF cosine similarity. It parses PDF/DOCX resumes and compares recognized evidence with job requirements. It has no machine-learning model and sends nothing to an external AI API. It does not claim to reproduce recruiter or ATS decisions.

## Features

- Bounded text extraction from text-based PDFs and DOCX files, including DOCX tables
- Catalog/alias skill extraction with canonical names such as HTML5 → HTML, Python 3 → Python, k8s → Kubernetes, and sklearn → Scikit-learn
- Context safeguards for ambiguous C, R, Go, Express, and Spring mentions
- Lightweight guards for explicit negation ("no experience with") and aspiration ("want to learn")
- A heuristic resume structure/content score that can recognize substantive prose evidence without exact headings
- Required, preferred, and general job-skill weighting with known and generic section-boundary resets
- Deterministic, bounded TF-IDF cosine similarity using a persisted derived resume profile
- A documented 70% final-score cap when a job contains only one recognized skill
- Anonymous session-scoped history, random public IDs, multiple matches per analysis, and cascade deletion
- Local synthetic evaluation fixtures, Python regression tests, and dependency-free JavaScript behavior tests

## Architecture

```text
PDF/DOCX -> bounded local parsing -> skill extraction -> heuristic resume score
                 |
                 +-> hashed token-frequency profile --------------------+
Job description -> skill extraction -> requirement classification       |
                 +-> weighted keyword coverage                          |
                 +-> TF-IDF/cosine comparison with resume profile ------+
                                      -> explainable combined match -> SQLite
```

Important files:

- `app.py`: Flask routes, request validation, database schema/migrations, and repository operations
- `config.py`: processing limits and heuristic matching weights
- `services/resume_parser.py`: PDF/DOCX parsing and DOCX archive protections
- `services/skill_extractor.py`: aliases, contextual ambiguity checks, and narrow intent guards
- `services/resume_scorer.py`: evidence-based heuristic score and feedback
- `services/semantic_matcher.py`: token profiles, sparse TF-IDF, and cosine similarity
- `services/job_matcher.py`: job section classification, weighted keyword score, and final formula
- `eval/` and `scripts/evaluate_matching.py`: small synthetic regression evaluation
- `static/js/app_helpers.test.js`: file/form validation, history/XSS, and API-error tests

## Resume scoring

The **Resume Structure & Content Score** is a 100-point heuristic: contact (10), summary (10), skills (20), education (15), projects (15), experience (15), certifications (5), and completeness/evidence (10).

Headings alone earn no section credit. When headings are absent, the scorer can infer limited category evidence from action-based prose containing role/date or years-of-experience context, project/technical context, technologies used, and measurable outcomes. Skill-list credit is limited unless project or experience evidence supports those skills. Repeated or unusually dense unsupported skill lists are discounted. The score has not been validated against recruiters or commercial ATS products and must not be treated as a hiring prediction.

## Job matching and TF-IDF

Recognized required skills receive weight 2.0, general skills 1.0, and preferred skills 0.5:

```text
keyword_score = matched weighted skills / all weighted job skills * 100
final_match_score = keyword_score * 0.60 + tfidf_cosine_score * 0.40
```

Headings such as Requirements, Qualifications, and Must Have enter required state. Preferred and Nice to Have enter preferred state. Responsibilities, What You'll Do, About, Description, Benefits, and Perks reset the state to general. Short standalone title-like headings—such as `Our Culture:`—also create a general boundary, preventing an earlier state from leaking into an unrelated section.

TF-IDF input is limited to 50,000 characters. Term frequency and smoothed inverse document frequency produce sparse vectors, and cosine similarity is converted to 0–100. This is classical information retrieval/NLP, not deep learning or contextual language understanding.

When only one catalog skill is recognized in the job text, the final score is capped at 70%. This is a heuristic sparse-evidence guardrail, not a learned threshold; the uncapped keyword component remains visible.

## Privacy and matching consistency

Uploads receive random UUID filenames and are deleted in a `finally` block immediately after parsing. Raw extracted resume text is never persisted.

Before matching, ResumeIQ lowercases and tokenizes the bounded resume text, hashes each token with SHA-256, and stores only token hashes and frequencies. Upload-time and later matches both use that same derived profile, so the same resume, job description, and scoring configuration produce identical keyword, TF-IDF, and final components.

The profile is less revealing than raw text but is not encryption or anonymization: hashes of predictable words may be guessed. Treat the database as sensitive derived data. Job descriptions, displayed filenames, scores, skills, and feedback are stored until the session deletes the analysis or the local database is removed.

## Database

`analyses` stores the random public ID, anonymous session owner, displayed filename, score, skills, token profile, feedback, and timestamp. `job_matches` has a many-to-one foreign key and stores every comparison. The detail API returns all matches newest-first in `job_matches`; `job_match` is the newest result for UI compatibility.

Startup code separates schema creation, migration, legacy backfill, and index creation. Foreign keys are enabled, match rows cascade on analysis deletion, and owner/history lookup indexes are created. Legacy analyses have an empty semantic profile because raw historical text cannot be reconstructed; re-uploading is required for meaningful later TF-IDF comparisons on those rows.

## Security controls

- 5 MB request limit and 20,000-character job-description limit
- MIME/extension validation plus PDF magic and DOCX ZIP validation
- DOCX uncompressed-size and compression-ratio limits; 200,000-character extracted-text limit
- Parameterized SQL, Jinja auto-escaping, and explicit client-side HTML escaping
- Same-origin checks for state-changing requests; HttpOnly/SameSite session cookie
- CSP, frame, MIME-sniffing, referrer, and permissions headers
- Session ownership checks and non-guessable public identifiers
- JSON errors for malformed API input without returning stack traces

There is no user account system. Clearing the session cookie makes that browser's prior analyses inaccessible through the application.

## Installation and running

Python 3.12 or newer is recommended.

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Open `http://127.0.0.1:5000`.

Startup fails closed when `SECRET_KEY` is absent unless local development is explicitly selected. For local-only use:

```powershell
$env:RESUMEIQ_ENV="development"
python app.py
```

For deployment, set a strong stable `SECRET_KEY`; `RESUMEIQ_ENV=production` is recommended for clarity. Missing both the secret and explicit development mode raises `RuntimeError`. `.env.example` contains instructions and a placeholder, not a real secret.

## API

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/analyze-resume` | Multipart PDF/DOCX plus optional `job_description` |
| `POST` | `/api/match-job` | JSON `analysis_id` and `job_description`; append another match |
| `POST` | `/api/demo` | Analyze bundled synthetic data |
| `GET` | `/api/history` | List analyses owned by the current session |
| `GET` | `/api/history/<id>` | Read one owned analysis and all its matches |
| `DELETE` | `/api/history/<id>` | Delete an owned analysis and its matches |

Validation errors use JSON `{ "error": "..." }` and appropriate 400, 403, 413, 415, or 422 statuses.

## Tests and evaluation

```powershell
pytest -q
pytest --cov
ruff check .
node --test static/js/app_helpers.test.js
python scripts/evaluate_matching.py
```

`eval/skill_extraction_cases.json` currently contains 37 small synthetic positive and adversarial cases covering ambiguous prose, structural technical lists, clause-scoped negation, aspiration, aliases, and version suffixes. The current measured fixture result is 62 true positives, 0 false positives, and 0 false negatives: precision `1.000`, recall `1.000`, F1 `1.000`. Those numbers only describe this explicit regression set and do not estimate behavior on unseen resumes.

`eval/matching_cases.json` contains five deterministic component-level scenarios (strong, alias, semantic-only, unrelated, and one-skill capped). No matching accuracy is reported because this is not a representative labeled corpus.

## Screenshots

No screenshots are committed because browser capture tooling was unavailable for this pass. [docs/screenshots/README.md](docs/screenshots/README.md) lists the four real application screens to capture using only synthetic demo data.

## Limitations

- Scanned/image-only PDFs require OCR, which is not included.
- Catalog and section extraction are transparent heuristics and may misclassify unusual wording.
- Intent guards support a few explicit phrase patterns, not general negation or intent understanding.
- TF-IDF captures shared tokens, not context, seniority, or equivalent experience.
- The scorer and matching weights are hand-designed and unvalidated.
- Anonymous sessions and SQLite suit a local portfolio deployment, not authenticated multi-tenant use.

## License

MIT. See `LICENSE`. Dependencies retain their upstream licenses.
