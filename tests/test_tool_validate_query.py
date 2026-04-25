"""Task 3.6 RED: validate_query tool (TOOLS.md §3 validate_query)."""
from __future__ import annotations

import pytest

from gh_search.schemas import (
    Control,
    Execution,
    ExecutionStatus,
    IntentionJudge,
    IntentStatus,
    SharedAgentState,
    StructuredQuery,
    TerminateReason,
    ToolName,
    Validation,
)
from gh_search.tools import validate_query


def _base_state(**overrides) -> SharedAgentState:
    default = dict(
        run_id="r1",
        turn_index=2,
        max_turns=5,
        user_query="python logistics",
        intention_judge=IntentionJudge(
            intent_status=IntentStatus.SUPPORTED, reason=None, should_terminate=False
        ),
        structured_query=None,
        validation=Validation(is_valid=False, errors=[], missing_required_fields=[]),
        compiled_query=None,
        execution=Execution(
            status=ExecutionStatus.NOT_STARTED, response_status=None, result_count=None
        ),
        control=Control(
            next_tool=ToolName.VALIDATE_QUERY, should_terminate=False, terminate_reason=None
        ),
    )
    default.update(overrides)
    return SharedAgentState(**default)


def _valid_sq() -> StructuredQuery:
    return StructuredQuery.model_validate(
        {
            "keywords": ["logistics"],
            "language": "Python",
            "created_after": None,
            "created_before": None,
            "min_stars": 100,
            "max_stars": None,
            "sort": "stars",
            "order": "desc",
            "limit": 10,
        }
    )


def _conflicting_sq() -> StructuredQuery:
    return StructuredQuery.model_validate(
        {
            "keywords": ["x"],
            "language": None,
            "created_after": None,
            "created_before": None,
            "min_stars": 500,
            "max_stars": 100,
            "sort": None,
            "order": None,
            "limit": 10,
        }
    )


def test_valid_query_passes_and_routes_to_compile():
    state = _base_state(structured_query=_valid_sq())
    new_state = validate_query(state)

    assert new_state is not state  # immutability
    assert new_state.validation.is_valid is True
    assert new_state.validation.errors == []
    assert new_state.control.next_tool is ToolName.COMPILE_GITHUB_QUERY
    assert new_state.control.should_terminate is False


def test_invalid_query_routes_to_repair():
    # iter10 query-driven rewrite would clear bounds without star evidence,
    # masking the validator-level conflict. Anchor the conflict in user_query
    # so iter10 preserves min=500 / max=100 verbatim and validator still trips.
    state = _base_state(
        user_query="python repos with min 500 stars but max 100 stars",
        structured_query=_conflicting_sq(),
    )
    new_state = validate_query(state)

    assert new_state.validation.is_valid is False
    assert new_state.validation.errors  # non-empty
    assert new_state.control.next_tool is ToolName.REPAIR_QUERY
    assert new_state.control.should_terminate is False


def test_missing_structured_query_terminates_with_validation_failed():
    state = _base_state(structured_query=None)
    new_state = validate_query(state)

    assert new_state.validation.is_valid is False
    assert any(e.code == "parse_failed" for e in new_state.validation.errors)
    assert new_state.control.next_tool is ToolName.FINALIZE
    assert new_state.control.should_terminate is True
    assert new_state.control.terminate_reason is TerminateReason.VALIDATION_FAILED


def test_does_not_mutate_structured_query_or_execution():
    sq = _valid_sq()
    # _valid_sq carries min_stars=100; anchor it so iter10 preserves it as-is
    # and the immutability check is meaningful.
    state = _base_state(
        user_query="python logistics with at least 100 stars",
        structured_query=sq,
    )
    new_state = validate_query(state)

    assert new_state.structured_query == sq
    assert new_state.execution == state.execution
    assert new_state.compiled_query is None


def test_preserves_other_state_fields():
    state = _base_state(
        user_query="python logistics with at least 100 stars",
        structured_query=_valid_sq(),
    )
    new_state = validate_query(state)

    assert new_state.run_id == state.run_id
    assert new_state.user_query == state.user_query
    assert new_state.intention_judge == state.intention_judge


# ---------------------------------------------------------------------------
# Iter8 multilingual canonicalization integration
# (ITER8_MULTILINGUAL_CANONICALIZATION_SPEC §7.2)
# ---------------------------------------------------------------------------


def _sq_with_keywords(keywords: list[str], language: str | None = None) -> StructuredQuery:
    return StructuredQuery.model_validate(
        {
            "keywords": keywords,
            "language": language,
            "created_after": None,
            "created_before": None,
            "min_stars": None,
            "max_stars": None,
            "sort": None,
            "order": None,
            "limit": 10,
        }
    )


@pytest.mark.parametrize(
    "qid,raw_keywords,language,expected_keywords",
    [
        # q027 GPT/CLA shape: parser emits scraping + 套件
        ("q027_pair", ["scraping", "套件"], None, ["scraping", "crawler"]),
        # q027 DSK shape: parser emits the joined CJK compound
        ("q027_compound", ["爬蟲套件"], None, ["scraping", "crawler"]),
        # q028 GPT shape: simplified Chinese compound
        ("q028", ["微服务框架"], "Go", ["microservice", "framework"]),
        # q029 GPT shape: Japanese compound + topic token
        ("q029_compound", ["react", "サンプルプロジェクト"], None, ["react", "sample"]),
        # q029 DSK shape: trio of canonical English tokens
        (
            "q029_trio",
            ["react", "sample", "project", "japanese"],
            None,
            ["react", "sample"],
        ),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_iter8_multilingual_canonicalization_through_validate_query(
    qid: str,
    raw_keywords: list[str],
    language: str | None,
    expected_keywords: list[str],
) -> None:
    sq = _sq_with_keywords(raw_keywords, language=language)
    state = _base_state(structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert list(new_state.structured_query.keywords) == expected_keywords, (
        f"{qid}: validate_query did not apply iter8 canonicalization"
    )
    assert new_state.validation.is_valid is True, (
        f"{qid}: post-canonicalization keywords should be semantically valid"
    )


# ---------------------------------------------------------------------------
# Iter9 language over-inference suppression integration
# (ITER9_LANGUAGE_OVERINFERENCE_RESIDUAL_SPEC §7.2)
# ---------------------------------------------------------------------------


def _sq_with_facets(
    keywords: list[str], language: str | None
) -> StructuredQuery:
    return StructuredQuery.model_validate(
        {
            "keywords": keywords,
            "language": language,
            "created_after": None,
            "created_before": None,
            "min_stars": None,
            "max_stars": None,
            "sort": None,
            "order": None,
            "limit": 10,
        }
    )


@pytest.mark.parametrize(
    "qid,user_query,raw_keywords,raw_language",
    [
        # q001 GPT: "find me some popular react component libraries" + pred='JavaScript'.
        (
            "q001_gpt",
            "find me some popular react component libraries",
            ["react", "component", "library"],
            "JavaScript",
        ),
        # q009 GPT: pred hallucinates language='Vue' from framework token.
        (
            "q009_gpt",
            "recommend some vue 3 admin dashboard templates",
            ["vue 3", "admin", "dashboard", "template"],
            "Vue",
        ),
        # q029 GPT: Japanese query, pred infers JavaScript from React framework.
        (
            "q029_gpt",
            "日本語で書かれたReactのサンプルプロジェクトを10個教えて",
            ["react", "sample"],
            "JavaScript",
        ),
        # q029 CLA: contract-only — language must be cleared even if keywords incomplete.
        (
            "q029_cla_contract",
            "日本語で書かれたReactのサンプルプロジェクトを10個教えて",
            ["sample"],
            "JavaScript",
        ),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_iter9_language_overinference_cleared_through_validate_query(
    qid: str,
    user_query: str,
    raw_keywords: list[str],
    raw_language: str,
) -> None:
    sq = _sq_with_facets(raw_keywords, language=raw_language)
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert new_state.structured_query.language is None, (
        f"{qid}: language should be cleared when user_query has no explicit anchor"
    )


@pytest.mark.parametrize(
    "qid,user_query,raw_keywords,raw_language",
    [
        # q018 GPT shape: explicit 'java' anchor.
        (
            "q018_java",
            "list 15 java spring boot starter projects from 2024 ranked by stars",
            ["spring boot", "starter"],
            "Java",
        ),
        # q015 GPT shape: explicit 'TypeScript' anchor.
        (
            "q015_typescript",
            "find me 20 popular TypeScript ORM libraries with more than 2k stars",
            ["orm", "library"],
            "TypeScript",
        ),
        # q027 shape: explicit 'python' anchor in CJK-mixed query.
        (
            "q027_python",
            "幫我找一下熱門的 python 爬蟲套件，star 數超過 1000 的",
            ["scraping", "crawler"],
            "Python",
        ),
        # q013 shape: explicit 'rust' anchor.
        (
            "q013_rust",
            "trending rust projects from last year with over 500 stars but under 10k",
            ["trending"],
            "Rust",
        ),
        # alias path: 'golang' must preserve Go.
        (
            "alias_golang",
            "golang cli tools with lots of stars",
            ["cli", "tool"],
            "Go",
        ),
        # q023 typo: 'pythn' must preserve Python.
        (
            "q023_pythn",
            "pythn web frameework sorted by strs",
            ["web", "framework"],
            "Python",
        ),
        # q024 typo: 'javscript' must preserve JavaScript.
        (
            "q024_javscript",
            "javscript chatbot libs with min 500 starz plz",
            ["chatbot", "library"],
            "JavaScript",
        ),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_iter9_explicit_language_preserved_through_validate_query(
    qid: str,
    user_query: str,
    raw_keywords: list[str],
    raw_language: str,
) -> None:
    sq = _sq_with_facets(raw_keywords, language=raw_language)
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert new_state.structured_query.language == raw_language, (
        f"{qid}: language should be preserved when user_query carries an explicit anchor"
    )


# ---------------------------------------------------------------------------
# Iter10 numeric evidence integration
# (ITER10_STARS_NUMERIC_SEMANTICS_SPEC §7.2)
# ---------------------------------------------------------------------------


def _sq_with_stars(
    *,
    min_stars: int | None,
    max_stars: int | None,
    keywords: list[str] | None = None,
    language: str | None = None,
    sort: str | None = None,
    order: str | None = None,
    limit: int = 10,
) -> StructuredQuery:
    return StructuredQuery.model_validate(
        {
            "keywords": keywords or [],
            "language": language,
            "created_after": None,
            "created_before": None,
            "min_stars": min_stars,
            "max_stars": max_stars,
            "sort": sort,
            "order": order,
            "limit": limit,
        }
    )


@pytest.mark.parametrize(
    "qid,user_query,raw_min,raw_max,expected_min,expected_max",
    [
        # §6.1 primary targets
        (
            "q013_cla",
            "trending rust projects from last year with over 500 stars but under 10k",
            500,
            10000,
            501,
            9999,
        ),
        (
            "q020_dsk",
            "popular stuff on github",
            100,
            None,
            None,
            None,
        ),
        (
            "q026_gpt",
            "rect native ui kit     with    lots     of stars",
            1,
            None,
            None,
            None,
        ),
        # §6.3 guard set: currently-correct cases must passthrough
        (
            "q011_inclusive_passthrough",
            "python scraping libraries created after 2023 with at least 1000 stars",
            1000,
            None,
            1000,
            None,
        ),
        (
            "q015_exclusive_passthrough",
            "find me 20 popular TypeScript ORM libraries with more than 2k stars",
            2001,
            None,
            2001,
            None,
        ),
        (
            "q017_exclusive_upper_passthrough",
            "small python utilities under 100 stars created this year",
            None,
            99,
            None,
            99,
        ),
        (
            "q024_inclusive_min_passthrough",
            "javscript chatbot libs with min 500 starz plz",
            500,
            None,
            500,
            None,
        ),
        (
            "q027_cjk_exclusive_passthrough",
            "幫我找一下熱門的 python 爬蟲套件，star 數超過 1000 的",
            1001,
            None,
            1001,
            None,
        ),
        # parser dropped values that query supports → query-driven rewrite must add
        (
            "q013_parser_dropped_both",
            "trending rust projects from last year with over 500 stars but under 10k",
            None,
            None,
            501,
            9999,
        ),
        # parser used inclusive interpretation; query is exclusive → rewrite
        (
            "q015_inclusive_to_exclusive_rewrite",
            "find me 20 popular TypeScript ORM libraries with more than 2k stars",
            2000,
            None,
            2001,
            None,
        ),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_iter10_numeric_evidence_through_validate_query(
    qid: str,
    user_query: str,
    raw_min: int | None,
    raw_max: int | None,
    expected_min: int | None,
    expected_max: int | None,
) -> None:
    sq = _sq_with_stars(min_stars=raw_min, max_stars=raw_max)
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert new_state.structured_query.min_stars == expected_min, (
        f"{qid}: min_stars mismatch"
    )
    assert new_state.structured_query.max_stars == expected_max, (
        f"{qid}: max_stars mismatch"
    )


@pytest.mark.parametrize(
    "qid,raw_min,raw_max",
    [
        ("q030_gpt_swap", 100, 500),
        ("q030_cla_swap", 100, 500),
        ("q030_dsk_reversed", 99, 501),
        ("q030_parser_dropped", None, None),
        ("q030_already_correct", 501, 99),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_iter10_q030_contradictory_range_contract(
    qid: str, raw_min: int | None, raw_max: int | None
) -> None:
    user_query = "找一些 star 超過 500 但少於 100 的 rust 專案"
    sq = _sq_with_stars(min_stars=raw_min, max_stars=raw_max, language="Rust")
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert new_state.structured_query.min_stars == 501, (
        f"{qid}: q030 contract requires min_stars=501"
    )
    assert new_state.structured_query.max_stars == 99, (
        f"{qid}: q030 contract requires max_stars=99"
    )


# ---------------------------------------------------------------------------
# Iter10 §7.3 guard: numeric-only scope — non-numeric facets must be untouched
# ---------------------------------------------------------------------------


def test_iter10_does_not_mutate_keywords() -> None:
    user_query = "rust projects with over 500 stars but under 10k"
    # 'logistics' is a topical keyword the iter8 normalizer leaves alone, so
    # any change here would have to come from iter10 numeric normalization.
    sq = _sq_with_stars(
        min_stars=500,
        max_stars=10000,
        keywords=["logistics"],
    )
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert list(new_state.structured_query.keywords) == ["logistics"]


def test_iter10_does_not_mutate_language() -> None:
    user_query = "find me 20 popular TypeScript ORM libraries with more than 2k stars"
    sq = _sq_with_stars(
        min_stars=2000,
        max_stars=None,
        keywords=["orm", "library"],
        language="TypeScript",
    )
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert new_state.structured_query.language == "TypeScript"


def test_iter10_does_not_mutate_sort_order() -> None:
    user_query = "popular stuff on github"
    sq = _sq_with_stars(
        min_stars=100,
        max_stars=None,
        sort="stars",
        order="desc",
    )
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    # Iter10 must clear hallucinated min_stars …
    assert new_state.structured_query.min_stars is None
    # … but must not touch sort/order set by upstream.
    assert new_state.structured_query.sort is not None
    assert new_state.structured_query.order is not None


def test_iter10_popular_alone_does_not_inject_min_stars() -> None:
    user_query = "popular stuff on github"
    sq = _sq_with_stars(min_stars=None, max_stars=None)
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert new_state.structured_query.min_stars is None
    assert new_state.structured_query.max_stars is None


def test_iter10_trending_alone_does_not_inject_min_stars() -> None:
    user_query = "trending repos"
    sq = _sq_with_stars(min_stars=None, max_stars=None)
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert new_state.structured_query.min_stars is None
    assert new_state.structured_query.max_stars is None


# ---------------------------------------------------------------------------
# Iter11 ranking intent integration
# (ITER11_SORT_DEFAULTS_SPEC §7.2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "qid,user_query",
    [
        # §6.1 DSK primary targets — all carry ranking intent in raw query
        (
            "q013_dsk",
            "trending rust projects from last year with over 500 stars but under 10k",
        ),
        (
            "q015_dsk",
            "find me 20 popular TypeScript ORM libraries with more than 2k stars",
        ),
        (
            "q026_dsk",
            "rect native ui kit     with    lots     of stars",
        ),
        (
            "q027_dsk",
            "幫我找一下熱門的 python 爬蟲套件，star 數超過 1000 的",
        ),
        # §6.2 bonus — q020 GPT
        (
            "q020_gpt_bonus",
            "popular stuff on github",
        ),
        # §6.3 guard — currently-correct cases must remain stars desc
        (
            "q025_top_n",
            "gimme top10 go repoz created aftr 2022!!!",
        ),
        (
            "q028_cjk_compact",
            "推荐几个2023年以后创建的golang微服务框架，按star排序",
        ),
    ],
    ids=lambda v: v if isinstance(v, str) else None,
)
def test_iter11_ranking_intent_through_validate_query(
    qid: str, user_query: str
) -> None:
    # Raw parser output dropped sort/order — iter11 must fill (stars, desc).
    sq = _sq_with_stars(min_stars=None, max_stars=None, sort=None, order=None)
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert new_state.structured_query.sort is not None, f"{qid}: sort missing"
    assert new_state.structured_query.sort.value == "stars", (
        f"{qid}: expected sort=stars"
    )
    assert new_state.structured_query.order is not None, f"{qid}: order missing"
    assert new_state.structured_query.order.value == "desc", (
        f"{qid}: expected order=desc"
    )


def test_iter11_idempotent_when_parser_already_correct() -> None:
    # Parser already gave stars/desc; ranking query reaffirms — must not flip.
    user_query = "popular TypeScript ORM libraries with more than 2k stars"
    sq = _sq_with_stars(min_stars=2001, max_stars=None, sort="stars", order="desc")
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert new_state.structured_query.sort is not None
    assert new_state.structured_query.sort.value == "stars"
    assert new_state.structured_query.order is not None
    assert new_state.structured_query.order.value == "desc"


# ---------------------------------------------------------------------------
# Iter11 §7.3 guard: sort-only scope — other facets must be untouched
# ---------------------------------------------------------------------------


def test_iter11_does_not_mutate_keywords() -> None:
    user_query = "popular TypeScript ORM libraries"
    sq = _sq_with_stars(
        min_stars=None,
        max_stars=None,
        keywords=["orm", "library"],
        language="TypeScript",
    )
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert list(new_state.structured_query.keywords) == ["orm", "library"]


def test_iter11_does_not_mutate_language() -> None:
    user_query = "popular TypeScript ORM libraries"
    sq = _sq_with_stars(
        min_stars=None,
        max_stars=None,
        keywords=["orm"],
        language="TypeScript",
    )
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert new_state.structured_query.language == "TypeScript"


def test_iter11_does_not_mutate_numeric_bounds() -> None:
    # Ranking phrase + explicit stars threshold — iter11 must not touch numerics
    # (those are iter10's job; §3.2).
    user_query = "popular TypeScript ORM libraries with more than 2k stars"
    sq = _sq_with_stars(min_stars=2001, max_stars=None, sort=None, order=None)
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert new_state.structured_query.min_stars == 2001
    assert new_state.structured_query.max_stars is None


def test_iter11_no_ranking_intent_does_not_invent_sort() -> None:
    # No ranking phrase → iter11 must not invent sort/order.
    user_query = "vue 3 admin dashboard templates"
    sq = _sq_with_stars(min_stars=None, max_stars=None, sort=None, order=None)
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert new_state.structured_query.sort is None
    assert new_state.structured_query.order is None


def test_iter11_does_not_overwrite_non_stars_sort() -> None:
    # Ranking intent present, but parser chose `updated` — iter11 must NOT
    # overwrite (§3.3 末段).
    user_query = "popular rust projects"
    sq = _sq_with_stars(
        min_stars=None,
        max_stars=None,
        sort="updated",
        order="desc",
    )
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert new_state.structured_query.sort is not None
    assert new_state.structured_query.sort.value == "updated"
    assert new_state.structured_query.order is not None
    assert new_state.structured_query.order.value == "desc"


def test_iter11_does_not_clear_existing_sort_when_no_intent() -> None:
    # No ranking phrase + parser chose `updated` — iter11 must not clear
    # existing sort/order (§3.3).
    user_query = "vue 3 admin dashboard templates"
    sq = _sq_with_stars(
        min_stars=None,
        max_stars=None,
        sort="updated",
        order="desc",
    )
    state = _base_state(user_query=user_query, structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert new_state.structured_query.sort is not None
    assert new_state.structured_query.sort.value == "updated"
    assert new_state.structured_query.order is not None
    assert new_state.structured_query.order.value == "desc"
