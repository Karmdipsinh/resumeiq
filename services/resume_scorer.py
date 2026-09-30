"""Explainable heuristic resume structure and evidence scoring."""

import re

from services.skill_extractor import flatten_skills

SECTION_PATTERNS = {
    "summary": r"(?im)^\s*(?:professional\s+summary|summary|profile|about\s+me|career\s+objective|objective)\s*:?\s*$",
    "skills": r"(?im)^\s*(?:technical\s+skills|key\s+skills|core\s+competencies|skills\s*&\s*tools|skills|tools|technologies|tech stack)\s*:?\s*$",
    "education": r"(?im)^\s*(?:education|educational\s+qualifications?|academic\s+background|academic\s+history|qualifications?)\s*:?\s*$",
    "projects": r"(?im)^\s*(?:projects?|key\s+projects|academic\s+projects|personal\s+projects|selected\s+work|portfolio)\s*:?\s*$",
    "experience": r"(?im)^\s*(?:professional\s+experience|work\s+experience|employment\s+history|work\s+history|career\s+history|relevant\s+experience|internship\s+experience|experience|internships?)\s*:?\s*$",
    "certifications": r"(?im)^\s*(?:certifications?|certificates?|licenses?|professional\s+development)\s*:?\s*$",
}
ACTION_PATTERN = re.compile(
    r"\b(?:achieved|automated|built|created|delivered|developed|implemented|improved|increased|led|managed|"
    r"optimized|reduced|designed|engineered|launched|maintained|migrated|tested)\b",
    re.IGNORECASE,
)
METRIC_PATTERN = re.compile(
    r"(?:\+?\d+(?:\.\d+)?\s*%|\+?\d+(?:\.\d+)?x\b|\b\d+(?:\.\d+)?\s*(?:users?|hours?|days?|projects?|clients?|requests?|records?))",
    re.IGNORECASE,
)
ROLE_PATTERN = re.compile(r"\b(?:intern|engineer|developer|analyst|manager|consultant|designer|researcher)\b", re.IGNORECASE)
DATE_PATTERN = re.compile(r"\b(?:(?:19|20)\d{2}|present|current)\b", re.IGNORECASE)
YEARS_EXPERIENCE_PATTERN = re.compile(r"\b\d{1,2}\+?\s+years?\b", re.IGNORECASE)
PROJECT_CONTEXT_PATTERN = re.compile(
    r"\b(?:project|application|app|service|api|platform|system|tool|website|pipeline|database|dashboard)\b",
    re.IGNORECASE,
)
EMPLOYMENT_CONTEXT_PATTERN = re.compile(
    r"\b(?:worked|role|responsib|company|team|clients?|employed|experience)\w*\b",
    re.IGNORECASE,
)


def _section_body(text: str, section: str) -> str:
    match = re.search(SECTION_PATTERNS[section], text)
    if not match:
        return ""
    start = match.end()
    ends = [start + found.start() for name, pattern in SECTION_PATTERNS.items() if name != section
            for found in [re.search(pattern, text[start:])] if found]
    return text[start:min(ends) if ends else len(text)].strip()


def _words(text: str) -> list[str]:
    return re.findall(r"\b[A-Za-z][A-Za-z+#.-]*\b", text)


def _evidence_lines(text: str) -> list[str]:
    clauses = [
        clause.strip(" -*•\t")
        for clause in re.split(r"(?:\r?\n|(?<=[.!?])\s+|;\s+)", text)
        if clause.strip()
    ]
    return [clause for clause in clauses if len(_words(clause)) >= 6 and ACTION_PATTERN.search(clause)]


def has_valid_phone(text: str) -> bool:
    """Detect plausible phone numbers while rejecting year ranges."""
    for candidate in re.findall(r"(?<!\w)\+?\d[\d ().-]{6,}\d(?!\w)", text):
        digits = re.sub(r"\D", "", candidate)
        if 10 <= len(digits) <= 15 and not re.fullmatch(r"\s*\d{4}\s*[-–]\s*\d{4}\s*", candidate):
            return True
    return False


def measurable_outcomes(text: str) -> list[str]:
    """Return genuine percentage, multiplier, and count signals."""
    return METRIC_PATTERN.findall(text or "")


def score_resume(text: str | None, skills_grouped=None) -> dict:
    """Calculate a bounded heuristic score from substantive resume evidence."""
    text = (text or "").strip()
    keys = ("contact", "summary", "skills", "education", "projects", "experience", "certifications", "completeness")
    if not text:
        return {"total_score": 0, "breakdown": {key: 0 for key in keys}, "strengths": [],
                "weaknesses": ["The resume does not contain readable text."],
                "suggestions": ["Upload a text-based resume with your relevant information."]}

    skills = flatten_skills(skills_grouped or {})
    words = _words(text)
    word_count = len(words)
    bodies = {name: _section_body(text, name) for name in SECTION_PATTERNS}
    all_evidence_lines = _evidence_lines(text)
    email = bool(re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.IGNORECASE))
    phone = has_valid_phone(text)
    link = bool(re.search(r"(?:https?://|www\.|linkedin\.com|github\.com)", text, re.IGNORECASE))
    breakdown = {"contact": (4 if email else 0) + (4 if phone else 0) + (2 if link else 0)}

    summary_source = bodies["summary"]
    if not summary_source:
        opening = re.split(r"(?:\r?\n\s*\r?\n|(?<=[.!?])\s+)", text, maxsplit=1)[0]
        if ROLE_PATTERN.search(opening) and 10 <= len(_words(opening)) <= 60:
            summary_source = opening
    summary_words = _words(summary_source)
    summary_sentences = len(re.findall(r"[.!?](?:\s|$)", summary_source))
    breakdown["summary"] = min(10, 4 + len(summary_words) // 8 + min(2, summary_sentences)) if len(summary_words) >= 10 else 0

    evidence_text = "\n".join((bodies["projects"], bodies["experience"])) or "\n".join(all_evidence_lines)
    evidenced_skills = sum(bool(re.search(rf"(?i)(?<!\w){re.escape(skill)}(?!\w)", evidence_text)) for skill in skills)
    breakdown["skills"] = min(20, min(12, len(skills) * 2) + min(8, evidenced_skills * 2))

    education = bodies["education"]
    if not education:
        has_degree = re.search(
            r"\b(?:B\.?Tech|M\.?Tech|B\.?E\.?|M\.?E\.?|BSc|MSc|Bachelor|Master|Diploma|Ph\.?D)\b",
            text,
            re.IGNORECASE,
        )
        has_institution = re.search(r"\b(?:University|College|Institute|School)\b", text, re.IGNORECASE)
        if has_degree and has_institution:
            education = text
    degree = bool(re.search(r"\b(?:B\.?Tech|M\.?Tech|B\.?E\.?|M\.?E\.?|BSc|MSc|Bachelor|Master|Diploma|Ph\.?D)\b", education, re.IGNORECASE))
    institution = bool(re.search(r"\b(?:University|College|Institute|School)\b", education, re.IGNORECASE))
    breakdown["education"] = min(15, (7 if degree else 0) + (4 if institution else 0) + (3 if DATE_PATTERN.search(education) else 0)) if len(_words(education)) >= 4 else 0

    project_source = bodies["projects"]
    project_lines = _evidence_lines(project_source)
    if not project_lines:
        project_lines = [line for line in all_evidence_lines if PROJECT_CONTEXT_PATTERN.search(line)]
        if project_lines:
            project_source = "\n".join(project_lines)
    project_metrics = measurable_outcomes(project_source)
    breakdown["projects"] = min(15, 4 + len(project_lines) * 3 + min(4, len(project_metrics) * 2)) if project_lines else 0

    experience = bodies["experience"]
    experience_lines = _evidence_lines(experience)
    context = bool(ROLE_PATTERN.search(experience) and (DATE_PATTERN.search(experience) or YEARS_EXPERIENCE_PATTERN.search(experience)))
    prose_experience = (
        ROLE_PATTERN.search(text)
        and (DATE_PATTERN.search(text) or YEARS_EXPERIENCE_PATTERN.search(text))
        and EMPLOYMENT_CONTEXT_PATTERN.search(text)
    )
    if not experience_lines and prose_experience:
        experience_lines = all_evidence_lines
        experience = "\n".join(experience_lines)
        context = bool(experience_lines)
    experience_metrics = measurable_outcomes(experience)
    breakdown["experience"] = min(15, 3 + (3 if context else 0) + len(experience_lines) * 2 + min(3, len(experience_metrics))) if experience_lines else 0

    cert_words = _words(bodies["certifications"])
    breakdown["certifications"] = min(5, 2 + len(cert_words) // 4) if len(cert_words) >= 3 else 0

    substantive = sum(breakdown[key] > 0 for key in ("summary", "education", "projects", "experience", "certifications"))
    bullets = len(re.findall(r"(?m)^\s*(?:[-•*]|\d+[.)])\s+", text))
    evidence_count = len(project_lines) + len(experience_lines)
    length_credit = 3 if 180 <= word_count <= 1000 else 2 if word_count >= 100 else 1 if word_count >= 60 else 0
    breakdown["completeness"] = min(10, length_credit + min(3, substantive) + min(2, bullets) + min(2, evidence_count))

    content_tokens = [token.casefold() for token in words if len(token) >= 2]
    lexical_diversity = len(set(content_tokens)) / len(content_tokens) if content_tokens else 0
    repeated_content = len(content_tokens) >= 50 and lexical_diversity < 0.24
    skill_density = len(skills) / max(word_count, 1)
    stuffed_content = len(skills) >= 8 and skill_density > 0.22 and evidence_count < 2
    if repeated_content or stuffed_content:
        breakdown["skills"] = round(breakdown["skills"] * 0.4)
        breakdown["completeness"] = round(breakdown["completeness"] * 0.4)
        if repeated_content:
            for key in ("summary", "education", "projects", "experience", "certifications"):
                breakdown[key] = round(breakdown[key] * 0.5)

    strengths, weaknesses, suggestions = [], [], []
    if breakdown["contact"] >= 8:
        strengths.append("The resume includes clear contact information.")
    else:
        weaknesses.append("Contact information is incomplete.")
        suggestions.append("Add a professional email, phone number, and portfolio or LinkedIn link.")
    for section, label in (("summary", "professional summary"), ("education", "education"),
                           ("projects", "project evidence"), ("experience", "work or internship evidence")):
        if breakdown[section]:
            strengths.append(f"The resume contains substantive {label}.")
        else:
            weaknesses.append(f"No substantive {label} was detected.")
            suggestions.append(f"Add {label} with specific, truthful details rather than an empty heading.")
    if len(skills) >= 8 and evidenced_skills >= 2:
        strengths.append("Several recognized technical skills are supported by project or experience evidence.")
    elif len(skills) < 4:
        weaknesses.append("Few recognized technical skills were detected.")
        suggestions.append("Add a focused technical skills section using tools you genuinely know.")
    if word_count < 100:
        weaknesses.append("The resume is very short and may lack useful detail.")
        suggestions.append("Expand relevant experience and projects with concise action-and-impact bullet points.")
    if measurable_outcomes(text):
        strengths.append("The resume includes measurable outcome signals.")
    else:
        suggestions.append("Use measurable outcomes where possible, without inventing achievements.")
    if repeated_content or stuffed_content:
        weaknesses.append("The resume contains repetitive or unsupported keywords rather than evidence.")
        suggestions.append("Connect a focused set of relevant skills to specific project or work outcomes.")
    return {"total_score": max(0, min(100, sum(breakdown.values()))), "breakdown": breakdown,
            "strengths": strengths or ["The resume contains readable content for analysis."],
            "weaknesses": weaknesses, "suggestions": list(dict.fromkeys(suggestions))}
