"""Run the small synthetic skill-extraction evaluation set."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.job_matcher import match_job
from services.skill_extractor import extract_skills, flatten_skills


def evaluate() -> dict:
    cases = json.loads((ROOT / "eval" / "skill_extraction_cases.json").read_text(encoding="utf-8"))
    true_positive = false_positive = false_negative = 0
    for case in cases:
        actual = set(flatten_skills(extract_skills(case["text"])))
        expected = set(case["expected"])
        true_positive += len(actual & expected)
        false_positive += len(actual - expected)
        false_negative += len(expected - actual)
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"cases": len(cases), "true_positives": true_positive, "false_positives": false_positive,
            "false_negatives": false_negative, "precision": precision, "recall": recall, "f1": f1}


def evaluate_matching() -> list[dict]:
    """Return components for synthetic regression cases without claiming an accuracy metric."""
    cases = json.loads((ROOT / "eval" / "matching_cases.json").read_text(encoding="utf-8"))
    results = []
    for case in cases:
        result = match_job(case["resume_skills"], case["job_description"], case["resume_text"])
        results.append({
            "id": case["id"],
            "expect": case["expect"],
            "keyword_score": result["keyword_score"],
            "semantic_score": result["semantic_score"],
            "combined_score": result["final_match_score"],
        })
    return results


if __name__ == "__main__":
    print(json.dumps({"skill_extraction": evaluate(), "matching_regressions": evaluate_matching()}, indent=2))
    print("Note: these are small synthetic regression datasets, not evidence of real-world accuracy.")
