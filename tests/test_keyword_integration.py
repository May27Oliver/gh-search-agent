"""Integration tests — shared keyword normalizer contract (KEYWORD_TUNING_SPEC §8).

These tests deliberately cross module boundaries so that next-round drift
(e.g. someone re-implements canonicalization locally in validator / scorer /
repair) is caught in CI:

1. `validate_query` tool must commit normalized keywords back to state.
2. Scorer must route both GT and predicted keywords through the same
   `normalize_keywords` call — no local lowercase / sort / merge / lemmatize.
3. `repair_query` must pass validation errors as structured ValidationIssue
   objects (JSON-serialized), not as loose strings.
"""
from __future__ import annotations

import json

from gh_search.eval.scorer import score_item
from gh_search.llm import LLMResponse
from gh_search.schemas import (
    Control,
    Execution,
    ExecutionStatus,
    IntentStatus,
    IntentionJudge,
    SharedAgentState,
    StructuredQuery,
    ToolName,
    Validation,
    ValidationIssue,
)
from gh_search.tools import repair_query, validate_query


def _make_sq(**overrides) -> StructuredQuery:
    base = {
        "keywords": [],
        "language": None,
        "created_after": None,
        "created_before": None,
        "min_stars": None,
        "max_stars": None,
        "sort": None,
        "order": None,
        "limit": 10,
    }
    base.update(overrides)
    return StructuredQuery.model_validate(base)


def _make_state(**overrides) -> SharedAgentState:
    base = dict(
        run_id="r_int",
        turn_index=2,
        max_turns=5,
        user_query="any",
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
            next_tool=ToolName.VALIDATE_QUERY, should_terminate=False, terminate_reason=None
        ),
    )
    base.update(overrides)
    return SharedAgentState(**base)


def test_validate_tool_commits_normalized_keywords_to_state():
    """Validate tool must write post-normalization keywords back to state —
    downstream compile / log / scorer all depend on this being the single
    canonical form (§8.2)."""
    sq = _make_sq(keywords=["JS", "libraries", "FRAMEWORK"], min_stars=100)
    state = _make_state(structured_query=sq)

    new_state = validate_query(state)

    assert new_state.structured_query is not None
    assert new_state.structured_query.keywords == ["javascript", "library", "framework"]
    assert new_state.validation.is_valid is True
    keyword_codes = {
        "alias_applied",
        "plural_drift",
        "language_leak",
        "modifier_stopword",
        "phrase_split",
    }
    assert not any(issue.code in keyword_codes for issue in new_state.validation.errors), (
        "keyword violations must not leak into Validation.errors post-iter2 "
        "(KEYWORD_TUNING_SPEC §8.4 decision)"
    )


def test_scorer_normalizes_both_sides_through_shared_entry_point():
    """GT and prediction that differ only in canonicalizable tokens (alias /
    plural / case) must score as equal — proves both sides route through
    `normalize_keywords` rather than a local string compare (§8.3)."""
    item = {
        "id": "int001",
        "ground_truth_structured_query": {
            "keywords": ["JS", "libraries"],
            "language": None,
            "created_after": None,
            "created_before": None,
            "min_stars": None,
            "max_stars": None,
            "sort": None,
            "order": None,
            "limit": 10,
        },
        "expect_rejection": False,
    }
    predicted = _make_sq(keywords=["javascript", "library"])

    result = score_item(
        eval_item=item,
        predicted_query=predicted,
        actual_outcome="success",
        actual_terminate_reason=None,
    )

    assert result.is_correct is True
    assert result.field_results["keywords"] is True


def test_repair_prompt_relays_structured_validation_issue():
    """Repair must JSON-encode ValidationIssue objects so the model sees the
    `code` / `field` / `token` structure, not a stringified blob (§8.0.5)."""
    captured: dict = {}

    def stub_llm(system_prompt: str, user_message: str, response_schema: dict) -> LLMResponse:
        captured["user_message"] = user_message
        fixed = {
            "keywords": ["x"],
            "language": None,
            "created_after": None,
            "created_before": None,
            "min_stars": 100,
            "max_stars": 500,
            "sort": None,
            "order": None,
            "limit": 10,
        }
        return LLMResponse(raw_text=json.dumps(fixed), parsed=fixed)

    issue = ValidationIssue(
        code="min_gt_max_stars",
        message="min_stars (500) must be <= max_stars (100)",
        field="min_stars",
    )
    state = _make_state(
        structured_query=_make_sq(keywords=["x"], min_stars=500, max_stars=100),
        validation=Validation(is_valid=False, errors=[issue], missing_required_fields=[]),
        control=Control(
            next_tool=ToolName.REPAIR_QUERY, should_terminate=False, terminate_reason=None
        ),
    )

    repair_query(state, llm=stub_llm)

    msg = captured["user_message"]
    # Raw string form would be "min_stars (500) must be <= max_stars (100)" —
    # structured form must include the JSON `"code"` key with the issue code.
    assert '"code": "min_gt_max_stars"' in msg or '"code":"min_gt_max_stars"' in msg
    assert '"field": "min_stars"' in msg or '"field":"min_stars"' in msg
