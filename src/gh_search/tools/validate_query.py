"""validate_query tool (TOOLS.md §3, §9).

Semantic validation — routes to compile on success, repair on failure.
"""
from __future__ import annotations

from gh_search.schemas import (
    Control,
    SharedAgentState,
    TerminateReason,
    ToolName,
    Validation,
)
from gh_search.validator import validate_structured_query


def validate_query(state: SharedAgentState) -> SharedAgentState:
    if state.structured_query is None:
        validation = Validation(
            is_valid=False,
            errors=["structured_query is missing; parse_query did not produce one"],
            missing_required_fields=[],
        )
        control = Control(
            next_tool=ToolName.FINALIZE,
            should_terminate=True,
            terminate_reason=TerminateReason.VALIDATION_FAILED,
        )
    else:
        validation = validate_structured_query(state.structured_query)
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

    return state.model_copy(update={"validation": validation, "control": control})
