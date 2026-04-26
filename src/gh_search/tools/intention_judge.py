"""intention_judge tool (TOOLS.md §3, §7).

Ask the LLM whether the user query is a GitHub repository search that the
current MVP schema can express. Route to parse_query if supported, otherwise
terminate with the corresponding reason. Prompt text is loaded from
`prompts/core/intention.md` + per-model appendix at call time so
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
    """用 LLM 判斷這句話是不是本專案支援的 GitHub repo 搜尋需求。

    這支 tool 的責任很單純：先做「要不要進主流程」的第一層分流。
    它不負責解析 stars、language、date 這些條件，只回答兩件事：

    1. 這是不是在找 GitHub repository？
    2. 如果是，描述是否清楚到可以進下一步 parse？

    分流結果會直接寫進 `state.control.next_tool`：
    - `supported` -> 下一步是 `PARSE_QUERY`
    - `ambiguous` / `unsupported` -> 下一步是 `FINALIZE`

    所以這一步判斷的是「能不能繼續跑 agent flow」，不是「query 怎麼拆」。
    """
    system_prompt = compose_system_for(PROMPT_NAME, llm)
    response = llm(system_prompt, state.user_query, RESPONSE_SCHEMA)
    judge = _parse_judge(response.parsed)

    if judge.intent_status is IntentStatus.SUPPORTED:
        # 確認是可處理的 repo 搜尋需求後，才交給 parse_query 繼續拆條件。
        control = Control(
            next_tool=ToolName.PARSE_QUERY, should_terminate=False, terminate_reason=None
        )
        judge = judge.model_copy(update={"should_terminate": False})
    else:
        # 不支援或描述過度模糊時，直接終止，不進後面的 parse / validate。
        control = Control(
            next_tool=ToolName.FINALIZE,
            should_terminate=True,
            terminate_reason=_TERMINATION_MAP[judge.intent_status],
        )
        judge = judge.model_copy(update={"should_terminate": True})

    return state.model_copy(update={"intention_judge": judge, "control": control})


def _parse_judge(raw: dict) -> IntentionJudge:
    """Validate the LLM payload, falling back to a safe ambiguous rejection."""
    try:
        return IntentionJudge.model_validate(raw)
    except ValidationError:
        return IntentionJudge(
            intent_status=IntentStatus.AMBIGUOUS,
            reason="malformed LLM response",
            should_terminate=True,
        )
