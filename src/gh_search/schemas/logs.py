"""RunLog / TurnLog / FinalState (SCHEMAS.md §7-§9, LOGGING.md §6)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gh_search.schemas.enums import IntentStatus, ToolName
from gh_search.schemas.shared_state import SharedAgentState
from gh_search.schemas.structured_query import StructuredQuery

_STRICT = ConfigDict(extra="forbid", frozen=True)


class RunLog(BaseModel):
    model_config = _STRICT

    session_id: str = Field(...)
    run_id: str = Field(...)
    run_type: str = Field(...)
    user_query: str = Field(...)
    model_name: str = Field(...)
    provider_name: str = Field(...)
    prompt_version: str = Field(...)
    final_outcome: str = Field(...)
    terminate_reason: str | None = Field(...)
    started_at: str = Field(...)
    ended_at: str = Field(...)
    log_version: str = Field(...)


class TurnLog(BaseModel):
    model_config = _STRICT

    session_id: str = Field(...)
    run_id: str = Field(...)
    turn_index: int = Field(..., ge=0)
    tool_name: ToolName = Field(...)
    input_query: str = Field(...)
    intention_status: IntentStatus | None = Field(...)
    raw_model_output: str | None = Field(...)
    parsed_structured_query: StructuredQuery | None = Field(...)
    validation_result: bool | None = Field(...)
    validation_errors: list[str] = Field(...)
    compiled_query: str | None = Field(...)
    response_status: int | None = Field(...)
    final_outcome: str | None = Field(...)
    next_action: ToolName | None = Field(...)
    latency_ms: int = Field(..., ge=0)
    created_at: str = Field(...)


class FinalState(BaseModel):
    model_config = _STRICT

    session_id: str = Field(...)
    run_id: str = Field(...)
    state_type: Literal["final"] = Field(...)
    turn_index: int = Field(..., ge=0)
    state_payload: SharedAgentState = Field(...)
    created_at: str = Field(...)
