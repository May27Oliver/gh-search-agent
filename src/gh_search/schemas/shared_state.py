"""SharedAgentState and its sub-models (SCHEMAS.md §2-§6)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from gh_search.schemas.enums import (
    ExecutionStatus,
    IntentStatus,
    TerminateReason,
    ToolName,
)
from gh_search.schemas.structured_query import StructuredQuery

_STRICT = ConfigDict(extra="forbid", frozen=True)


class IntentionJudge(BaseModel):
    model_config = _STRICT

    intent_status: IntentStatus = Field(...)
    reason: str | None = Field(...)
    should_terminate: bool = Field(...)


class Validation(BaseModel):
    model_config = _STRICT

    is_valid: bool = Field(...)
    errors: list[str] = Field(...)
    missing_required_fields: list[str] = Field(...)


class Execution(BaseModel):
    model_config = _STRICT

    status: ExecutionStatus = Field(...)
    response_status: int | None = Field(...)
    result_count: int | None = Field(...)


class Control(BaseModel):
    model_config = _STRICT

    next_tool: ToolName | None = Field(...)
    should_terminate: bool = Field(...)
    terminate_reason: TerminateReason | None = Field(...)


class SharedAgentState(BaseModel):
    """The single piece of state every tool reads from and writes to."""

    model_config = _STRICT

    run_id: str = Field(...)
    turn_index: int = Field(..., ge=0)
    max_turns: int = Field(..., ge=1)
    user_query: str = Field(...)
    intention_judge: IntentionJudge = Field(...)
    structured_query: StructuredQuery | None = Field(...)
    validation: Validation = Field(...)
    compiled_query: str | None = Field(...)
    execution: Execution = Field(...)
    control: Control = Field(...)
