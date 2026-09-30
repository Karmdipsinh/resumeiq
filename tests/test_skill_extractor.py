import pytest

from services.skill_extractor import extract_skills, flatten_skills


def test_extracts_aliases_case_insensitively():
    skills = flatten_skills(extract_skills("Built RESTful APIs with springboot, JS, Postgres and GCP."))
    assert {"REST API", "Spring Boot", "JavaScript", "PostgreSQL", "Google Cloud"} <= set(skills)


def test_avoids_false_substring_matches():
    skills = flatten_skills(extract_skills("I drink javaScripted coffee in class."))
    assert "Java" not in skills
    assert "JavaScript" not in skills
    assert "C" not in skills


def test_returns_unique_grouped_skills():
    grouped = extract_skills("Python python PYTHON and Flask")
    assert grouped["Programming"] == ["Python"]
    assert grouped["Backend"] == ["Flask"]


def test_empty_input_returns_empty_dictionary():
    assert extract_skills("   ") == {}


@pytest.mark.parametrize(
    ("text", "unexpected"),
    [
        ("Vitamin C is important.", "C"),
        ("I go to the gym.", "Go"),
        ("We used Spring 2024 data.", "Spring"),
        ("The company reported R&D expenses.", "R"),
        ("Please express interest clearly.", "Express"),
        ("Spring water is refreshing.", "Spring"),
    ],
)
def test_ambiguous_words_need_technical_context(text, unexpected):
    assert unexpected not in flatten_skills(extract_skills(text))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("C programming", "C"),
        ("The parser was written in C.", "C"),
        ("R programming", "R"),
        ("R language", "R"),
        ("Go programming", "Go"),
        ("Developed a Go backend service.", "Go"),
        ("Built REST APIs using Spring Boot.", "Spring Boot"),
        ("Built services with the Spring Framework.", "Spring"),
        ("Built an API with Express.js.", "Express"),
    ],
)
def test_ambiguous_skills_are_kept_with_technical_evidence(text, expected):
    assert expected in flatten_skills(extract_skills(text))


def test_version_and_alias_normalization_in_realistic_bullet():
    text = "- Built a Python 3 service with HTML5, CSS3, Java 8, OOPs, K8s, sklearn, scikit learn, Node.js and AngularJS."
    found = set(flatten_skills(extract_skills(text)))
    assert {"Python", "HTML", "CSS", "Java", "OOP", "Kubernetes", "Scikit-learn", "Node.js", "AngularJS"} <= found


@pytest.mark.parametrize(
    "text",
    [
        "I go home and then go to college.",
        "We will go ahead with the plan, and finalize.",
        "Worked in R&D, improving processes.",
        "Express your ideas clearly, with confidence.",
        "Spring 2024 internship.",
        "I received a grade of C.",
    ],
)
def test_ambiguous_prose_and_punctuation_do_not_imply_skills(text):
    assert not ({"C", "R", "Go", "Express", "Spring"} & set(flatten_skills(extract_skills(text))))


def test_negated_and_aspirational_skills_are_not_owned():
    assert not ({"Docker", "Kubernetes"} & set(flatten_skills(extract_skills(
        "I have no experience with Docker or Kubernetes."
    ))))
    assert "Python" not in flatten_skills(extract_skills("I want to learn Python someday."))
    assert "Docker" in flatten_skills(extract_skills("I have experience with Docker."))


def test_node_hyphen_does_not_trigger_js_and_spring_slash_normalizes():
    found = set(flatten_skills(extract_skills("node-js, spring/boot")))
    assert found == {"Node.js", "Spring Boot"}


@pytest.mark.parametrize(
    ("text", "expected", "unexpected"),
    [
        ("I have no experience with Docker, but I have 3 years with Python and Java.", {"Python", "Java"}, {"Docker"}),
        ("I have no experience with Docker or Kubernetes.", set(), {"Docker", "Kubernetes"}),
        ("I lack experience with React and Redux.", set(), {"React", "Redux"}),
        ("I want to learn Python someday.", set(), {"Python"}),
        ("I have experience with Python, but I do not have experience with Java.", {"Python"}, {"Java"}),
    ],
)
def test_negation_and_aspiration_are_scoped_to_their_clause(text, expected, unexpected):
    found = set(flatten_skills(extract_skills(text)))
    assert expected <= found
    assert not (unexpected & found)


def test_later_explicit_denial_overrides_an_earlier_skill_claim():
    text = "Studied Go in college but have no experience with Go programming."
    assert "Go" not in flatten_skills(extract_skills(text))


@pytest.mark.parametrize(
    ("text", "expected", "unexpected"),
    [
        ("I have no experience with Docker, but I have 3 years with Python and Java.", {"Python", "Java"}, {"Docker"}),
        ("Studied Go in college but have no experience with Go programming.", set(), {"Go"}),
        (
            (
                "5 years professional experience in Python backend development.\n"
                "Skills: Python, Django, PostgreSQL.\n"
                "I have no experience with Python's asyncio internals specifically."
            ),
            {"Python", "Django", "PostgreSQL"},
            set(),
        ),
        (
            (
                "Python is my primary backend language.\n"
                "I have no experience with Python's asyncio internals."
            ),
            {"Python"},
            set(),
        ),
        (
            (
                "I have experience with Python and Java.\n"
                "I do not have experience with Docker."
            ),
            {"Python", "Java"},
            {"Docker"},
        ),
        (
            (
                "I want to learn Rust.\n"
                "I have 4 years of experience with Java."
            ),
            {"Java"},
            {"Rust"},
        ),
        (
            (
                "I have no experience with React.\n"
                "I have built multiple production applications using React."
            ),
            {"React"},
            set(),
        ),
    ],
)
def test_skill_assertion_is_combined_across_sentence_occurrences(text, expected, unexpected):
    found = set(flatten_skills(extract_skills(text)))
    assert expected <= found
    assert not (unexpected & found)


@pytest.mark.parametrize(
    ("text", "expected", "unexpected"),
    [
        (
            "I have no experience with Kubernetes, but I do have hands-on experience with Kubernetes from personal projects.",
            {"Kubernetes"},
            set(),
        ),
        (
            "I have no experience with AWS Lambda, though I have used AWS extensively for EC2 and S3 in production.",
            {"AWS"},
            set(),
        ),
        (
            "I studied Kubernetes, but I have no professional experience with Kubernetes.",
            set(),
            {"Kubernetes"},
        ),
        (
            "I have no professional experience with AWS, but I have built and deployed applications using AWS.",
            {"AWS"},
            set(),
        ),
        (
            "I have no experience with Docker, and I have no experience with Docker in production.",
            set(),
            {"Docker"},
        ),
    ],
)
def test_same_sentence_contrast_uses_ordered_occurrence_statuses(text, expected, unexpected):
    found = set(flatten_skills(extract_skills(text)))
    assert expected <= found
    assert not (unexpected & found)


@pytest.mark.parametrize(
    ("text", "expected", "unexpected"),
    [
        ("Skills: Python, Java, and I will go now", {"Python", "Java"}, {"Go"}),
        ("My hobbies: React, Vue, R&B music", {"React", "Vue"}, {"R"}),
        ("Skills: Python, Java, Go, Docker, Kubernetes", {"Python", "Java", "Go", "Docker", "Kubernetes"}, set()),
        ("Experienced in C, C++, C#, Java", {"C", "C++", "C#", "Java"}, set()),
        ("Worked in R&D, improving processes", set(), {"R"}),
        ("Developed statistical models using R programming", {"R"}, set()),
    ],
)
def test_ambiguous_skills_require_structural_or_explicit_technical_evidence(text, expected, unexpected):
    found = set(flatten_skills(extract_skills(text)))
    assert expected <= found
    assert not (unexpected & found)
