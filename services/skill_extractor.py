"""Catalog-driven technical skill extraction with ambiguity and intent safeguards."""

import json
import re
from functools import lru_cache
from pathlib import Path

SKILLS_PATH = Path(__file__).resolve().parents[1] / "data" / "skills.json"
CONTEXT_HEADING = re.compile(r"(?i)\b(?:skills?|technologies|tech stack|tools?|languages?|competencies)\b")
TECHNICAL_PREFIX = (
    r"(?:using|used|with|written\s+in|built\s+in|coded\s+in|experience\s+with|experienced\s+in|"
    r"proficient\s+in|knowledge\s+of)"
)
TECHNICAL_SUFFIX = {
    "C": r"(?:programming|language|code|development|developer)",
    "R": r"(?:programming|language|code|analysis|statistical|development|developer)",
    "Go": r"(?:programming|language|code|backend|development|developer|service|api)",
    "Express": r"(?:framework|middleware|server|backend|api|development)",
    "Spring": r"(?:framework|boot|mvc|data|security|cloud|batch|backend|api|development)",
}


@lru_cache(maxsize=1)
def load_skill_catalog() -> dict:
    """Load categories, aliases, and ambiguous terms from JSON."""
    with SKILLS_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if "categories" in data else {"categories": data, "aliases": {}, "ambiguous": []}


def _pattern(term: str) -> re.Pattern:
    escaped = re.escape(term).replace(r"\ ", r"[\s\-/]*")
    left = r"(?<![A-Za-z0-9+#./-])" if term.casefold() == "js" else r"(?<![A-Za-z0-9+#])"
    return re.compile(rf"{left}{escaped}(?![A-Za-z0-9+#])", re.IGNORECASE)


def _candidate_clause(line: str, match: re.Match) -> tuple[str, int]:
    """Return the grammatical clause containing a candidate and its local offset."""
    boundaries = list(re.finditer(r"(?i)[,;.!?]|\b(?:but|though|however|although|yet)\b", line))
    start = max((boundary.end() for boundary in boundaries if boundary.end() <= match.start()), default=0)
    end = min((boundary.start() for boundary in boundaries if boundary.start() >= match.end()), default=len(line))
    return line[start:end], match.start() - start


def _occurrence_status(candidate: str, line: str, match: re.Match) -> str:
    """Classify one candidate occurrence using only its local clause."""
    clause, local_start = _candidate_clause(line, match)
    before = clause[:local_start]
    escaped = re.escape(candidate)
    experience = r"(?:(?:prior|professional)\s+)*experience"
    if (
        re.search(rf"(?i)\b(?:no|without)\s+{experience}\s+(?:with|in|using)\b.*$", before)
        or re.search(rf"(?i)\b(?:lack|lacks|lacking)\s+{experience}\s+(?:with|in|using)\b.*$", before)
        or re.search(rf"(?i)\b(?:do|does|did)\s+not\s+have\s+{experience}\s+(?:with|in|using)\b.*$", before)
        or re.search(rf"(?i)\b(?:not|never)\s+(?:used|worked\s+with|experienced\s+in)\s+.*{escaped}", clause)
    ):
        return "denied"
    if re.search(r"(?i)\b(?:want|wants|wanted|wish|hope|plan|planning)\s+to\s+(?:learn|study)\b.*$", before):
        return "aspirational"
    if re.search(r"(?i)\b(?:studied|learned|coursework\s+in)\b.*$", before):
        return "educational"
    return "asserted"


def _denied_or_aspirational(candidate: str, line: str, match: re.Match) -> bool:
    """Recognize explicit non-possession phrases within the candidate's clause."""
    return _occurrence_status(candidate, line, match) in {"denied", "aspirational"}


def _has_asserted_occurrence(candidate: str, text: str) -> bool:
    sentence_units = re.split(r"(?:\r?\n)+|(?<=[.!?])\s+", text)
    for sentence in sentence_units:
        asserted = None
        for match in _pattern(candidate).finditer(sentence):
            status = _occurrence_status(candidate, sentence, match)
            if status == "asserted":
                asserted = True
            elif status == "denied":
                asserted = False
            elif status == "educational" and asserted is None:
                asserted = True
            elif status == "aspirational" and asserted is None:
                asserted = False
        if asserted:
            return True
    return False


def _ambiguous_in_context(term: str, candidate: str, text: str, technical_terms: list[str]) -> bool:
    """Require explicit technical evidence for words that are common in prose."""
    if candidate.casefold() in {"express.js", "expressjs", "spring framework"}:
        return _has_asserted_occurrence(candidate, text)
    lines = text.splitlines()
    for index, line in enumerate(lines):
        matches = list(_pattern(candidate).finditer(line))
        if not matches or all(_denied_or_aspirational(candidate, line, match) for match in matches):
            continue
        if term == "Spring" and re.search(r"(?i)\bSpring\s+(?:19|20)\d{2}\b", line):
            continue
        stripped = line.strip()
        prior = lines[index - 1].strip().rstrip(":") if index else ""
        heading_context = bool(CONTEXT_HEADING.search(stripped) or CONTEXT_HEADING.fullmatch(prior))
        technical_phrase = bool(re.search(
            rf"(?i)(?:\b{TECHNICAL_PREFIX}\b.{{0,30}}{re.escape(candidate)}(?![A-Za-z0-9+#])|"
            rf"(?<![A-Za-z0-9+#]){re.escape(candidate)}.{{0,30}}\b{TECHNICAL_SUFFIX[term]}\b)",
            stripped,
        ))
        list_items = re.split(r"[,|;]", stripped.split(":", 1)[-1])
        listed_skill = any(
            re.fullmatch(rf"(?i)\s*(?:and|or)?\s*{re.escape(candidate)}\s*", item)
            for item in list_items
        )
        technical_list = listed_skill and (
            heading_context
            or len(list_items) >= 3
            or sum(bool(_pattern(known).search(stripped)) for known in technical_terms) >= 2
        )
        if technical_phrase or technical_list:
            return True
    return False


def extract_skills(text: str | None) -> dict[str, list[str]]:
    """Extract canonical, categorized skills from asserted technical context."""
    if not isinstance(text, str) or not text.strip():
        return {}
    config = load_skill_catalog()
    categories = config["categories"]
    aliases = config.get("aliases", {})
    ambiguous = set(config.get("ambiguous", []))
    canonical_category = {skill.casefold(): category for category, skills in categories.items() for skill in skills}
    technical_terms = [skill for skills in categories.values() for skill in skills if skill not in ambiguous]
    found: set[str] = set()
    candidates = [(skill, skill) for skills in categories.values() for skill in skills] + list(aliases.items())
    for term, canonical in sorted(candidates, key=lambda item: len(item[0]), reverse=True):
        if canonical in ambiguous and not _ambiguous_in_context(canonical, term, text, technical_terms):
            continue
        if _has_asserted_occurrence(term, text):
            found.add(canonical)

    suppressions = (
        ("Spring Boot", "Spring", r"\bSpring\b(?![\s/-]*Boot)"),
        ("JavaScript", "Java", r"\bJava\b(?!\s*Script)"),
        ("C++", "C", r"(?<![A-Za-z0-9+#])C(?![A-Za-z0-9+#])"),
        ("C#", "C", r"(?<![A-Za-z0-9+#])C(?![A-Za-z0-9+#])"),
    )
    for specific, parent, independent_pattern in suppressions:
        if specific in found and not re.search(independent_pattern, text, re.IGNORECASE):
            found.discard(parent)

    grouped: dict[str, list[str]] = {}
    for skill in sorted(found, key=str.casefold):
        grouped.setdefault(canonical_category.get(skill.casefold(), "Other"), []).append(skill)
    return grouped


def flatten_skills(grouped) -> list[str]:
    """Return a sorted unique skill list from grouped or flat input."""
    if isinstance(grouped, list):
        return sorted(set(grouped), key=str.casefold)
    return sorted({skill for skills in (grouped or {}).values() for skill in skills}, key=str.casefold)
