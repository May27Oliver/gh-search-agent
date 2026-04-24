"""Task 3.3 RED: GitHub query compiler (TOOLS.md §8).

Contract: pure function StructuredQuery -> str (the GitHub Search `q` parameter).
Per SCHEMAS.md, compiled_query is a string; sort/order/limit are read by the client
separately from the structured query.
"""
from __future__ import annotations

import pytest

from gh_search.compiler import compile_github_query
from gh_search.schemas import StructuredQuery


def _sq(**overrides) -> StructuredQuery:
    base = {
        "keywords": [],
        "language": None,
        "created_after": None,
        "created_before": None,
        "min_stars": None,
        "max_stars": None,
        "sort": None,
        "order": None,
        "limit": 10,
    }
    base.update(overrides)
    return StructuredQuery.model_validate(base)


def test_keywords_joined_with_space():
    q = compile_github_query(_sq(keywords=["logistics", "optimization"]))
    assert q == "logistics optimization"


def test_single_keyword():
    assert compile_github_query(_sq(keywords=["chatgpt"])) == "chatgpt"


def test_language_mapped_as_qualifier():
    q = compile_github_query(_sq(keywords=["foo"], language="Python"))
    assert "language:Python" in q
    assert q.startswith("foo ")


def test_created_after_uses_gte():
    q = compile_github_query(_sq(keywords=["x"], created_after="2024-01-01"))
    assert "created:>=2024-01-01" in q


def test_created_before_uses_lte():
    q = compile_github_query(_sq(keywords=["x"], created_before="2024-12-31"))
    assert "created:<=2024-12-31" in q


def test_created_after_and_before_both_present():
    q = compile_github_query(
        _sq(keywords=["x"], created_after="2024-01-01", created_before="2024-12-31")
    )
    assert "created:>=2024-01-01" in q
    assert "created:<=2024-12-31" in q


def test_min_stars_uses_gte():
    q = compile_github_query(_sq(keywords=["x"], min_stars=100))
    assert "stars:>=100" in q


def test_max_stars_uses_lte():
    q = compile_github_query(_sq(keywords=["x"], max_stars=500))
    assert "stars:<=500" in q


def test_min_and_max_stars_both_present():
    q = compile_github_query(_sq(keywords=["x"], min_stars=10, max_stars=500))
    assert "stars:>=10" in q
    assert "stars:<=500" in q


def test_sort_and_order_do_not_appear_in_q_string():
    # sort and order are HTTP params, not q qualifiers.
    q = compile_github_query(_sq(keywords=["x"], sort="stars", order="desc"))
    assert "sort" not in q
    assert "order" not in q


def test_limit_does_not_appear_in_q_string():
    q = compile_github_query(_sq(keywords=["x"], limit=20))
    assert "20" not in q or "limit" not in q  # limit never leaks into q


def test_all_fields_combined_deterministic_order():
    q = compile_github_query(
        _sq(
            keywords=["logistics"],
            language="Python",
            created_after="2024-01-01",
            created_before="2024-12-31",
            min_stars=100,
            max_stars=500,
        )
    )
    assert q == (
        "logistics language:Python "
        "created:>=2024-01-01 created:<=2024-12-31 "
        "stars:>=100 stars:<=500"
    )


def test_no_keywords_only_qualifiers():
    # Minimal valid case where parser found a language but no free-text keywords.
    q = compile_github_query(_sq(language="Go"))
    assert q == "language:Go"


def test_multi_word_keywords_joined_verbatim():
    # Spec §8 says "以空白 join". No quoting logic in phase 1.
    q = compile_github_query(_sq(keywords=["machine learning", "agents"]))
    assert q == "machine learning agents"


def test_return_type_is_str():
    assert isinstance(compile_github_query(_sq(keywords=["x"])), str)
