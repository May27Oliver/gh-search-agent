"""Task 3.7 RED: repair_query tool (TOOLS.md §3 repair_query)."""
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
from gh_search.llm import LLMResponse
from gh_search.tools import repair_query


def _invalid_sq():
    return StructuredQuery.model_validate(
        {
            "keywords": ["x"],
            "language": None,
            "created_after": None,
            "created_before": None,
            "min_stars": 500,
            "max_stars": 100,  # invalid: min > max
            "sort": None,
            "order": None,
            "limit": 10,
        }
    )


def _state_after_validate():
    return SharedAgentState(
        run_id="r1",
        turn_index=3,
        max_turns=5,
        user_query="repos with stars between 100 and 500",
        intention_judge=IntentionJudge(
            intent_status=IntentStatus.SUPPORTED, reason=None, should_terminate=False
        ),
        structured_query=_invalid_sq(),
        validation=Validation(
            is_valid=False,
            errors=["min_stars (500) must be <= max_stars (100)"],
            missing_required_fields=[],
        ),
        compiled_query=None,
        execution=Execution(
            status=ExecutionStatus.NOT_STARTED, response_status=None, result_count=None
        ),
        control=Control(
            next_tool=ToolName.REPAIR_QUERY, should_terminate=False, terminate_reason=None
        ),
    )


_FIXED_LLM_OUTPUT = {
    "keywords": ["x"],
    "language": None,
    "created_after": None,
    "created_before": None,
    "min_stars": 100,
    "max_stars": 500,
    "sort": None,
    "order": None,
    "limit": 10,
}


def _stub_llm(response: dict):
    import json

    captured: dict = {}

    def fn(system_prompt: str, user_message: str, response_schema: dict) -> LLMResponse:
        captured["system_prompt"] = system_prompt
        captured["user_message"] = user_message
        captured["response_schema"] = response_schema
        return LLMResponse(raw_text=json.dumps(response), parsed=response)

    return fn, captured


def test_repair_updates_structured_query_and_routes_back_to_validate():
    llm, _ = _stub_llm(_FIXED_LLM_OUTPUT)
    new_state = repair_query(_state_after_validate(), llm=llm)

    assert new_state.structured_query is not None
    assert new_state.structured_query.min_stars == 100
    assert new_state.structured_query.max_stars == 500
    assert new_state.control.next_tool is ToolName.VALIDATE_QUERY
    assert new_state.control.should_terminate is False


def test_repair_prompts_include_user_query_prior_query_and_errors():
    llm, captured = _stub_llm(_FIXED_LLM_OUTPUT)
    repair_query(_state_after_validate(), llm=llm)

    msg = captured["user_message"]
    assert "repos with stars between 100 and 500" in msg
    # Prior query represented somehow (as JSON)
    assert "500" in msg and "100" in msg
    # Validation errors relayed
    assert "min_stars" in msg


def test_repair_malformed_output_leaves_structured_query_none():
    llm, _ = _stub_llm({"not": "valid"})
    new_state = repair_query(_state_after_validate(), llm=llm)

    assert new_state.structured_query is None
    assert new_state.control.next_tool is ToolName.VALIDATE_QUERY


def test_repair_does_not_modify_validation_or_execution():
    llm, _ = _stub_llm(_FIXED_LLM_OUTPUT)
    state = _state_after_validate()
    new_state = repair_query(state, llm=llm)

    # validation must remain unchanged until validate_query re-runs
    assert new_state.validation == state.validation
    assert new_state.execution == state.execution
    assert new_state.compiled_query is None
