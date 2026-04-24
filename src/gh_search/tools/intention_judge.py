"""intention_judge tool (TOOLS.md §3, §7).

Ask the LLM whether the user query is a GitHub repository search that the
current MVP schema can express. Route to parse_query if supported, otherwise
terminate with the corresponding reason. Prompt text is loaded from
`prompts/core/intention-v1.md` + per-model appendix at call time so
model-specific intent-gate tuning (PHASE2_PLAN §1.1) stays isolated.
"""
from __future__ import annotations

from pydantic import ValidationError

from gh_search.llm import LLMJsonCall
from gh_search.llm.prompts import compose_system_for
from gh_search.schemas import (
    Control,
    IntentStatus,
    IntentionJudge,
    SharedAgentState,
    TerminateReason,
    ToolName,
)

PROMPT_NAME = "intention"

RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "intent_status": {
            "type": "string",
            "enum": ["supported", "ambiguous", "unsupported"],
        },
        "reason": {"type": ["string", "null"]},
        "should_terminate": {"type": "boolean"},
    },
    "required": ["intent_status", "reason", "should_terminate"],
    "additionalProperties": False,
}


_TERMINATION_MAP = {
    IntentStatus.UNSUPPORTED: TerminateReason.UNSUPPORTED_INTENT,
    IntentStatus.AMBIGUOUS: TerminateReason.AMBIGUOUS_QUERY,
}


def intention_judge(state: SharedAgentState, llm: LLMJsonCall) -> SharedAgentState:
    system_prompt = compose_system_for(PROMPT_NAME, llm)
    response = llm(system_prompt, state.user_query, RESPONSE_SCHEMA)
    judge = _parse_judge(response.parsed)

    if judge.intent_status is IntentStatus.SUPPORTED:
        control = Control(
            next_tool=ToolName.PARSE_QUERY, should_terminate=False, terminate_reason=None
        )
        judge = judge.model_copy(update={"should_terminate": False})
    else:
        control = Control(
            next_tool=ToolName.FINALIZE,
            should_terminate=True,
            terminate_reason=_TERMINATION_MAP[judge.intent_status],
        )
        judge = judge.model_copy(update={"should_terminate": True})

    return state.model_copy(update={"intention_judge": judge, "control": control})


def _parse_judge(raw: dict) -> IntentionJudge:
    try:
        return IntentionJudge.model_validate(raw)
    except ValidationError:
        return IntentionJudge(
            intent_status=IntentStatus.AMBIGUOUS,
            reason="malformed LLM response",
            should_terminate=True,
        )
