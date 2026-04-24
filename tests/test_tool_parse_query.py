"""Task 3.6 RED: parse_query tool (TOOLS.md §3 parse_query)."""
from __future__ import annotations

from gh_search.schemas import (
    Control,
    Execution,
    ExecutionStatus,
    IntentStatus,
    IntentionJudge,
    SharedAgentState,
    ToolName,
    Validation,
)
from gh_search.llm import LLMResponse
from gh_search.tools import parse_query


def _post_intent_state(user_query="python logistics after 2024 with 100+ stars"):
    return SharedAgentState(
        run_id="r1",
        turn_index=2,
        max_turns=5,
        user_query=user_query,
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
            next_tool=ToolName.PARSE_QUERY, should_terminate=False, terminate_reason=None
        ),
    )


def _stub_llm(response: dict):
    import json

    captured: dict = {}

    def fn(system_prompt: str, user_message: str, response_schema: dict) -> LLMResponse:
        captured["system_prompt"] = system_prompt
        captured["user_message"] = user_message
        captured["response_schema"] = response_schema
        return LLMResponse(raw_text=json.dumps(response), parsed=response)

    return fn, captured


_VALID_LLM_OUTPUT = {
    "keywords": ["logistics"],
    "language": "Python",
    "created_after": "2024-01-01",
    "created_before": None,
    "min_stars": 100,
    "max_stars": None,
    "sort": "stars",
    "order": "desc",
    "limit": 10,
}


def test_valid_llm_output_populates_structured_query_and_routes_to_validate():
    llm, _ = _stub_llm(_VALID_LLM_OUTPUT)
    state = _post_intent_state()

    new_state = parse_query(state, llm=llm)

    assert new_state.structured_query is not None
    assert new_state.structured_query.keywords == ["logistics"]
    assert new_state.structured_query.language == "Python"
    assert new_state.structured_query.min_stars == 100
    assert new_state.control.next_tool is ToolName.VALIDATE_QUERY
    assert new_state.control.should_terminate is False


def test_user_query_passed_as_user_message():
    llm, captured = _stub_llm(_VALID_LLM_OUTPUT)
    state = _post_intent_state("rust web frameworks over 500 stars")

    parse_query(state, llm=llm)

    assert "rust web frameworks over 500 stars" in captured["user_message"]


def test_does_not_mutate_validation_execution_or_compiled_query():
    llm, _ = _stub_llm(_VALID_LLM_OUTPUT)
    state = _post_intent_state()

    new_state = parse_query(state, llm=llm)

    assert new_state.validation == state.validation
    assert new_state.execution == state.execution
    assert new_state.compiled_query is None


def test_malformed_llm_output_leaves_structured_query_none_and_routes_to_validate():
    # parse cannot set terminate itself (TOOLS.md §3 parse_query contract);
    # validate_query is responsible for terminating on missing structured_query.
    llm, _ = _stub_llm({"not": "a structured query"})
    state = _post_intent_state()

    new_state = parse_query(state, llm=llm)

    assert new_state.structured_query is None
    assert new_state.control.next_tool is ToolName.VALIDATE_QUERY


def test_llm_response_schema_matches_structured_query_shape():
    llm, captured = _stub_llm(_VALID_LLM_OUTPUT)
    state = _post_intent_state()
    parse_query(state, llm=llm)

    schema = captured["response_schema"]
    assert schema["type"] == "object"
    required = set(schema.get("required", []))
    assert {
        "keywords",
        "language",
        "created_after",
        "created_before",
        "min_stars",
        "max_stars",
        "sort",
        "order",
        "limit",
    }.issubset(required)
