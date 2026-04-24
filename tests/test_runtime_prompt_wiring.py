"""Runtime prompt wiring (PHASE2_PLAN §3.0 — review fix).

Phase 2 claims tools use `prompts/core/*.md` + `prompts/appendix/*.md` at
runtime. Earlier versions scaffolded the files but tools still shipped
hard-coded `SYSTEM_PROMPT` constants — so `prompt_version` was a cosmetic
label that didn't describe what the model actually saw.

These tests lock the wiring in place:

1. The system prompt the LLM receives matches `prompts/core/<tool>-v1.md`.
2. Per-model appendix content flows through to the LLM (via model_name on
   the adapter closure).
3. `_record_llm` preserves `.model_name` so tools can compose mid-session.
"""
from __future__ import annotations

import json
from pathlib import Path

from gh_search.agent.loop import _record_llm
from gh_search.llm import LLMResponse
from gh_search.llm.prompts import (
    DEFAULT_PROMPTS_ROOT,
    compose_system_for,
    load_prompt_bundle,
)
from gh_search.schemas import (
    Control,
    Execution,
    ExecutionStatus,
    IntentionJudge,
    IntentStatus,
    SharedAgentState,
    StructuredQuery,
    ToolName,
    Validation,
    ValidationIssue,
)
from gh_search.tools.intention_judge import intention_judge
from gh_search.tools.parse_query import parse_query
from gh_search.tools.repair_query import repair_query


def _recording_llm(payload: dict, model_name: str = "gpt-4.1-mini"):
    """Fake LLM that records the system prompt it was handed."""

    sink: dict[str, str] = {}

    def fn(system_prompt: str, user_message: str, response_schema: dict) -> LLMResponse:
        sink["system_prompt"] = system_prompt
        sink["user_message"] = user_message
        return LLMResponse(
            raw_text=json.dumps(payload),
            parsed=payload,
            provider_name="openai",
            model_name=model_name,
        )

    fn.model_name = model_name  # type: ignore[attr-defined]
    fn.provider_name = "openai"  # type: ignore[attr-defined]
    return fn, sink


def _base_state(user_query: str = "some query") -> SharedAgentState:
    return SharedAgentState(
        run_id="run_test",
        turn_index=0,
        max_turns=5,
        user_query=user_query,
        intention_judge=IntentionJudge(
            intent_status=IntentStatus.SUPPORTED, reason=None, should_terminate=False
        ),
        structured_query=None,
        validation=Validation(is_valid=False, errors=[], missing_required_fields=[]),
        compiled_query=None,
        execution=Execution(
            status=ExecutionStatus.NOT_STARTED, response_status=None, result_count=None
        ),
        control=Control(
            next_tool=ToolName.INTENTION_JUDGE, should_terminate=False, terminate_reason=None
        ),
    )


_PARSE_OK = {
    "keywords": ["orm"],
    "language": "Python",
    "created_after": None,
    "created_before": None,
    "min_stars": None,
    "max_stars": None,
    "sort": None,
    "order": None,
    "limit": 10,
}


def test_parse_query_uses_core_prompt_file_content():
    llm, sink = _recording_llm(_PARSE_OK, model_name="gpt-4.1-mini")
    parse_query(_base_state(), llm)

    expected = load_prompt_bundle("parse", "gpt-4.1-mini").composed_system
    assert sink["system_prompt"] == expected
    # Sanity: the prompt actually contains the rule text from the file, not
    # whatever was hard-coded in an old inline string.
    file_text = (DEFAULT_PROMPTS_ROOT / "core" / "parse-v1.md").read_text(encoding="utf-8")
    assert "keywords" in sink["system_prompt"]
    assert sink["system_prompt"].strip() == file_text.strip()  # empty appendix


def test_intention_judge_uses_core_prompt_file_content():
    payload = {"intent_status": "supported", "reason": None, "should_terminate": False}
    llm, sink = _recording_llm(payload, model_name="claude-sonnet-4")
    intention_judge(_base_state(), llm)

    expected = load_prompt_bundle("intention", "claude-sonnet-4").composed_system
    assert sink["system_prompt"] == expected


def test_repair_query_uses_core_prompt_file_content():
    llm, sink = _recording_llm(_PARSE_OK, model_name="deepseek-r1")
    state = _base_state()
    state = state.model_copy(
        update={
            "structured_query": StructuredQuery.model_validate(_PARSE_OK),
            "validation": Validation(
                is_valid=False,
                errors=[
                    ValidationIssue(code="min_gt_max_stars", message="min_stars > max_stars")
                ],
                missing_required_fields=[],
            ),
        }
    )
    repair_query(state, llm)

    expected = load_prompt_bundle("repair", "deepseek-r1").composed_system
    assert sink["system_prompt"] == expected


def test_appendix_content_reaches_llm_when_present(tmp_path: Path, monkeypatch):
    """Edit an appendix file on disk and verify the tool picks it up.

    This is the canary test: if someone re-introduces a hard-coded
    SYSTEM_PROMPT in a tool, the appendix text never reaches the LLM and
    this test fails loudly.
    """
    # Build a scratch prompts tree. parse tool's compose_system_for reads
    # the default prompts root, so we monkeypatch it.
    scratch = tmp_path / "prompts"
    (scratch / "core").mkdir(parents=True)
    (scratch / "appendix").mkdir(parents=True)
    (scratch / "core" / "parse-v1.md").write_text("CORE_TEXT", encoding="utf-8")
    (scratch / "appendix" / "parse-gpt-4.1-mini-v1.md").write_text(
        "APPENDIX_INJECTED_MARKER", encoding="utf-8"
    )

    import gh_search.llm.prompts as prompts_mod

    monkeypatch.setattr(prompts_mod, "DEFAULT_PROMPTS_ROOT", scratch)

    llm, sink = _recording_llm(_PARSE_OK, model_name="gpt-4.1-mini")
    parse_query(_base_state(), llm)

    assert "CORE_TEXT" in sink["system_prompt"]
    assert "APPENDIX_INJECTED_MARKER" in sink["system_prompt"]


def test_record_llm_preserves_model_name_attr():
    """The loop wraps the llm with `_record_llm` to capture raw_text. The
    wrapper must propagate `.model_name` / `.provider_name` or tools that
    introspect them (for prompt composition) will fall back to the default
    model, producing silently-wrong per-model appendix selection."""

    def base(sys_, usr, sch):
        return LLMResponse(raw_text="{}", parsed={}, model_name="X", provider_name="openai")

    base.model_name = "claude-sonnet-4"
    base.provider_name = "anthropic"

    wrapped = _record_llm(base, raw_box=[])
    assert wrapped.model_name == "claude-sonnet-4"
    assert wrapped.provider_name == "anthropic"


def test_compose_system_for_falls_back_when_model_name_missing():
    """Test stubs that hand-build a plain function (no `.model_name`) must
    still get a working prompt — compose_system_for falls back to a
    sensible default rather than crashing."""

    def raw(_s, _u, _sch):
        return LLMResponse(raw_text="{}", parsed={})

    composed = compose_system_for("parse", raw)
    assert "keywords" in composed  # core prompt loaded
