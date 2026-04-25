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
    state = _base_state(structured_query=_conflicting_sq())
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
    state = _base_state(structured_query=sq)
    new_state = validate_query(state)

    assert new_state.structured_query == sq
    assert new_state.execution == state.execution
    assert new_state.compiled_query is None


def test_preserves_other_state_fields():
    state = _base_state(structured_query=_valid_sq())
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
