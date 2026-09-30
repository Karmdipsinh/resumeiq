from time import perf_counter

from services.semantic_matcher import semantic_similarity


def test_semantic_similarity_is_calculated_and_bounded():
    close = semantic_similarity("Python Flask REST API", "Python developer building Flask APIs")
    unrelated = semantic_similarity("Python Flask REST API", "retail accounting operations")
    assert close["semantic_score"] > unrelated["semantic_score"]
    assert close["method"] == "tfidf_cosine_similarity"
    assert 0 <= close["semantic_similarity"] <= 1


def test_semantic_similarity_handles_edge_cases():
    for left, right in (("", "Python"), ("a", "b"), ("Python " * 100, "Python"), ("!!!", "...")):
        result = semantic_similarity(left, right)
        assert 0 <= result["semantic_score"] <= 100


def test_large_input_is_bounded_and_fast_enough_for_regression_suite():
    text = "Python Flask scalable API delivery " * 20_000
    started = perf_counter()
    result = semantic_similarity(text, text)
    elapsed = perf_counter() - started
    assert result["semantic_score"] == 100
    assert elapsed < 2.0
