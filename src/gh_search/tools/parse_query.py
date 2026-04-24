"""parse_query tool (TOOLS.md §3 parse_query).

Ask the LLM to turn the user's natural-language request into a StructuredQuery.
The system prompt is composed at call time from `prompts/core/parse-v1.md`
plus the per-model appendix (`prompts/appendix/parse-<model>-v1.md`) so that
PHASE2_PLAN §1.1's "prompt / few-shot / gate wording must stay isolated as
model-specific appendix" is actually enforced at runtime — not just claimed
by a `prompt_version` label (PHASE2_PLAN §3.0).

This tool is deliberately narrow: it only touches state.structured_query and
state.control.next_tool. It never sets terminate flags; validate_query owns
that decision.
"""
from __future__ import annotations

from pydantic import ValidationError

from gh_search.llm import LLMJsonCall
from gh_search.llm.prompts import compose_system_for
from gh_search.schemas import Control, SharedAgentState, StructuredQuery, ToolName

PROMPT_NAME = "parse"

RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "keywords": {"type": "array", "items": {"type": "string"}},
        "language": {"type": ["string", "null"]},
        "created_after": {"type": ["string", "null"]},
        "created_before": {"type": ["string", "null"]},
        "min_stars": {"type": ["integer", "null"], "minimum": 0},
        "max_stars": {"type": ["integer", "null"], "minimum": 0},
        "sort": {"type": ["string", "null"], "enum": ["stars", "forks", "updated", None]},
        "order": {"type": ["string", "null"], "enum": ["asc", "desc", None]},
        "limit": {"type": "integer", "minimum": 1, "maximum": 20},
    },
    "required": [
        "keywords",
        "language",
        "created_after",
        "created_before",
        "min_stars",
        "max_stars",
        "sort",
        "order",
        "limit",
    ],
    "additionalProperties": False,
}


def parse_query(state: SharedAgentState, llm: LLMJsonCall) -> SharedAgentState:
    system_prompt = compose_system_for(PROMPT_NAME, llm)
    response = llm(system_prompt, state.user_query, RESPONSE_SCHEMA)
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
