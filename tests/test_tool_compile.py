"""Task 3.7 RED: compile_github_query tool (TOOLS.md §3 compile_github_query)."""
from __future__ import annotations

from gh_search.schemas import (
    Control,
    Execution,
    ExecutionStatus,
    IntentStatus,
    IntentionJudge,
    SharedAgentState,
    StructuredQuery,
    ToolName,
    Validation,
)
from gh_search.tools import compile_github_query


def _state_with_valid_query() -> SharedAgentState:
    sq = StructuredQuery.model_validate(
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
    return SharedAgentState(
        run_id="r1",
        turn_index=3,
        max_turns=5,
        user_query="python logistics 100+ stars",
        intention_judge=IntentionJudge(
            intent_status=IntentStatus.SUPPORTED, reason=None, should_terminate=False
        ),
        structured_query=sq,
        validation=Validation(is_valid=True, errors=[], missing_required_fields=[]),
        compiled_query=None,
        execution=Execution(
            status=ExecutionStatus.NOT_STARTED, response_status=None, result_count=None
        ),
        control=Control(
            next_tool=ToolName.COMPILE_GITHUB_QUERY,
            should_terminate=False,
            terminate_reason=None,
        ),
    )


def test_compile_sets_compiled_query_string():
    state = _state_with_valid_query()
    new_state = compile_github_query(state)

    assert new_state.compiled_query == "logistics language:Python stars:>=100"
    assert new_state.control.next_tool is ToolName.EXECUTE_GITHUB_SEARCH
    assert new_state.control.should_terminate is False


def test_compile_does_not_touch_structured_query_or_validation():
    state = _state_with_valid_query()
    new_state = compile_github_query(state)

    assert new_state.structured_query == state.structured_query
    assert new_state.validation == state.validation
    assert new_state.execution == state.execution


def test_compile_returns_new_state_object():
    state = _state_with_valid_query()
    new_state = compile_github_query(state)
    assert new_state is not state
