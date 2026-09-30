"""Lightweight, deterministic TF-IDF and cosine-similarity matching."""

import math
import re
from collections import Counter
from hashlib import sha256

from config import MAX_SEMANTIC_TEXT_CHARS

TOKEN_PATTERN = re.compile(r"(?u)\b[a-zA-Z][a-zA-Z0-9+#.]{1,}\b")


def normalize_text(text: str | None) -> str:
    """Normalize user text without inventing or expanding its meaning."""
    return " ".join(TOKEN_PATTERN.findall((text or "")[:MAX_SEMANTIC_TEXT_CHARS].casefold()))


def semantic_profile(text: str | None) -> dict[str, int]:
    """Build a deterministic, one-way token-frequency profile for persistence."""
    tokens = TOKEN_PATTERN.findall((text or "")[:MAX_SEMANTIC_TEXT_CHARS].casefold())
    return dict(Counter(sha256(token.encode("utf-8")).hexdigest() for token in tokens))


def _tfidf_vectors(counters: list[Counter]) -> list[dict[str, float]]:
    document_frequency = Counter(term for counts in counters for term in counts)
    if not document_frequency:
        return [{} for _ in counters]
    vectors = []
    document_count = len(counters)
    for counts in counters:
        total = sum(counts.values()) or 1
        vector = {
            term: (count / total) * (math.log((1 + document_count) / (1 + document_frequency[term])) + 1)
            for term, count in counts.items()
        }
        vectors.append(vector)
    return vectors


def _profile_counter(value: str | dict[str, int] | None) -> Counter:
    if isinstance(value, dict):
        return Counter({str(term): int(count) for term, count in value.items() if int(count) > 0})
    return Counter(semantic_profile(value))


def semantic_similarity(resume_text: str | dict[str, int] | None, job_description: str | None) -> dict:
    """Return an actual cosine score for two locally computed TF-IDF vectors."""
    resume = _profile_counter(resume_text)
    job = _profile_counter(job_description)
    if not resume or not job:
        return {"semantic_similarity": 0.0, "semantic_score": 0, "method": "tfidf_cosine_similarity"}
    left, right = _tfidf_vectors([resume, job])
    terms = set(left) | set(right)
    dot_product = sum(left.get(term, 0.0) * right.get(term, 0.0) for term in terms)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    similarity = dot_product / (left_norm * right_norm) if left_norm and right_norm else 0.0
    similarity = max(0.0, min(1.0, similarity))
    return {"semantic_similarity": round(similarity, 4), "semantic_score": round(similarity * 100), "method": "tfidf_cosine_similarity"}
