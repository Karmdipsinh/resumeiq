# Evaluation fixtures

`skill_extraction_cases.json` contains synthetic, narrowly scoped positive and negative cases used to calculate precision, recall, and F1. It covers aliases/version suffixes, ordinary uses of C/R/Go/Express/Spring, structural technical lists, R&B and prose-list traps, clause-scoped negation, aspirational skills, and the `node-js` boundary regression. `matching_cases.json` records keyword-only, TF-IDF, and combined scores for positive, negative, alias, semantic-only, and sparse-evidence scenarios.

These are deterministic regression fixtures, not a representative resume corpus. Matching accuracy is intentionally not calculated, and skill precision/recall/F1 only describe this small labeled fixture set. They are not evidence of real-world hiring, recruiter, or ATS performance.
