"""EvalResult schema (SCHEMAS.md §10, EVAL.md §10)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from gh_search.schemas.structured_query import StructuredQuery


class EvalResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(...)
    session_id: str = Field(...)
    eval_item_id: str = Field(...)
    model_name: str = Field(...)
    ground_truth_structured_query: StructuredQuery | None = Field(...)
    predicted_structured_query: StructuredQuery | None = Field(...)
    score: float = Field(..., ge=0.0, le=1.0)
    is_correct: bool = Field(...)
    created_at: str = Field(...)
