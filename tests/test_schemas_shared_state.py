"""Task 3.2 RED: SharedAgentState + sub-models (SCHEMAS.md §2-§6)."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from gh_search.schemas import (
    ExecutionStatus,
    IntentStatus,
    StructuredQuery,
    TerminateReason,
    ToolName,
)
from gh_search.schemas.shared_state import (
    Control,
    Execution,
    IntentionJudge,
    SharedAgentState,
    Validation,
)


def _initial_state() -> dict:
    return {
        "run_id": str(uuid.uuid4()),
        "turn_index": 1,
        "max_turns": 5,
        "user_query": "find python repos about logistics after 2023 with 100+ stars",
        "intention_judge": {
            "intent_status": "supported",
            "reason": None,
            "should_terminate": False,
        },
        "structured_query": None,
        "validation": {
            "is_valid": False,
            "errors": [],
            "missing_required_fields": [],
        },
        "compiled_query": None,
        "execution": {
            "status": "not_started",
            "response_status": None,
            "result_count": None,
        },
        "control": {
            "next_tool": "parse_query",
            "should_terminate": False,
            "terminate_reason": None,
        },
    }


def test_initial_state_parses():
    st = SharedAgentState.model_validate(_initial_state())
    assert st.turn_index == 1
    assert st.intention_judge.intent_status is IntentStatus.SUPPORTED
    assert st.execution.status is ExecutionStatus.NOT_STARTED
    assert st.control.next_tool is ToolName.PARSE_QUERY


def test_unknown_top_level_field_rejected():
    payload = _initial_state()
    payload["extra"] = "nope"
    with pytest.raises(ValidationError):
        SharedAgentState.model_validate(payload)


def test_missing_required_top_level_field_rejected():
    payload = _initial_state()
    del payload["execution"]
    with pytest.raises(ValidationError) as exc:
        SharedAgentState.model_validate(payload)
    assert "execution" in str(exc.value)


def test_structured_query_accepts_none():
    payload = _initial_state()
    st = SharedAgentState.model_validate(payload)
    assert st.structured_query is None


def test_structured_query_accepts_valid_object():
    payload = _initial_state()
    payload["structured_query"] = {
        "keywords": ["x"],
        "language": None,
        "created_after": None,
        "created_before": None,
        "min_stars": None,
        "max_stars": None,
        "sort": None,
        "order": None,
        "limit": 10,
    }
    st = SharedAgentState.model_validate(payload)
    assert isinstance(st.structured_query, StructuredQuery)


def test_intent_status_enum_rejected():
    payload = _initial_state()
    payload["intention_judge"]["intent_status"] = "maybe"
    with pytest.raises(ValidationError):
        SharedAgentState.model_validate(payload)


def test_validation_errors_must_be_list_of_str():
    payload = _initial_state()
    payload["validation"]["errors"] = [{"not": "a string"}]
    with pytest.raises(ValidationError):
        SharedAgentState.model_validate(payload)


def test_control_terminate_reason_enum():
    payload = _initial_state()
    payload["control"]["terminate_reason"] = "something_else"
    with pytest.raises(ValidationError):
        SharedAgentState.model_validate(payload)


def test_control_valid_terminate_reason():
    payload = _initial_state()
    payload["control"]["should_terminate"] = True
    payload["control"]["terminate_reason"] = "ambiguous_query"
    payload["control"]["next_tool"] = "finalize"
    st = SharedAgentState.model_validate(payload)
    assert st.control.terminate_reason is TerminateReason.AMBIGUOUS_QUERY


def test_state_immutable():
    # Per coding-style rules: domain models should be immutable. Mutating returns new copy.
    st = SharedAgentState.model_validate(_initial_state())
    with pytest.raises((ValidationError, TypeError)):
        st.turn_index = 2  # type: ignore[misc]


def test_sub_models_independently_importable():
    # DRY anchor: these sub-types are exported for logger/tools to reuse.
    assert Validation and Execution and Control and IntentionJudge
