"""ITER6_LANGUAGE_OVERINFERENCE_SPEC §7.1: language evidence policy.

Validates `normalize_language_facet(raw_language, user_query)` —
single source of truth for language facet contraction (§3.3, §6.3).
The helper returns `(normalized_language, issues)`:

- preserve raw_language when explicit evidence exists in user_query
- clear it when only implicit (framework/topic) evidence exists
- pass through unchanged when raw_language is None
"""
from __future__ import annotations

import pytest

from gh_search.normalizers.language_rules import normalize_language_facet


# ---------------------------------------------------------------------------
# Clear path (no explicit evidence in user_query)
# ---------------------------------------------------------------------------


def test_react_in_query_clears_javascript_inference():
    """q001 GPT pattern: parser infers JS from `react`, no explicit language."""
    lang, issues = normalize_language_facet(
        raw_language="JavaScript",
        user_query="find me some popular react component libraries",
    )
    assert lang is None
    assert any(i.code == "language_inferred_without_evidence" for i in issues)


def test_vue_3_in_query_clears_vue_language():
    """q009 GPT pattern: parser treats `vue 3` framework as language."""
    lang, issues = normalize_language_facet(
        raw_language="Vue",
        user_query="recommend some vue 3 admin dashboard templates",
    )
    assert lang is None
    assert any(i.code == "language_inferred_without_evidence" for i in issues)


def test_japanese_react_query_clears_javascript_inference():
    """q029 GPT/CLA pattern: CJK query with React framework but no explicit lang."""
    lang, issues = normalize_language_facet(
        raw_language="JavaScript",
        user_query="日本語で書かれた React のサンプルプロジェクト",
    )
    assert lang is None
    assert any(i.code == "language_inferred_without_evidence" for i in issues)


def test_mismatched_evidence_still_clears():
    """If raw_language doesn't match any evidence in query, it's contraction."""
    lang, issues = normalize_language_facet(
        raw_language="JavaScript",
        user_query="golang cli tools",  # evidence is Go, not JS
    )
    assert lang is None
    assert any(i.code == "language_inferred_without_evidence" for i in issues)


# ---------------------------------------------------------------------------
# Preserve path (explicit evidence matches raw_language)
# ---------------------------------------------------------------------------


def test_golang_evidence_preserves_go():
    """q004 pattern: `golang` is alias for Go."""
    lang, _ = normalize_language_facet(
        raw_language="Go",
        user_query="any good golang cli tools out there?",
    )
    assert lang == "Go"


def test_bare_go_evidence_preserves_go():
    """q012 / q025 pattern: `go` standalone is language token."""
    lang, _ = normalize_language_facet(
        raw_language="Go",
        user_query="give me top 5 go repos made before 2020",
    )
    assert lang == "Go"


def test_python_evidence_preserves_python():
    """q011 / q017 pattern."""
    lang, _ = normalize_language_facet(
        raw_language="Python",
        user_query="python scraping libraries created after 2023",
    )
    assert lang == "Python"


def test_pythn_typo_preserves_python():
    """§3.1 typo tolerance: pythn → Python evidence."""
    lang, _ = normalize_language_facet(
        raw_language="Python",
        user_query="pythn web frameework sorted by strs",
    )
    assert lang == "Python"


def test_typescript_evidence_preserves_typescript():
    """q015 pattern."""
    lang, _ = normalize_language_facet(
        raw_language="TypeScript",
        user_query="find me 20 popular TypeScript ORM libraries with more than 2k stars",
    )
    assert lang == "TypeScript"


def test_ts_alias_evidence_preserves_typescript():
    """§3.1 alias: ts → TypeScript evidence."""
    lang, _ = normalize_language_facet(
        raw_language="TypeScript",
        user_query="ts repos with redux",
    )
    assert lang == "TypeScript"


def test_rust_evidence_preserves_rust():
    """q013 / q030 pattern."""
    lang, _ = normalize_language_facet(
        raw_language="Rust",
        user_query="trending rust projects from last year",
    )
    assert lang == "Rust"


def test_swift_evidence_preserves_swift():
    """q021 pattern."""
    lang, _ = normalize_language_facet(
        raw_language="Swift",
        user_query="show me some cool swift repos",
    )
    assert lang == "Swift"


def test_java_evidence_preserves_java():
    """q018 pattern."""
    lang, _ = normalize_language_facet(
        raw_language="Java",
        user_query="list 15 java spring boot starter projects",
    )
    assert lang == "Java"


def test_javascript_evidence_preserves_javascript():
    """q014 pattern: explicit `javascript` token must preserve."""
    lang, _ = normalize_language_facet(
        raw_language="JavaScript",
        user_query="javascript testing frameworks between 2019 and 2022",
    )
    assert lang == "JavaScript"


def test_javscript_typo_preserves_javascript():
    """q024 pattern: `javscript` typo must still count as JavaScript evidence."""
    lang, _ = normalize_language_facet(
        raw_language="JavaScript",
        user_query="javscript chatbot libs with min 500 starz plz",
    )
    assert lang == "JavaScript"


def test_cpp_evidence_preserves_cpp():
    """q016 pattern: `c++` token must preserve C++ (not get tokenized to `c`)."""
    lang, _ = normalize_language_facet(
        raw_language="C++",
        user_query="c++ game engines sorted by most recently updated",
    )
    assert lang == "C++"


def test_evidence_match_is_case_insensitive():
    lang, _ = normalize_language_facet(
        raw_language="Python",
        user_query="PYTHON microservice frameworks",
    )
    assert lang == "Python"


# ---------------------------------------------------------------------------
# Pass-through (raw_language is None)
# ---------------------------------------------------------------------------


def test_none_raw_language_passes_through_with_no_issues():
    lang, issues = normalize_language_facet(
        raw_language=None,
        user_query="any good react component libraries",
    )
    assert lang is None
    assert issues == []


def test_none_raw_language_with_explicit_evidence_still_none():
    """Parser produced None; we don't add language even if query mentions one."""
    lang, issues = normalize_language_facet(
        raw_language=None,
        user_query="python web frameworks",
    )
    assert lang is None
    assert issues == []


# ---------------------------------------------------------------------------
# Iter5 target pairs as parametrized contract (§5.1 + §5.2)
# ---------------------------------------------------------------------------


ITER6_PRIMARY_TARGETS = [
    # (qid+model, raw_language, user_query, expected_language)
    ("q001-GPT", "JavaScript", "find me some popular react component libraries", None),
    ("q009-GPT", "Vue", "recommend some vue 3 admin dashboard templates", None),
    ("q029-GPT", "JavaScript", "日本語で書かれた React のサンプルプロジェクト", None),
    ("q029-CLA", "JavaScript", "日本語で書かれた React のサンプルプロジェクト", None),
]


@pytest.mark.parametrize(
    "case_id,raw_language,user_query,expected",
    ITER6_PRIMARY_TARGETS,
    ids=[c[0] for c in ITER6_PRIMARY_TARGETS],
)
def test_iter6_primary_target_clears_language(
    case_id: str, raw_language: str, user_query: str, expected
):
    lang, _ = normalize_language_facet(
        raw_language=raw_language, user_query=user_query
    )
    assert lang == expected


ITER6_POSITIVE_PRESERVATION = [
    # (qid, raw_language, user_query)
    ("q004", "Go", "any good golang cli tools out there?"),
    ("q011", "Python", "python scraping libraries created after 2023 with at least 1000 stars"),
    ("q014", "JavaScript", "javascript testing frameworks between 2019 and 2022"),
    ("q015", "TypeScript", "find me 20 popular TypeScript ORM libraries with more than 2k stars"),
    ("q016", "C++", "c++ game engines sorted by most recently updated"),
    ("q017", "Python", "small python utilities under 100 stars created this year"),
    ("q024", "JavaScript", "javscript chatbot libs with min 500 starz plz"),
    ("q025", "Go", "gimme top10 go repoz created aftr 2022!!!"),
    ("q028", "Go", "推荐几个2023年以后创建的golang微服务框架，按star排序"),
]


@pytest.mark.parametrize(
    "qid,raw_language,user_query",
    ITER6_POSITIVE_PRESERVATION,
    ids=[c[0] for c in ITER6_POSITIVE_PRESERVATION],
)
def test_iter6_positive_set_preserves_language(
    qid: str, raw_language: str, user_query: str
):
    lang, _ = normalize_language_facet(
        raw_language=raw_language, user_query=user_query
    )
    assert lang == raw_language, (
        f"{qid} positive set must preserve language={raw_language!r}, got {lang!r}"
    )
