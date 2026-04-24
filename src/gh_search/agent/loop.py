"""Bounded agent loop (MAIN_SPEC §4-§6, TOOLS.md §5)."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from gh_search.github import GitHubClient, Repository
from gh_search.llm import LLMJsonCall, LLMResponse
from gh_search.logger import SessionLogger
from gh_search.schemas import (
    Control,
    Execution,
    ExecutionStatus,
    IntentionJudge,
    IntentStatus,
    SharedAgentState,
    TerminateReason,
    ToolName,
    TurnLog,
    Validation,
)
from gh_search.tools import (
    compile_github_query,
    execute_github_search,
    intention_judge,
    parse_query,
    repair_query,
    validate_query,
)


def run_agent_loop(
    user_query: str,
    run_id: str,
    llm: LLMJsonCall,
    github: GitHubClient,
    max_turns: int = 5,
    results_sink: list[Repository] | None = None,
    session_logger: SessionLogger | None = None,
) -> SharedAgentState:
    if max_turns < 1:
        raise ValueError(f"max_turns must be >= 1, got {max_turns}")

    session_id = session_logger.session_id if session_logger is not None else run_id
    state = _initial_state(user_query=user_query, run_id=run_id, max_turns=max_turns)
    terminated = False

    for turn in range(1, max_turns + 1):
        if state.control.should_terminate or state.control.next_tool is None:
            terminated = True
            break

        tool = state.control.next_tool
        raw_box: list[str] = []
        recording_llm = _record_llm(llm, raw_box)

        started = time.perf_counter()
        new_state = _dispatch(
            state, tool, llm=recording_llm, github=github, results_sink=results_sink
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        new_state = new_state.model_copy(update={"turn_index": turn})

        raw_model_output = raw_box[-1] if raw_box else None

        if session_logger is not None:
            session_logger.append_turn(
                _turn_log(new_state, session_id, tool, latency_ms, raw_model_output)
            )
            session_logger.write_turn_artifact(
                turn_index=turn,
                tool_name=tool,
                payload=_artifact_payload(state, new_state, raw_model_output),
            )

        state = new_state

        if state.control.should_terminate:
            terminated = True
            break

    if not terminated:
        state = state.model_copy(
            update={
                "control": Control(
                    next_tool=ToolName.FINALIZE,
                    should_terminate=True,
                    terminate_reason=TerminateReason.MAX_TURNS_EXCEEDED,
                )
            }
        )

    return state


def _initial_state(user_query: str, run_id: str, max_turns: int) -> SharedAgentState:
    return SharedAgentState(
        run_id=run_id,
        turn_index=0,
        max_turns=max_turns,
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
            next_tool=ToolName.INTENTION_JUDGE,
            should_terminate=False,
            terminate_reason=None,
        ),
    )


def _dispatch(
    state: SharedAgentState,
    tool: ToolName,
    *,
    llm: LLMJsonCall,
    github: GitHubClient,
    results_sink: list[Repository] | None,
) -> SharedAgentState:
    if tool is ToolName.INTENTION_JUDGE:
        return intention_judge(state, llm=llm)
    if tool is ToolName.PARSE_QUERY:
        return parse_query(state, llm=llm)
    if tool is ToolName.VALIDATE_QUERY:
        return validate_query(state)
    if tool is ToolName.REPAIR_QUERY:
        return repair_query(state, llm=llm)
    if tool is ToolName.COMPILE_GITHUB_QUERY:
        return compile_github_query(state)
    if tool is ToolName.EXECUTE_GITHUB_SEARCH:
        return execute_github_search(state, github=github, results_sink=results_sink)
    if tool is ToolName.FINALIZE:
        return state.model_copy(
            update={
                "control": state.control.model_copy(
                    update={"should_terminate": True, "next_tool": None}
                )
            }
        )
    raise ValueError(f"unknown tool: {tool}")


def _turn_log(
    state: SharedAgentState,
    session_id: str,
    tool: ToolName,
    latency_ms: int,
    raw_model_output: str | None,
) -> TurnLog:
    return TurnLog(
        session_id=session_id,
        run_id=state.run_id,
        turn_index=state.turn_index,
        tool_name=tool,
        input_query=state.user_query,
        intention_status=state.intention_judge.intent_status,
        raw_model_output=raw_model_output,
        parsed_structured_query=state.structured_query,
        validation_result=state.validation.is_valid if tool is ToolName.VALIDATE_QUERY else None,
        validation_errors=list(state.validation.errors),
        compiled_query=state.compiled_query,
        response_status=state.execution.response_status,
        final_outcome=None,
        next_action=state.control.next_tool,
        latency_ms=latency_ms,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
    )


def _record_llm(llm: LLMJsonCall, raw_box: list[str]) -> LLMJsonCall:
    def wrapped(system_prompt: str, user_message: str, response_schema: dict) -> LLMResponse:
        response = llm(system_prompt, user_message, response_schema)
        raw_box.append(response.raw_text)
        return response

    # Preserve provider/model metadata so tools that introspect
    # `llm.model_name` (for per-model prompt composition) still see the
    # original adapter's identity through this passthrough.
    for attr in ("model_name", "provider_name"):
        if hasattr(llm, attr):
            setattr(wrapped, attr, getattr(llm, attr))
    return wrapped


def _artifact_payload(
    prev: SharedAgentState, new: SharedAgentState, raw_model_output: str | None
) -> dict:
    prev_dump = prev.model_dump(mode="json")
    new_dump = new.model_dump(mode="json")
    diff = {k: new_dump[k] for k in new_dump if new_dump[k] != prev_dump.get(k)}
    return {
        "input_state": prev_dump,
        "raw_model_output": raw_model_output,
        "output_state": new_dump,
        "state_diff": diff,
    }


