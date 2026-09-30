from services.job_matcher import classify_job_skills, match_job


def test_matcher_returns_exact_percentage_and_gaps():
    result = match_job(
        ["Java", "SQL", "Git"],
        "Requirements: Java, Spring Boot, SQL, Git, Docker",
    )
    assert result["keyword_score"] == 60
    assert result["final_match_score"] == result["match_percentage"]
    assert result["matched_skills"] == ["Git", "Java", "SQL"]
    assert result["missing_skills"] == ["Docker", "Spring Boot"]


def test_matcher_is_deterministic_and_bounded():
    first = match_job(["Python"], "Python Flask Docker")
    second = match_job(["Python"], "Python Flask Docker")
    assert first == second
    assert 0 <= first["match_percentage"] <= 100


def test_no_job_skills_returns_zero_not_division_error():
    result = match_job(["Python"], "We value communication and curiosity.")
    assert result["keyword_score"] == 0
    assert result["job_skills"] == []


def test_required_and_preferred_sections_are_classified_and_weighted():
    description = """Requirements
Python, SQL, Docker
Nice to have
AWS, Kubernetes
"""
    classified = classify_job_skills(description)
    assert classified["required_skills"] == ["Docker", "Python", "SQL"]
    assert classified["preferred_skills"] == ["AWS", "Kubernetes"]
    result = match_job(["Python", "SQL", "Docker"], description)
    assert result["keyword_score"] > 75


def test_one_skill_alone_cannot_produce_a_complete_match():
    result = match_job(["Python"], "Python", "Python")
    assert result["keyword_score"] == 100
    assert result["final_match_score"] == 70
    assert result["evidence_cap"] == 70
    assert "too little evidence" in result["explanation"]


def test_alias_match_and_exact_multi_skill_match():
    alias = match_job(["Kubernetes", "Scikit-learn"], "K8s and sklearn")
    exact = match_job(["Python", "Flask", "SQL"], "Python Flask SQL")
    assert alias["missing_skills"] == []
    assert exact["matched_skills"] == ["Flask", "Python", "SQL"]
    assert exact["final_match_score"] > alias["final_match_score"] - 20


def test_semantic_signal_without_catalog_skill_overlap():
    result = match_job([], "Build scalable customer-facing web services", "Developed scalable web services for customers")
    assert result["job_skills"] == []
    assert result["keyword_score"] == 0
    assert result["semantic_score"] > 0
    assert result["final_match_score"] > 0


def test_requirement_state_resets_at_unrelated_section_boundaries():
    description = """Requirements:
Python
Responsibilities:
Use Docker and AWS daily.
About the Company
We deploy Kubernetes.
"""
    classified = classify_job_skills(description)
    assert classified["required_skills"] == ["Python"]
    assert classified["preferred_skills"] == []
    assert classified["general_skills"] == ["AWS", "Docker", "Kubernetes"]


def test_required_preferred_and_general_transitions_do_not_bleed():
    description = """Required Skills
Python
Preferred
Docker
What You'll Do
Use AWS and SQL.
"""
    classified = classify_job_skills(description)
    assert classified == {
        "required_skills": ["Python"],
        "preferred_skills": ["Docker"],
        "general_skills": ["AWS", "SQL"],
    }


def test_no_heading_keeps_skills_general():
    classified = classify_job_skills("Build services with Python, Flask, and Docker.")
    assert classified["required_skills"] == []
    assert classified["preferred_skills"] == []
    assert classified["general_skills"] == ["Docker", "Flask", "Python"]


def test_required_preferred_and_general_weights_are_distinct():
    description = """Requirements
Python
Preferred
Docker
Responsibilities
Use AWS.
"""
    required = match_job(["Python"], description)["keyword_score"]
    preferred = match_job(["Docker"], description)["keyword_score"]
    general = match_job(["AWS"], description)["keyword_score"]
    assert required > general > preferred


def test_completely_unrelated_documents_have_no_match_signal():
    result = match_job([], "Python Flask Docker", "Retail accounting and inventory operations")
    assert result["matched_skills"] == []
    assert result["missing_skills"] == ["Docker", "Flask", "Python"]
    assert result["keyword_score"] == 0
    assert result["semantic_score"] == 0
    assert result["final_match_score"] == 0


def test_unknown_section_heading_resets_required_state():
    description = """Requirements:
Python

Our Culture:
AWS and Docker are part of our culture.
"""
    assert classify_job_skills(description) == {
        "required_skills": ["Python"],
        "preferred_skills": [],
        "general_skills": ["AWS", "Docker"],
    }


def test_perks_and_what_youll_do_reset_required_state():
    description = """Requirements
Python
What you'll do
Java and SQL
Perks
AWS certification support
"""
    assert classify_job_skills(description) == {
        "required_skills": ["Python"],
        "preferred_skills": [],
        "general_skills": ["AWS", "Java", "SQL"],
    }


def test_preferred_state_resets_at_generic_general_heading():
    description = """Required Skills
Python
Preferred
Docker
Team Culture
AWS and Kubernetes
"""
    assert classify_job_skills(description) == {
        "required_skills": ["Python"],
        "preferred_skills": ["Docker"],
        "general_skills": ["AWS", "Kubernetes"],
    }
