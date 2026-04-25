"""Iter11 RED: ranking intent policy unit tests.

Covers ITER11_SORT_DEFAULTS_SPEC §7.1.

Targets the deterministic SSoT helper
`_normalize_ranking(sort, order, user_query)` used by `validate_query`
to fill in `sort=stars`, `order=desc` when `user_query` carries a
dataset-backed ranking intent (§3 query-driven rewrite).

Policy summary (spec §3.1, §3.3):
  - ranking intent present + sort is None → fill (stars, desc)
  - ranking intent present + sort already stars → keep (idempotent)
  - ranking intent present + sort is non-stars (e.g. updated) → KEEP, do not overwrite
  - ranking intent absent + sort is None → stay None (don't invent)
  - ranking intent absent + sort already set → KEEP (don't clear)
"""
from __future__ import annotations

import pytest

from gh_search.schemas import OrderDir, SortField
from gh_search.tools.validate_query import _normalize_ranking


# ---------------------------------------------------------------------------
# §7.1 (group 1): stars ranking intent → (stars, desc)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_query",
    [
        "popular TypeScript ORM libraries",
        "trending rust projects",
        "repos ranked by stars",
        "sorted by stars please",
        "ui kit with lots of stars",
        "repos with most stars",
        "gimme top10 go repoz created aftr 2022!!!",
        "give me top 10 react libraries",
        "按 star 排序",
        "按star排序",
        "按 stars 排序",
        "按stars排序",
        "熱門的 python 爬蟲套件",
    ],
)
def test_stars_ranking_intent_fills_stars_desc(user_query: str) -> None:
    assert _normalize_ranking(None, None, user_query) == (
        SortField.STARS,
        OrderDir.DESC,
    )


# ---------------------------------------------------------------------------
# §7.1 (group 2): no ranking intent → don't invent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_query",
    [
        "vue 3 admin dashboard templates",
        "java spring boot starter projects from 2024",
        "python scraping libraries created after 2023",
        "small python utilities created this year",
    ],
)
def test_no_ranking_intent_stays_none(user_query: str) -> None:
    assert _normalize_ranking(None, None, user_query) == (None, None)


# ---------------------------------------------------------------------------
# §7.1 (group 3): don't clear existing sort/order (no ranking intent)
# ---------------------------------------------------------------------------


def test_no_ranking_intent_preserves_incoming_updated() -> None:
    user_query = "vue 3 admin dashboard templates"
    assert _normalize_ranking(SortField.UPDATED, OrderDir.DESC, user_query) == (
        SortField.UPDATED,
        OrderDir.DESC,
    )


def test_no_ranking_intent_preserves_incoming_forks_asc() -> None:
    user_query = "react chart libs"
    assert _normalize_ranking(SortField.FORKS, OrderDir.ASC, user_query) == (
        SortField.FORKS,
        OrderDir.ASC,
    )


# ---------------------------------------------------------------------------
# §7.1 (group 4): idempotence — already stars desc + ranking query
# ---------------------------------------------------------------------------


def test_idempotent_stars_desc_with_ranking_query() -> None:
    user_query = "popular TypeScript ORM libraries"
    assert _normalize_ranking(SortField.STARS, OrderDir.DESC, user_query) == (
        SortField.STARS,
        OrderDir.DESC,
    )


def test_idempotent_stars_desc_with_cjk_ranking_query() -> None:
    user_query = "按star排序"
    assert _normalize_ranking(SortField.STARS, OrderDir.DESC, user_query) == (
        SortField.STARS,
        OrderDir.DESC,
    )


# ---------------------------------------------------------------------------
# §3.3 末段: ranking intent + parser non-stars sort → DO NOT overwrite
# ---------------------------------------------------------------------------


def test_ranking_intent_does_not_overwrite_updated_sort() -> None:
    user_query = "popular rust projects"
    assert _normalize_ranking(SortField.UPDATED, OrderDir.DESC, user_query) == (
        SortField.UPDATED,
        OrderDir.DESC,
    )


def test_ranking_intent_does_not_overwrite_forks_sort() -> None:
    user_query = "trending go libraries"
    assert _normalize_ranking(SortField.FORKS, OrderDir.DESC, user_query) == (
        SortField.FORKS,
        OrderDir.DESC,
    )


# ---------------------------------------------------------------------------
# §3.1 phrase boundary: English multi-word phrases must match the WHOLE phrase
# ---------------------------------------------------------------------------


def test_partial_phrase_does_not_match_lots_of_stars() -> None:
    # "lots of fries" lacks the 'stars' tail → no ranking intent
    user_query = "got lots of fries today"
    assert _normalize_ranking(None, None, user_query) == (None, None)


def test_partial_phrase_does_not_match_ranked_by_stars() -> None:
    # "ranked by relevance" is not the lexicon phrase
    user_query = "repos ranked by relevance"
    assert _normalize_ranking(None, None, user_query) == (None, None)


def test_partial_phrase_does_not_match_sorted_by_stars() -> None:
    user_query = "sorted by recency"
    assert _normalize_ranking(None, None, user_query) == (None, None)


def test_most_alone_does_not_trigger() -> None:
    # 'most' without 'stars' should not trigger
    user_query = "the most useful repos"
    assert _normalize_ranking(None, None, user_query) == (None, None)


def test_starlight_does_not_match_most_stars() -> None:
    # 'starlight' contains 'star' substring but no whole 'stars' word
    user_query = "most starlight glow"
    assert _normalize_ranking(None, None, user_query) == (None, None)


# ---------------------------------------------------------------------------
# §3.1 CJK phrase boundary: must match the full 排序 phrase
# ---------------------------------------------------------------------------


def test_cjk_partial_does_not_match() -> None:
    # 按star顯示 is not the 排序 phrase
    user_query = "按star顯示"
    assert _normalize_ranking(None, None, user_query) == (None, None)


# ---------------------------------------------------------------------------
# §3.1 top N variants — both connected and spaced forms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_query",
    [
        "top10 go repos",
        "top 10 go repos",
        "top 5 react libraries",
        "TOP10 GO REPOS",  # case-insensitive
    ],
)
def test_top_n_variants(user_query: str) -> None:
    assert _normalize_ranking(None, None, user_query) == (
        SortField.STARS,
        OrderDir.DESC,
    )


def test_top_alone_does_not_trigger() -> None:
    # 'top' without a number should not match `top N`
    user_query = "top quality go libs"
    assert _normalize_ranking(None, None, user_query) == (None, None)


# ---------------------------------------------------------------------------
# §3.1 case-insensitive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_query",
    [
        "POPULAR rust projects",
        "Trending Go Libraries",
        "Ranked By Stars",
    ],
)
def test_case_insensitive(user_query: str) -> None:
    assert _normalize_ranking(None, None, user_query) == (
        SortField.STARS,
        OrderDir.DESC,
    )


# ---------------------------------------------------------------------------
# Edge: empty / whitespace user_query
# ---------------------------------------------------------------------------


def test_empty_user_query_no_ranking_intent() -> None:
    assert _normalize_ranking(None, None, "") == (None, None)


def test_whitespace_user_query_no_ranking_intent() -> None:
    assert _normalize_ranking(None, None, "   \n\t ") == (None, None)
