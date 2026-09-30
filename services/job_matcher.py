"""Explainable keyword, requirement-level, and semantic job matching."""

import re

from config import (
    GENERAL_SKILL_WEIGHT,
    KEYWORD_WEIGHT,
    PREFERRED_SKILL_WEIGHT,
    REQUIRED_SKILL_WEIGHT,
    SEMANTIC_WEIGHT,
)
from services.semantic_matcher import semantic_similarity
from services.skill_extractor import extract_skills, flatten_skills

REQUIRED_MARKER = re.compile(r"(?i)\b(?:required|requirements|must[ -]?have|required skills?|essential)\b")
PREFERRED_MARKER = re.compile(r"(?i)\b(?:preferred|nice[ -]?to[ -]?have|bonus|a plus|plus)\b")
GENERAL_MARKER = re.compile(
    r"(?i)^\s*(?:responsibilities|what\s+you(?:['’])?ll\s+do|about(?:\s+the\s+(?:company|role))?|"
    r"description|benefits|perks|duties|role|who\s+we\s+are)\b"
)


def _likely_section_heading(line: str) -> bool:
    """Recognize short standalone headings without maintaining an exhaustive whitelist."""
    stripped = line.strip()
    if not stripped or re.search(r"[.!?]$", stripped):
        return False
    label = stripped.split(":", 1)[0].strip()
    words = re.findall(r"[A-Za-z][A-Za-z'’&-]*", label)
    if not 1 <= len(words) <= 6:
        return False
    if ":" not in stripped and flatten_skills(extract_skills(stripped)):
        return False
    title_like = label.isupper() or all(
        word[:1].isupper() for word in words if word.casefold() not in {"and", "or", "the"}
    )
    return stripped.endswith(":") or (":" in stripped and title_like) or (stripped == label and title_like)


def classify_job_skills(job_description: str) -> dict[str, list[str]]:
    """Classify skills with transparent section/phrase heuristics."""
    all_skills = flatten_skills(extract_skills(job_description))
    buckets = {"required_skills": [], "preferred_skills": [], "general_skills": []}
    state = "general_skills"
    for line in job_description.splitlines():
        required = bool(REQUIRED_MARKER.search(line))
        preferred = bool(PREFERRED_MARKER.search(line))
        if required and not preferred:
            state = "required_skills"
        elif preferred:
            state = "preferred_skills"
        elif GENERAL_MARKER.match(line) or _likely_section_heading(line):
            state = "general_skills"
        for skill in flatten_skills(extract_skills(line)):
            target = "preferred_skills" if preferred else "required_skills" if required else state
            if skill not in buckets[target]:
                buckets[target].append(skill)
    classified = {skill for skills in buckets.values() for skill in skills}
    buckets["general_skills"].extend(skill for skill in all_skills if skill not in classified)
    for key, values in buckets.items():
        buckets[key] = sorted(set(values), key=str.casefold)
    return buckets


def _keyword_score(resume_set: set[str], classified: dict[str, list[str]]) -> int:
    weights = {"required_skills": REQUIRED_SKILL_WEIGHT, "preferred_skills": PREFERRED_SKILL_WEIGHT,
               "general_skills": GENERAL_SKILL_WEIGHT}
    available = sum(len(classified[key]) * weight for key, weight in weights.items())
    earned = sum(weight for key, weight in weights.items() for skill in classified[key]
                 if skill.casefold() in resume_set)
    return round(earned / available * 100) if available else 0


def match_job(resume_skills, job_description: str | None, resume_text: str | dict | None = None) -> dict:
    """Combine a weighted keyword baseline with local TF-IDF cosine similarity."""
    description = job_description.strip() if isinstance(job_description, str) else ""
    resume_list = flatten_skills(resume_skills)
    resume_set = {skill.casefold() for skill in resume_list}
    classified = classify_job_skills(description)
    job_skills = sorted({skill for skills in classified.values() for skill in skills}, key=str.casefold)
    matched = [skill for skill in job_skills if skill.casefold() in resume_set]
    missing = [skill for skill in job_skills if skill.casefold() not in resume_set]
    keyword_score = _keyword_score(resume_set, classified)
    semantic = semantic_similarity(resume_text or " ".join(resume_list), description)
    final_score = round(keyword_score * KEYWORD_WEIGHT + semantic["semantic_score"] * SEMANTIC_WEIGHT)
    evidence_cap = 70 if len(job_skills) == 1 else 100
    final_score = min(final_score, evidence_cap)
    if not description:
        explanation = "Enter a job description to calculate compatibility."
    elif not job_skills:
        explanation = "No catalog skills were recognized; the semantic score still compares the wording."
    else:
        explanation = (f"{len(matched)} of {len(job_skills)} recognized skills match. Final score = "
                       f"{round(KEYWORD_WEIGHT * 100)}% keyword + {round(SEMANTIC_WEIGHT * 100)}% semantic.")
        if len(job_skills) == 1:
            explanation += " A 70% evidence cap applies because one recognized skill is too little evidence for a complete match."
    return {
        "final_match_score": max(0, min(100, final_score)),
        "match_percentage": max(0, min(100, final_score)),
        "keyword_score": keyword_score,
        **semantic,
        "matched_skills": matched,
        "missing_skills": missing,
        "job_skills": job_skills,
        **classified,
        "recommendations": [f"Develop and demonstrate {skill} if it is relevant to your goals." for skill in missing[:5]],
        "explanation": explanation,
        "weights": {"keyword": KEYWORD_WEIGHT, "semantic": SEMANTIC_WEIGHT},
        "evidence_cap": evidence_cap,
    }
