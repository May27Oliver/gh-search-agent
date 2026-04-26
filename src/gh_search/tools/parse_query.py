"""parse_query tool (TOOLS.md §3 parse_query).

Ask the LLM to turn the user's natural-language request into a StructuredQuery.
The system prompt is composed at call time from `prompts/core/parse.md`
plus the per-model appendix (`prompts/appendix/parse-<model>.md`) so that
PHASE2_PLAN §1.1's "prompt / few-shot / gate wording must stay isolated as
model-specific appendix" is actually enforced at runtime — not just claimed
by a `prompt_version` label (PHASE2_PLAN §3.0).

This tool is deliberately narrow: it only touches state.structured_query and
state.control.next_tool. It never sets terminate flags; validate_query owns
that decision.

ITER5_DATE_TUNING_SPEC §7.1.1: the user_message is prefixed with a
`Today: YYYY-MM-DD` anchor line so relative-date rules in parse.md
(last year / this year / 今年 / 去年) can resolve against a concrete date.
Eval path can pin the anchor from dataset metadata; production CLI path omits
the kwarg so it falls back to `date.today()`.
"""
from __future__ import annotations

from datetime import date

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


def parse_query(
    state: SharedAgentState,
    llm: LLMJsonCall,
    *,
    reference_date: date | None = None,
) -> SharedAgentState:
    """Ask the LLM for a `StructuredQuery` and hand off to validation."""
    system_prompt = compose_system_for(PROMPT_NAME, llm)
    reference_date_iso = (reference_date or date.today()).isoformat()
    user_message = f"Today: {reference_date_iso}\n\n{state.user_query}"
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
