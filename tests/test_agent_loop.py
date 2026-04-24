"""Task 3.7 RED: bounded agent loop (MAIN_SPEC §4-§6, TOOLS.md §5)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from gh_search.agent import run_agent_loop
from gh_search.github import Repository
from gh_search.llm import LLMResponse
from gh_search.schemas import (
    ExecutionStatus,
    IntentStatus,
    TerminateReason,
    ToolName,
)


_VALID_PARSE_OUTPUT = {
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


def _scripted_llm(*responses: dict):
    """LLM stub that returns responses in sequence, one per call."""
    import json

    calls = iter(responses)

    def fn(system_prompt: str, user_message: str, response_schema: dict) -> LLMResponse:
        payload = next(calls)
        return LLMResponse(raw_text=json.dumps(payload), parsed=payload)

    return fn


def _fake_github(repos):
    g = MagicMock()
    g.search_repositories.return_value = repos
    return g


def test_supported_normal_query_runs_to_success():
    llm = _scripted_llm(
        {"intent_status": "supported", "reason": None, "should_terminate": False},
        _VALID_PARSE_OUTPUT,
    )
    github = _fake_github(
        [Repository(name="a/b", url="https://github.com/a/b", stars=200, language="Python")]
    )

    state = run_agent_loop(
        user_query="python logistics 100+ stars",
        run_id="r1",
        llm=llm,
        github=github,
        max_turns=5,
    )

    assert state.intention_judge.intent_status is IntentStatus.SUPPORTED
    assert state.structured_query is not None
    assert state.validation.is_valid is True
    assert state.compiled_query == "logistics language:Python stars:>=100"
    assert state.execution.status is ExecutionStatus.SUCCESS
    assert state.execution.result_count == 1
    assert state.control.should_terminate is True
    assert state.control.terminate_reason is None


def test_unsupported_intent_terminates_after_one_turn():
    llm = _scripted_llm(
        {
            "intent_status": "unsupported",
            "reason": "asks about tweets",
            "should_terminate": True,
        }
    )
    github = _fake_github([])

    state = run_agent_loop(
        user_query="find trending tweets about AI",
        run_id="r2",
        llm=llm,
        github=github,
        max_turns=5,
    )

    assert state.intention_judge.intent_status is IntentStatus.UNSUPPORTED
    assert state.control.should_terminate is True
    assert state.control.terminate_reason is TerminateReason.UNSUPPORTED_INTENT
    assert state.execution.status is ExecutionStatus.NOT_STARTED
    assert github.search_repositories.call_count == 0


def test_ambiguous_intent_terminates_after_one_turn():
    llm = _scripted_llm(
        {"intent_status": "ambiguous", "reason": "too vague", "should_terminate": True}
    )
    state = run_agent_loop(
        user_query="find good repos",
        run_id="r3",
        llm=llm,
        github=_fake_github([]),
        max_turns=5,
    )

    assert state.control.terminate_reason is TerminateReason.AMBIGUOUS_QUERY


def test_empty_result_set_terminates_with_no_results():
    llm = _scripted_llm(
        {"intent_status": "supported", "reason": None, "should_terminate": False},
        _VALID_PARSE_OUTPUT,
    )
    state = run_agent_loop(
        user_query="obscure niche topic",
        run_id="r4",
        llm=llm,
        github=_fake_github([]),
        max_turns=5,
    )

    assert state.execution.status is ExecutionStatus.NO_RESULTS
    assert state.control.should_terminate is True


def test_invalid_parse_triggers_repair_and_recovers():
    # parse returns an empty query; validator rejects; repair fills in, validator
    # passes, compile + execute succeed.
    empty = {**_VALID_PARSE_OUTPUT, "keywords": [], "language": None, "min_stars": None}
    llm = _scripted_llm(
        {"intent_status": "supported", "reason": None, "should_terminate": False},
        empty,
        _VALID_PARSE_OUTPUT,  # repair fixes
    )
    github = _fake_github(
        [Repository(name="a/b", url="https://github.com/a/b", stars=200, language="Python")]
    )

    state = run_agent_loop(
        user_query="python logistics 100+ stars",
        run_id="r5",
        llm=llm,
        github=github,
        max_turns=8,
    )

    assert state.execution.status is ExecutionStatus.SUCCESS
    assert state.control.should_terminate is True


def test_max_turns_exceeded_sets_terminate_reason():
    # LLM keeps returning empty queries; validation keeps failing; we eventually
    # hit max_turns.
    empty = {**_VALID_PARSE_OUTPUT, "keywords": [], "language": None, "min_stars": None}
    # Enough invalid responses to exhaust the loop.
    llm = _scripted_llm(
        {"intent_status": "supported", "reason": None, "should_terminate": False},
        empty,  # parse
        empty,  # repair #1
        empty,  # repair #2
        empty,  # repair #3 (unused but available)
    )
    state = run_agent_loop(
        user_query="blah",
        run_id="r6",
        llm=llm,
        github=_fake_github([]),
        max_turns=5,
    )

    assert state.control.should_terminate is True
    assert state.control.terminate_reason is TerminateReason.MAX_TURNS_EXCEEDED


def test_results_sink_collects_repositories():
    llm = _scripted_llm(
        {"intent_status": "supported", "reason": None, "should_terminate": False},
        _VALID_PARSE_OUTPUT,
    )
    repo = Repository(name="a/b", url="https://github.com/a/b", stars=200, language="Python")
    sink: list[Repository] = []

    run_agent_loop(
        user_query="...",
        run_id="r7",
        llm=llm,
        github=_fake_github([repo]),
        max_turns=5,
        results_sink=sink,
    )

    assert sink == [repo]


def test_turn_logs_include_raw_model_output_for_llm_tools(tmp_path):
    from gh_search.logger import SessionLogger
    import json as _json

    llm = _scripted_llm(
        {"intent_status": "supported", "reason": None, "should_terminate": False},
        _VALID_PARSE_OUTPUT,
    )
    logger = SessionLogger(session_id="sess_raw", log_root=tmp_path)

    run_agent_loop(
        user_query="python logistics 100+ stars",
        run_id="r_raw",
        llm=llm,
        github=_fake_github(
            [Repository(name="a/b", url="https://github.com/a/b", stars=1, language="Python")]
        ),
        max_turns=5,
        session_logger=logger,
    )

    lines = (
        (tmp_path / "sessions" / "sess_raw" / "turns.jsonl").read_text().strip().splitlines()
    )
    by_tool = {_json.loads(line)["tool_name"]: _json.loads(line) for line in lines}

    # intention_judge and parse_query called the LLM — raw must be captured
    assert by_tool["intention_judge"]["raw_model_output"] is not None
    assert "supported" in by_tool["intention_judge"]["raw_model_output"]
    assert by_tool["parse_query"]["raw_model_output"] is not None
    assert "logistics" in by_tool["parse_query"]["raw_model_output"]

    # Pure tools (no LLM) leave raw_model_output as null
    assert by_tool["validate_query"]["raw_model_output"] is None
    assert by_tool["compile_github_query"]["raw_model_output"] is None


def test_turn_artifacts_written_per_turn(tmp_path):
    from gh_search.logger import SessionLogger
    import json as _json

    llm = _scripted_llm(
        {"intent_status": "supported", "reason": None, "should_terminate": False},
        _VALID_PARSE_OUTPUT,
    )
    logger = SessionLogger(session_id="sess_art", log_root=tmp_path)

    run_agent_loop(
        user_query="x",
        run_id="r_art",
        llm=llm,
        github=_fake_github([]),
        max_turns=5,
        session_logger=logger,
    )

    art_dir = tmp_path / "sessions" / "sess_art" / "artifacts"
    assert (art_dir / "turn_01_intention_judge.json").exists()
    assert (art_dir / "turn_02_parse_query.json").exists()

    # Artifact payload matches LOGGING.md §6: input_state, raw_model_output,
    # output_state, state_diff.
    payload = _json.loads((art_dir / "turn_02_parse_query.json").read_text())
    assert "input_state" in payload
    assert "output_state" in payload
    assert "state_diff" in payload
    assert "raw_model_output" in payload
    assert payload["raw_model_output"] is not None
    # state_diff must flag structured_query as changed after parse_query
    assert "structured_query" in payload["state_diff"]


def test_turn_logger_appends_one_line_per_turn(tmp_path):
    from gh_search.logger import SessionLogger

    llm = _scripted_llm(
        {"intent_status": "supported", "reason": None, "should_terminate": False},
        _VALID_PARSE_OUTPUT,
    )
    logger = SessionLogger(session_id="sess_1", log_root=tmp_path)

    state = run_agent_loop(
        user_query="python logistics 100+ stars",
        run_id="r8",
        llm=llm,
        github=_fake_github(
            [Repository(name="a/b", url="https://github.com/a/b", stars=200, language="Python")]
        ),
        max_turns=5,
        session_logger=logger,
    )

    lines = (
        (tmp_path / "sessions" / "sess_1" / "turns.jsonl").read_text().strip().splitlines()
    )
    # intention_judge, parse_query, validate_query, compile_github_query, execute_github_search
    assert len(lines) == 5
    assert state.control.should_terminate is True


def test_turn_count_never_exceeds_max_turns():
    llm = _scripted_llm(
        {"intent_status": "supported", "reason": None, "should_terminate": False},
        _VALID_PARSE_OUTPUT,
    )
    state = run_agent_loop(
        user_query="...",
        run_id="r9",
        llm=llm,
        github=_fake_github([]),
        max_turns=5,
    )
    assert state.turn_index <= 5


def test_invalid_max_turns_rejected():
    with pytest.raises(ValueError):
        run_agent_loop(
            user_query="x",
            run_id="r10",
            llm=_scripted_llm(),
            github=_fake_github([]),
            max_turns=0,
        )


# ITER5_DATE_TUNING_SPEC §8.1.1: run_agent_loop must forward `today` kwarg
# to parse_query so eval path can pin DATASET_TODAY_ANCHOR.
def test_run_agent_loop_forwards_today_to_parse_query(monkeypatch):
    from datetime import date

    captured: dict = {}

    def fake_parse_query(state, *, llm, today=None):
        captured["today"] = today
        # route to validate_query so loop exits cleanly
        from gh_search.schemas import Control, ToolName

        return state.model_copy(
            update={
                "control": Control(
                    next_tool=ToolName.VALIDATE_QUERY,
                    should_terminate=True,
                    terminate_reason=None,
                )
            }
        )

    monkeypatch.setattr("gh_search.agent.loop.parse_query", fake_parse_query)

    llm = _scripted_llm(
        {"intent_status": "supported", "reason": None, "should_terminate": False},
    )
    run_agent_loop(
        user_query="find python repos from last year",
        run_id="r_today",
        llm=llm,
        github=_fake_github([]),
        max_turns=5,
        today=date(2026, 4, 23),
    )

    assert captured["today"] == date(2026, 4, 23)


def test_run_agent_loop_today_defaults_to_none_when_not_provided(monkeypatch):
    captured: dict = {}

    def fake_parse_query(state, *, llm, today=None):
        captured["today"] = today
        from gh_search.schemas import Control, ToolName

        return state.model_copy(
            update={
                "control": Control(
                    next_tool=ToolName.VALIDATE_QUERY,
                    should_terminate=True,
                    terminate_reason=None,
                )
            }
        )

    monkeypatch.setattr("gh_search.agent.loop.parse_query", fake_parse_query)

    llm = _scripted_llm(
        {"intent_status": "supported", "reason": None, "should_terminate": False},
    )
    run_agent_loop(
        user_query="anything",
        run_id="r_no_today",
        llm=llm,
        github=_fake_github([]),
        max_turns=5,
    )

    assert captured["today"] is None
