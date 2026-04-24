"""Task 3.6 RED: intention_judge tool (TOOLS.md §3 intention_judge, §7)."""
from __future__ import annotations

import pytest

from gh_search.schemas import (
    Control,
    Execution,
    ExecutionStatus,
    IntentStatus,
    IntentionJudge,
    SharedAgentState,
    TerminateReason,
    ToolName,
    Validation,
)
from gh_search.llm import LLMResponse
from gh_search.tools import intention_judge


def _fresh_state(user_query="find python repos about logistics") -> SharedAgentState:
    return SharedAgentState(
        run_id="r1",
        turn_index=1,
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
            next_tool=ToolName.INTENTION_JUDGE, should_terminate=False, terminate_reason=None
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


def test_supported_intent_routes_to_parse_query():
    llm, _ = _stub_llm(
        {"intent_status": "supported", "reason": None, "should_terminate": False}
    )
    state = _fresh_state()
    new_state = intention_judge(state, llm=llm)

    assert new_state.intention_judge.intent_status is IntentStatus.SUPPORTED
    assert new_state.intention_judge.should_terminate is False
    assert new_state.control.next_tool is ToolName.PARSE_QUERY
    assert new_state.control.should_terminate is False
    assert new_state.control.terminate_reason is None


def test_unsupported_intent_terminates_with_unsupported_intent():
    llm, _ = _stub_llm(
        {
            "intent_status": "unsupported",
            "reason": "asks about Twitter, not GitHub repos",
            "should_terminate": True,
        }
    )
    state = _fresh_state("find trending tweets about AI")
    new_state = intention_judge(state, llm=llm)

    assert new_state.intention_judge.intent_status is IntentStatus.UNSUPPORTED
    assert new_state.intention_judge.reason == "asks about Twitter, not GitHub repos"
    assert new_state.control.next_tool is ToolName.FINALIZE
    assert new_state.control.should_terminate is True
    assert new_state.control.terminate_reason is TerminateReason.UNSUPPORTED_INTENT


def test_ambiguous_intent_terminates_with_ambiguous_query():
    llm, _ = _stub_llm(
        {
            "intent_status": "ambiguous",
            "reason": "no constraint provided",
            "should_terminate": True,
        }
    )
    state = _fresh_state("find good repos")
    new_state = intention_judge(state, llm=llm)

    assert new_state.intention_judge.intent_status is IntentStatus.AMBIGUOUS
    assert new_state.control.next_tool is ToolName.FINALIZE
    assert new_state.control.should_terminate is True
    assert new_state.control.terminate_reason is TerminateReason.AMBIGUOUS_QUERY


def test_user_query_passed_as_user_message():
    llm, captured = _stub_llm(
        {"intent_status": "supported", "reason": None, "should_terminate": False}
    )
    state = _fresh_state("rust web frameworks over 500 stars")
    intention_judge(state, llm=llm)

    assert "rust web frameworks over 500 stars" in captured["user_message"]


def test_does_not_mutate_structured_query_or_execution():
    llm, _ = _stub_llm(
        {"intent_status": "supported", "reason": None, "should_terminate": False}
    )
    state = _fresh_state()
    new_state = intention_judge(state, llm=llm)

    assert new_state.structured_query is state.structured_query
    assert new_state.validation == state.validation
    assert new_state.execution == state.execution


def test_malformed_llm_response_defaults_to_ambiguous_termination():
    # If the LLM returns something that doesn't validate, the tool must fail-safe
    # to avoid letting a malformed intent leak downstream (AGENTS.md §2 "no
    # over-engineering" applies: simplest safe default is treat as ambiguous).
    llm, _ = _stub_llm({"not_a_valid": "response"})
    state = _fresh_state()
    new_state = intention_judge(state, llm=llm)

    assert new_state.intention_judge.intent_status is IntentStatus.AMBIGUOUS
    assert new_state.control.should_terminate is True
    assert new_state.control.terminate_reason is TerminateReason.AMBIGUOUS_QUERY


# ITER3_INTENTION_JUDGE_TUNING_SPEC §8.1: lock the 7 dataset-aligned queries
# to `supported` so a stubbed-supported LLM response routes them into
# parse_query. These are contract tests for control flow — prompt-vs-LLM
# judgment is validated out-of-band via `gh-search smoke` (§8.2, §9.2).
ITER3_SUPPORTED_QUERIES = [
    ("q004", "any good golang cli tools out there?"),
    ("q009", "recommend some vue 3 admin dashboard templates"),
    ("q019", "good repos for learning programming"),
    ("q020", "popular stuff on github"),
    ("q021", "show me some cool swift repos not too old but not too new"),
    ("q022", "I want repos about apple"),
    ("q030", "找一些 star 超過 500 但少於 100 的 rust 專案"),
]


@pytest.mark.parametrize("qid,query", ITER3_SUPPORTED_QUERIES, ids=[q[0] for q in ITER3_SUPPORTED_QUERIES])
def test_iter3_supported_query_routes_to_parse_query(qid: str, query: str):
    llm, _ = _stub_llm(
        {"intent_status": "supported", "reason": None, "should_terminate": False}
    )
    state = _fresh_state(query)
    new_state = intention_judge(state, llm=llm)

    assert new_state.intention_judge.intent_status is IntentStatus.SUPPORTED
    assert new_state.intention_judge.should_terminate is False
    assert new_state.control.next_tool is ToolName.PARSE_QUERY
    assert new_state.control.should_terminate is False
    assert new_state.control.terminate_reason is None


# ITER3_INTENTION_JUDGE_TUNING_SPEC §8.3: off-domain negative set must still
# terminate even after the gate is relaxed. Guards against over-recovery.
ITER3_UNSUPPORTED_QUERIES = [
    ("prs_in_repo", "show me PRs in repo X"),
    ("users_named", "find users named alice"),
    ("code_snippets", "give me code snippets for redis retry logic"),
]


@pytest.mark.parametrize(
    "case_id,query",
    ITER3_UNSUPPORTED_QUERIES,
    ids=[c[0] for c in ITER3_UNSUPPORTED_QUERIES],
)
def test_iter3_off_domain_query_terminates(case_id: str, query: str):
    llm, _ = _stub_llm(
        {
            "intent_status": "unsupported",
            "reason": "target is not a repository search",
            "should_terminate": True,
        }
    )
    state = _fresh_state(query)
    new_state = intention_judge(state, llm=llm)

    assert new_state.intention_judge.intent_status is IntentStatus.UNSUPPORTED
    assert new_state.control.next_tool is ToolName.FINALIZE
    assert new_state.control.should_terminate is True
    assert new_state.control.terminate_reason is TerminateReason.UNSUPPORTED_INTENT
