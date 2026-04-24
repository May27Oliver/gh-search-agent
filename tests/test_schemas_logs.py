"""Task 3.2 RED: RunLog / TurnLog / FinalState / EvalResult (SCHEMAS.md §7-§10)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from gh_search.schemas.eval import EvalResult
from gh_search.schemas.logs import FinalState, RunLog, TurnLog
from gh_search.schemas.shared_state import SharedAgentState


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _run_log_payload(**overrides):
    base = {
        "session_id": "sess_abc",
        "run_id": "run_123",
        "run_type": "cli",
        "user_query": "python logistics",
        "model_name": "gpt-4.1-mini",
        "provider_name": "openai",
        "prompt_version": "v1",
        "keyword_rules_version": "kw-rules-v1",
        "final_outcome": "success",
        "terminate_reason": None,
        "started_at": _now(),
        "ended_at": _now(),
        "log_version": "1",
    }
    base.update(overrides)
    return base


def test_run_log_parses():
    RunLog.model_validate(_run_log_payload())


@pytest.mark.parametrize(
    "missing_field",
    [
        "session_id",
        "run_id",
        "run_type",
        "user_query",
        "model_name",
        "provider_name",
        "prompt_version",
        "keyword_rules_version",
        "final_outcome",
        "started_at",
        "ended_at",
        "log_version",
    ],
)
def test_run_log_missing_required(missing_field):
    payload = _run_log_payload()
    del payload[missing_field]
    with pytest.raises(ValidationError) as exc:
        RunLog.model_validate(payload)
    assert missing_field in str(exc.value)


def test_run_log_rejects_unknown_field():
    payload = _run_log_payload()
    payload["unknown"] = "x"
    with pytest.raises(ValidationError):
        RunLog.model_validate(payload)


def _turn_log_payload(**overrides):
    base = {
        "session_id": "sess_abc",
        "run_id": "run_123",
        "turn_index": 1,
        "tool_name": "parse_query",
        "input_query": "python logistics",
        "intention_status": "supported",
        "raw_model_output": '{"keywords":["logistics"]}',
        "parsed_structured_query": None,
        "validation_result": None,
        "validation_errors": [],
        "keyword_normalization_trace": None,
        "compiled_query": None,
        "response_status": None,
        "final_outcome": None,
        "next_action": "validate_query",
        "latency_ms": 123,
        "created_at": _now(),
    }
    base.update(overrides)
    return base


def test_turn_log_parses():
    TurnLog.model_validate(_turn_log_payload())


def test_turn_log_rejects_invalid_tool_name():
    with pytest.raises(ValidationError):
        TurnLog.model_validate(_turn_log_payload(tool_name="do_something_weird"))


def test_turn_log_rejects_negative_latency():
    with pytest.raises(ValidationError):
        TurnLog.model_validate(_turn_log_payload(latency_ms=-1))


def test_final_state_wraps_shared_state():
    state_payload = {
        "run_id": "run_123",
        "turn_index": 3,
        "max_turns": 5,
        "user_query": "x",
        "intention_judge": {
            "intent_status": "supported",
            "reason": None,
            "should_terminate": False,
        },
        "structured_query": None,
        "validation": {"is_valid": False, "errors": [], "missing_required_fields": []},
        "compiled_query": None,
        "execution": {"status": "not_started", "response_status": None, "result_count": None},
        "control": {"next_tool": "finalize", "should_terminate": True, "terminate_reason": None},
    }
    payload = {
        "session_id": "sess_abc",
        "run_id": "run_123",
        "state_type": "final",
        "turn_index": 3,
        "state_payload": state_payload,
        "created_at": _now(),
    }
    final = FinalState.model_validate(payload)
    assert isinstance(final.state_payload, SharedAgentState)


def test_final_state_rejects_wrong_state_type():
    payload = {
        "session_id": "sess_abc",
        "run_id": "run_123",
        "state_type": "interim",
        "turn_index": 3,
        "state_payload": {},
        "created_at": _now(),
    }
    with pytest.raises(ValidationError):
        FinalState.model_validate(payload)


def _eval_result_payload(**overrides):
    gt = {
        "keywords": ["logistics"],
        "language": None,
        "created_after": None,
        "created_before": None,
        "min_stars": None,
        "max_stars": None,
        "sort": None,
        "order": None,
        "limit": 10,
    }
    base = {
        "run_id": "run_123",
        "session_id": "sess_abc",
        "eval_item_id": "q001",
        "model_name": "gpt-4.1-mini",
        "ground_truth_structured_query": gt,
        "predicted_structured_query": gt,
        "score": 1.0,
        "is_correct": True,
        "created_at": _now(),
    }
    base.update(overrides)
    return base


def test_eval_result_parses_correct_case():
    EvalResult.model_validate(_eval_result_payload())


def test_eval_result_allows_null_prediction_for_rejected_case():
    payload = _eval_result_payload(predicted_structured_query=None, score=1.0, is_correct=True)
    EvalResult.model_validate(payload)


def test_eval_result_score_out_of_range_rejected():
    with pytest.raises(ValidationError):
        EvalResult.model_validate(_eval_result_payload(score=1.5))
