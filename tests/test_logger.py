"""Task 3.5 RED: SessionLogger (LOGGING.md §2, §5, §7).

Writes the canonical session tree:
  artifacts/logs/sessions/{session_id}/
    run.json
    turns.jsonl
    final_state.json
    artifacts/turn_XX_<tool>.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from gh_search.logger import SessionLogger
from gh_search.schemas import (
    Control,
    Execution,
    ExecutionStatus,
    FinalState,
    IntentionJudge,
    IntentStatus,
    RunLog,
    SharedAgentState,
    ToolName,
    TurnLog,
    Validation,
)


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _shared_state(run_id="run_1"):
    return SharedAgentState(
        run_id=run_id,
        turn_index=1,
        max_turns=5,
        user_query="python logistics",
        intention_judge=IntentionJudge(
            intent_status=IntentStatus.SUPPORTED, reason=None, should_terminate=False
        ),
        structured_query=None,
        validation=Validation(is_valid=False, errors=[], missing_required_fields=[]),
        compiled_query=None,
        execution=Execution(status=ExecutionStatus.NOT_STARTED, response_status=None, result_count=None),
        control=Control(next_tool=ToolName.PARSE_QUERY, should_terminate=False, terminate_reason=None),
    )


def _turn_log(session_id="sess_1", run_id="run_1", turn_index=1, tool=ToolName.INTENTION_JUDGE):
    return TurnLog(
        session_id=session_id,
        run_id=run_id,
        turn_index=turn_index,
        tool_name=tool,
        input_query="python logistics",
        intention_status=IntentStatus.SUPPORTED,
        raw_model_output='{"intent_status":"supported"}',
        parsed_structured_query=None,
        validation_result=None,
        validation_errors=[],
        keyword_normalization_trace=None,
        compiled_query=None,
        response_status=None,
        final_outcome=None,
        next_action=ToolName.PARSE_QUERY,
        latency_ms=12,
        created_at=_now(),
    )


def _run_log(session_id="sess_1", run_id="run_1"):
    return RunLog(
        session_id=session_id,
        run_id=run_id,
        run_type="cli",
        user_query="python logistics",
        model_name="gpt-4.1-mini",
        provider_name="openai",
        prompt_version="v1",
        keyword_rules_version="kw-rules-v1",
        final_outcome="success",
        terminate_reason=None,
        started_at=_now(),
        ended_at=_now(),
        log_version="1",
    )


def test_init_creates_session_directory(tmp_path: Path):
    logger = SessionLogger(session_id="sess_1", log_root=tmp_path)
    session_dir = tmp_path / "sessions" / "sess_1"
    assert session_dir.is_dir()
    assert (session_dir / "artifacts").is_dir()
    assert logger.session_dir == session_dir


def test_append_turn_creates_jsonl_line(tmp_path: Path):
    logger = SessionLogger(session_id="sess_1", log_root=tmp_path)
    logger.append_turn(_turn_log())

    jsonl = (tmp_path / "sessions" / "sess_1" / "turns.jsonl").read_text().strip().splitlines()
    assert len(jsonl) == 1
    decoded = json.loads(jsonl[0])
    assert decoded["session_id"] == "sess_1"
    assert decoded["tool_name"] == "intention_judge"


def test_append_turn_multiple_lines_ordered(tmp_path: Path):
    logger = SessionLogger(session_id="sess_1", log_root=tmp_path)
    logger.append_turn(_turn_log(turn_index=1, tool=ToolName.INTENTION_JUDGE))
    logger.append_turn(_turn_log(turn_index=2, tool=ToolName.PARSE_QUERY))
    logger.append_turn(_turn_log(turn_index=3, tool=ToolName.VALIDATE_QUERY))

    lines = (tmp_path / "sessions" / "sess_1" / "turns.jsonl").read_text().strip().splitlines()
    tools = [json.loads(line)["tool_name"] for line in lines]
    assert tools == ["intention_judge", "parse_query", "validate_query"]


def test_turn_artifact_written_with_canonical_name(tmp_path: Path):
    logger = SessionLogger(session_id="sess_1", log_root=tmp_path)
    logger.write_turn_artifact(
        turn_index=2,
        tool_name=ToolName.PARSE_QUERY,
        payload={"raw_model_output": "x", "state_diff": {}},
    )

    artifact = tmp_path / "sessions" / "sess_1" / "artifacts" / "turn_02_parse_query.json"
    assert artifact.exists()
    data = json.loads(artifact.read_text())
    assert data["raw_model_output"] == "x"


def test_finalize_writes_run_and_final_state(tmp_path: Path):
    logger = SessionLogger(session_id="sess_1", log_root=tmp_path)
    final_state = FinalState(
        session_id="sess_1",
        run_id="run_1",
        state_type="final",
        turn_index=3,
        state_payload=_shared_state(),
        created_at=_now(),
    )
    logger.finalize(run_log=_run_log(), final_state=final_state)

    session_dir = tmp_path / "sessions" / "sess_1"
    run_json = json.loads((session_dir / "run.json").read_text())
    assert run_json["session_id"] == "sess_1"
    assert run_json["run_id"] == "run_1"

    final_json = json.loads((session_dir / "final_state.json").read_text())
    assert final_json["state_type"] == "final"
    assert final_json["state_payload"]["run_id"] == "run_1"


def test_turns_jsonl_replayable_into_turn_logs(tmp_path: Path):
    logger = SessionLogger(session_id="sess_1", log_root=tmp_path)
    logger.append_turn(_turn_log(turn_index=1))
    logger.append_turn(_turn_log(turn_index=2, tool=ToolName.PARSE_QUERY))

    replayed = [
        TurnLog.model_validate_json(line)
        for line in (tmp_path / "sessions" / "sess_1" / "turns.jsonl").read_text().splitlines()
    ]
    assert [t.turn_index for t in replayed] == [1, 2]


def test_session_ids_consistent_across_files(tmp_path: Path):
    logger = SessionLogger(session_id="sess_abc", log_root=tmp_path)
    logger.append_turn(_turn_log(session_id="sess_abc", run_id="run_abc"))
    final_state = FinalState(
        session_id="sess_abc",
        run_id="run_abc",
        state_type="final",
        turn_index=1,
        state_payload=_shared_state(run_id="run_abc"),
        created_at=_now(),
    )
    logger.finalize(
        run_log=_run_log(session_id="sess_abc", run_id="run_abc"),
        final_state=final_state,
    )

    session_dir = tmp_path / "sessions" / "sess_abc"
    run = json.loads((session_dir / "run.json").read_text())
    turn = json.loads((session_dir / "turns.jsonl").read_text().strip().splitlines()[0])
    fs = json.loads((session_dir / "final_state.json").read_text())

    assert run["session_id"] == turn["session_id"] == fs["session_id"] == "sess_abc"
    assert run["run_id"] == turn["run_id"] == fs["run_id"] == "run_abc"


def test_append_turn_rejects_mismatched_session(tmp_path: Path):
    import pytest

    logger = SessionLogger(session_id="sess_1", log_root=tmp_path)
    with pytest.raises(ValueError):
        logger.append_turn(_turn_log(session_id="sess_different"))
