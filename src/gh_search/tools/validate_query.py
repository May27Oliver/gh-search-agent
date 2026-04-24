"""validate_query tool (TOOLS.md §3, §9, KEYWORD_TUNING_SPEC §8).

Runs the shared keyword canonicalization pipeline (`normalize_keywords`)
before semantic validation so the rest of the loop, the repair step, the
scorer, and the artifact trace all see the same post-normalization keywords.
"""
from __future__ import annotations

from gh_search.normalizers import normalize_keywords
from gh_search.schemas import (
    Control,
    SharedAgentState,
    StructuredQuery,
    TerminateReason,
    ToolName,
    Validation,
    ValidationIssue,
)
from gh_search.validator import validate_structured_query


def validate_query(state: SharedAgentState) -> SharedAgentState:
    if state.structured_query is None:
        validation = Validation(
            is_valid=False,
            errors=[
                ValidationIssue(
                    code="parse_failed",
                    message="structured_query is missing; parse_query did not produce one",
                    field="structured_query",
                )
            ],
            missing_required_fields=[],
        )
        control = Control(
            next_tool=ToolName.FINALIZE,
            should_terminate=True,
            terminate_reason=TerminateReason.VALIDATION_FAILED,
        )
        return state.model_copy(update={"validation": validation, "control": control})

    normalized_sq = _normalize_structured_query(state.structured_query)
    validation = validate_structured_query(normalized_sq)
    if validation.is_valid:
        control = Control(
            next_tool=ToolName.COMPILE_GITHUB_QUERY,
            should_terminate=False,
            terminate_reason=None,
        )
    else:
        control = Control(
            next_tool=ToolName.REPAIR_QUERY,
            should_terminate=False,
            terminate_reason=None,
        )

    return state.model_copy(
        update={
            "structured_query": normalized_sq,
            "validation": validation,
            "control": control,
        }
    )


def _normalize_structured_query(sq: StructuredQuery) -> StructuredQuery:
    normalized = normalize_keywords(list(sq.keywords), language=sq.language)
    if normalized == list(sq.keywords):
        return sq
    return sq.model_copy(update={"keywords": normalized})
