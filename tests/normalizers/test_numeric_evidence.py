"""Iter10 RED: numeric evidence policy unit tests.

Covers ITER10_STARS_NUMERIC_SEMANTICS_SPEC §7.1.

Targets the deterministic SSoT helper `_normalize_star_bounds(min_stars,
max_stars, user_query)` used by `validate_query` to recompute `min_stars` /
`max_stars` from explicit `user_query` evidence (§3 query-driven rewrite).
"""
from __future__ import annotations

import pytest

from gh_search.tools.validate_query import _normalize_star_bounds


# ---------------------------------------------------------------------------
# §7.1 (group 1): exclusive lower bound
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_query,expected_min",
    [
        ("over 500 stars", 501),
        ("more than 2k stars", 2001),
        ("超過 500 star", 501),
        ("repos with > 1000 stars", 1001),
    ],
)
def test_exclusive_lower_bound(user_query: str, expected_min: int) -> None:
    assert _normalize_star_bounds(None, None, user_query) == (expected_min, None)


# ---------------------------------------------------------------------------
# §7.1 (group 2): exclusive upper bound
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_query,expected_max",
    [
        ("under 10k stars", 9999),
        ("less than 100 stars", 99),
        ("少於 100 stars", 99),
        ("repos with < 1000 stars", 999),
    ],
)
def test_exclusive_upper_bound(user_query: str, expected_max: int) -> None:
    assert _normalize_star_bounds(None, None, user_query) == (None, expected_max)


# ---------------------------------------------------------------------------
# §7.1 (group 3): inclusive lower bound
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_query,expected_min",
    [
        ("min 500 starz", 500),
        ("at least 1000 stars", 1000),
        ("repos with >= 250 stars", 250),
        ("minimum 50 stars please", 50),
    ],
)
def test_inclusive_lower_bound(user_query: str, expected_min: int) -> None:
    assert _normalize_star_bounds(None, None, user_query) == (expected_min, None)


# ---------------------------------------------------------------------------
# §7.1 (group 4): inclusive upper bound
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_query,expected_max",
    [
        ("max 500 stars", 500),
        ("at most 100 stars", 100),
        ("repos with <= 250 stars", 250),
        ("maximum 50 stars", 50),
    ],
)
def test_inclusive_upper_bound(user_query: str, expected_max: int) -> None:
    assert _normalize_star_bounds(None, None, user_query) == (None, expected_max)


# ---------------------------------------------------------------------------
# §7.1 (group 5): vague popularity must NOT create numeric filters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_query,incoming_min,incoming_max",
    [
        ("popular stuff on github", 100, None),
        ("ui kit with lots of stars", 1, None),
        ("trending rust stuff", 500, None),
        ("high-star repos", None, 9999),
    ],
)
def test_vague_popularity_clears_numeric(
    user_query: str, incoming_min: int | None, incoming_max: int | None
) -> None:
    assert _normalize_star_bounds(incoming_min, incoming_max, user_query) == (None, None)


# ---------------------------------------------------------------------------
# §7.1 (group 6): stars-context anchoring (must not grab limit / year numbers)
# ---------------------------------------------------------------------------


def test_anchoring_ignores_limit_keeps_stars_threshold() -> None:
    user_query = (
        "find me 20 popular TypeScript ORM libraries with more than 2k stars"
    )
    # Parser hallucinated min_stars=20 from the limit token.
    assert _normalize_star_bounds(20, None, user_query) == (2001, None)


def test_anchoring_idempotent_when_incoming_is_correct() -> None:
    user_query = (
        "find me 20 popular TypeScript ORM libraries with more than 2k stars"
    )
    assert _normalize_star_bounds(2001, None, user_query) == (2001, None)


def test_anchoring_does_not_grab_year_number() -> None:
    user_query = "list 15 java spring boot starter projects from 2024 ranked by stars"
    # 'ranked by stars' is a sort signal, not numeric; '2024' is a year.
    assert _normalize_star_bounds(None, None, user_query) == (None, None)


# ---------------------------------------------------------------------------
# §7.1 (group 7): contradictory range MUST be preserved (no swap, no widen)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "incoming_min,incoming_max",
    [
        (100, 500),  # parser swapped to "reasonable"
        (99, 501),  # parser also reversed exclusivity
        (None, None),  # parser dropped both; query-driven rewrite must add
        (501, 99),  # already correct
    ],
)
def test_contradictory_range_preserved(
    incoming_min: int | None, incoming_max: int | None
) -> None:
    user_query = "找一些 star 超過 500 但少於 100 的 rust 專案"
    assert _normalize_star_bounds(incoming_min, incoming_max, user_query) == (501, 99)


# ---------------------------------------------------------------------------
# §7.1 (group 8): idempotence — correct values pass through unchanged
# ---------------------------------------------------------------------------


def test_idempotent_exclusive_range() -> None:
    user_query = "trending rust projects from last year with over 500 stars but under 10k"
    assert _normalize_star_bounds(501, 9999, user_query) == (501, 9999)


def test_idempotent_inclusive_lower_only() -> None:
    user_query = "find me 20 popular TypeScript ORM libraries with more than 2k stars"
    assert _normalize_star_bounds(2001, None, user_query) == (2001, None)


def test_idempotent_inclusive_lower_at_least() -> None:
    user_query = "python scraping libraries created after 2023 with at least 1000 stars"
    assert _normalize_star_bounds(1000, None, user_query) == (1000, None)


def test_idempotent_cjk_exclusive_lower() -> None:
    user_query = "幫我找一下熱門的 python 爬蟲套件，star 數超過 1000 的"
    assert _normalize_star_bounds(1001, None, user_query) == (1001, None)


def test_idempotent_inclusive_min_dataset_typo() -> None:
    user_query = "javscript chatbot libs with min 500 starz plz"
    assert _normalize_star_bounds(500, None, user_query) == (500, None)


def test_idempotent_exclusive_upper_dataset() -> None:
    user_query = "small python utilities under 100 stars created this year"
    assert _normalize_star_bounds(None, 99, user_query) == (None, 99)


# ---------------------------------------------------------------------------
# §3 query-driven rewrite: parser dropped value, query has evidence → add
# ---------------------------------------------------------------------------


def test_query_driven_rewrite_adds_when_parser_dropped_lower() -> None:
    # Parser may emit None; query has explicit comparator → must add.
    assert _normalize_star_bounds(None, None, "over 500 stars") == (501, None)


def test_query_driven_rewrite_adds_when_parser_dropped_upper() -> None:
    assert _normalize_star_bounds(None, None, "under 100 stars") == (None, 99)


def test_query_driven_rewrite_overrides_wrong_parser_value() -> None:
    # Parser said 500 (inclusive interpretation); query is exclusive → 501.
    assert _normalize_star_bounds(500, None, "over 500 stars") == (501, None)


# ---------------------------------------------------------------------------
# §3.1: query has no numeric evidence → clear any incoming value
# ---------------------------------------------------------------------------


def test_no_numeric_evidence_clears_incoming() -> None:
    # No comparator + number anywhere; "rect native ui kit ... lots of stars"
    user_query = "rect native ui kit     with    lots     of stars"
    assert _normalize_star_bounds(1, None, user_query) == (None, None)


def test_empty_query_clears_incoming() -> None:
    assert _normalize_star_bounds(100, 200, "") == (None, None)


# ---------------------------------------------------------------------------
# §3.3: range logical consistency NOT checked — even if min > max, keep both
# ---------------------------------------------------------------------------


def test_logical_inconsistency_not_auto_corrected() -> None:
    # Spec §3.3 末段：iter10 不檢查 numeric range 的可解性。
    user_query = "找一些 star 超過 500 但少於 100 的 rust 專案"
    out = _normalize_star_bounds(None, None, user_query)
    assert out == (501, 99)
    assert out[0] > out[1]  # noqa: confirms preserved inconsistency
