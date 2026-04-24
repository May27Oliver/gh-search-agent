"""repair_query tool (TOOLS.md §3 repair_query).

Takes a structurally-valid but semantically-rejected StructuredQuery plus the
validator's error messages, and asks the LLM to produce a corrected query.
Routes back to validate_query unconditionally (TOOLS.md §5). Prompt text is
loaded from `prompts/core/repair-v1.md` + per-model appendix at call time so
repair-specific tuning can diverge per model (PHASE2_PLAN §1.1).
"""
from __future__ import annotations

import json

from pydantic import ValidationError

from gh_search.llm import LLMJsonCall
from gh_search.llm.prompts import compose_system_for
from gh_search.schemas import Control, SharedAgentState, StructuredQuery, ToolName
from gh_search.tools.parse_query import RESPONSE_SCHEMA

PROMPT_NAME = "repair"


def repair_query(state: SharedAgentState, llm: LLMJsonCall) -> SharedAgentState:
    errors_payload = [issue.model_dump(mode="json") for issue in state.validation.errors]
    user_message = (
        f"User query: {state.user_query}\n"
        f"Current structured query: "
        f"{json.dumps(_dump(state.structured_query), ensure_ascii=False)}\n"
        f"Validation errors: {json.dumps(errors_payload, ensure_ascii=False)}\n"
        "Return a corrected structured query."
    )

    system_prompt = compose_system_for(PROMPT_NAME, llm)
    response = llm(system_prompt, user_message, RESPONSE_SCHEMA)
    try:
        sq = StructuredQuery.model_validate(response.parsed)
    except ValidationError:
        sq = None

    return state.model_copy(
        update={
            "structured_query": sq,
            "control": Control(
                next_tool=ToolName.VALIDATE_QUERY,
                should_terminate=False,
                terminate_reason=None,
            ),
        }
    )


def _dump(sq: StructuredQuery | None) -> dict | None:
    return sq.model_dump(mode="json") if sq is not None else None
