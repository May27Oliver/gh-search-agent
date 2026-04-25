"""Iter9 RED: language evidence policy unit tests.

Covers ITER9_LANGUAGE_OVERINFERENCE_RESIDUAL_SPEC §7.1.

Targets the read-only SSoT helper `_suppress_unsupported_language(language,
user_query)` used by `validate_query` to clear `language` facets that have
no explicit user-query evidence.
"""
from __future__ import annotations

import pytest

from gh_search.tools.validate_query import _suppress_unsupported_language


# ---------------------------------------------------------------------------
# §7.1 (group 1): no explicit anchor → clear language
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_query,language",
    [
        ("find me some popular react component libraries", "JavaScript"),
        ("recommend some vue 3 admin dashboard templates", "Vue"),
        ("日本語で書かれたReactのサンプルプロジェクトを10個教えて", "JavaScript"),
    ],
)
def test_no_explicit_anchor_clears_language(user_query: str, language: str) -> None:
    assert _suppress_unsupported_language(language, user_query) is None


# ---------------------------------------------------------------------------
# §7.1 (group 2): explicit anchor + matching pred → preserve
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_query,language",
    [
        ("javascript testing frameworks", "JavaScript"),
        ("c++ game engines", "C++"),
        ("python scraping repos", "Python"),
        ("list 15 java spring boot starter projects from 2024 ranked by stars", "Java"),
        (
            "trending rust projects from last year with over 500 stars but under 10k",
            "Rust",
        ),
        ("find me 20 popular TypeScript ORM libraries with more than 2k stars", "TypeScript"),
    ],
)
def test_explicit_anchor_preserves_language(user_query: str, language: str) -> None:
    assert _suppress_unsupported_language(language, user_query) == language


# ---------------------------------------------------------------------------
# §7.1 (group 3): alias evidence → preserve
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_query,language",
    [
        ("golang cli tools", "Go"),
        ("js chatbot libraries", "JavaScript"),
        ("ts orm options", "TypeScript"),
        ("py scraping repos", "Python"),
        ("cpp template metaprogramming", "C++"),
    ],
)
def test_alias_evidence_preserves_language(user_query: str, language: str) -> None:
    assert _suppress_unsupported_language(language, user_query) == language


# Dataset-anchored typo aliases (q023 / q024).
@pytest.mark.parametrize(
    "user_query,language",
    [
        ("pythn web frameework sorted by strs", "Python"),
        ("javscript chatbot libs with min 500 starz plz", "JavaScript"),
    ],
)
def test_dataset_typo_alias_preserves_language(
    user_query: str, language: str
) -> None:
    assert _suppress_unsupported_language(language, user_query) == language


# ---------------------------------------------------------------------------
# §7.1 (group 4): idempotence — pred=None must stay None
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_query",
    [
        "any random query",
        "python web framework",
        "",
    ],
)
def test_pred_language_none_is_idempotent(user_query: str) -> None:
    assert _suppress_unsupported_language(None, user_query) is None


# ---------------------------------------------------------------------------
# §7.1 (group 5): unknown / non-canonical predicted language → clear
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "user_query,language",
    [
        # Vue is not in _LANGUAGE_TOKEN_TO_FACET — no anchor can ever justify it.
        ("vue 3 admin dashboard templates", "Vue"),
        # Hallucinated language name.
        ("react component libraries", "JavaScriptish"),
        # Empty / whitespace.
        ("react component libraries", ""),
        ("react component libraries", "  "),
    ],
)
def test_non_canonical_pred_is_cleared(user_query: str, language: str) -> None:
    assert _suppress_unsupported_language(language, user_query) is None


# ---------------------------------------------------------------------------
# §7.1 (group 6): token-boundary / special-char matching
# ---------------------------------------------------------------------------


def test_java_anchor_does_not_falsely_preserve_javascript_pred() -> None:
    # 'find me java tutorials' has anchor 'java' (canonical=Java).
    # pred='JavaScript' — query canonical (Java) != pred (JavaScript) → clear.
    assert (
        _suppress_unsupported_language("JavaScript", "find me java tutorials") is None
    )


def test_javascript_anchor_does_not_falsely_preserve_java_pred() -> None:
    # Inverse: 'javascript testing frameworks' has only the JavaScript anchor.
    # 'java' substring of 'javascript' must NOT match Java token-bounded.
    assert (
        _suppress_unsupported_language("Java", "javascript testing frameworks") is None
    )


def test_cjk_adjacent_anchor_still_matches() -> None:
    # CJK chars are non-[A-Za-z0-9] → valid token boundary.
    assert (
        _suppress_unsupported_language("Python", "python で書かれた爬蟲") == "Python"
    )


def test_c_plus_plus_anchor_special_chars() -> None:
    assert _suppress_unsupported_language("C++", "c++ game engines") == "C++"


def test_c_sharp_anchor_special_chars() -> None:
    assert _suppress_unsupported_language("C#", "find me c# tutorials") == "C#"


def test_anchor_substring_inside_larger_word_does_not_match() -> None:
    assert _suppress_unsupported_language("Rust", "rusty old projects") is None
    assert _suppress_unsupported_language("Python", "the pythonista community") is None


def test_anchor_matching_is_case_insensitive() -> None:
    assert _suppress_unsupported_language("Python", "PYTHON web stuff") == "Python"
    assert _suppress_unsupported_language("Python", "Python web stuff") == "Python"


def test_pred_canonical_compare_is_case_insensitive() -> None:
    # Parser may emit lowercase variant; should still preserve when query supports it.
    assert (
        _suppress_unsupported_language("javascript", "js chatbot libraries")
        == "javascript"
    )
