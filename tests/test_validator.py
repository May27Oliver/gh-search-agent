"""Task 3.6 RED: semantic validator (TOOLS.md §9).

Pure domain service. Schema-level validation (types/enums/required) is already
enforced by StructuredQuery's pydantic model; this checks the remaining
semantic rules:
  - created_after <= created_before
  - min_stars <= max_stars
  - at least one effective search condition
"""
from __future__ import annotations

from gh_search.schemas import StructuredQuery, Validation
from gh_search.validator import validate_structured_query


def _sq(**overrides):
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


def test_keywords_only_is_valid():
    result = validate_structured_query(_sq(keywords=["logistics"]))
    assert isinstance(result, Validation)
    assert result.is_valid is True
    assert result.errors == []


def test_language_only_is_valid():
    result = validate_structured_query(_sq(language="Go"))
    assert result.is_valid is True


def test_empty_query_rejected():
    result = validate_structured_query(_sq())
    assert result.is_valid is False
    assert any(e.code == "no_effective_condition" for e in result.errors)


def test_min_greater_than_max_stars_rejected():
    result = validate_structured_query(_sq(keywords=["x"], min_stars=500, max_stars=100))
    assert result.is_valid is False
    assert any(e.code == "min_gt_max_stars" for e in result.errors)


def test_created_after_greater_than_before_rejected():
    result = validate_structured_query(
        _sq(keywords=["x"], created_after="2024-06-01", created_before="2024-01-01")
    )
    assert result.is_valid is False
    assert any(e.code == "created_after_gt_before" for e in result.errors)


def test_equal_boundaries_accepted():
    result = validate_structured_query(
        _sq(
            keywords=["x"],
            min_stars=100,
            max_stars=100,
            created_after="2024-01-01",
            created_before="2024-01-01",
        )
    )
    assert result.is_valid is True


def test_multiple_errors_all_reported():
    result = validate_structured_query(
        _sq(min_stars=500, max_stars=100, created_after="2024-06-01", created_before="2024-01-01")
    )
    assert result.is_valid is False
    # min>max + after>before → 2 distinct semantic errors (query is not empty)
    assert len(result.errors) == 2


def test_result_missing_required_fields_stable_shape():
    # Field is reserved for future use; must exist and be a list.
    result = validate_structured_query(_sq(keywords=["x"]))
    assert result.missing_required_fields == []
