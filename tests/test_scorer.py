"""Task 3.8 RED: scorer (EVAL.md §7, EVAL_EXECUTION_SPEC.md §10-§11)."""
from __future__ import annotations

from gh_search.eval.scorer import ScoreResult, score_item
from gh_search.schemas import StructuredQuery

_BASE = {
    "keywords": ["react", "component"],
    "language": "JavaScript",
    "created_after": None,
    "created_before": None,
    "min_stars": 100,
    "max_stars": None,
    "sort": "stars",
    "order": "desc",
    "limit": 10,
}


def _sq(**overrides):
    payload = {**_BASE, **overrides}
    return StructuredQuery.model_validate(payload)


def _item(gt=_BASE, expect_rejection=False, item_id="q001"):
    return {
        "id": item_id,
        "ground_truth_structured_query": gt,
        "expect_rejection": expect_rejection,
    }


def test_exact_match_scores_one():
    r = score_item(
        eval_item=_item(),
        predicted_query=_sq(),
        actual_outcome="success",
        actual_terminate_reason=None,
    )
    assert isinstance(r, ScoreResult)
    assert r.is_correct is True
    assert r.score == 1.0


def test_keyword_order_does_not_matter():
    r = score_item(
        eval_item=_item(),
        predicted_query=_sq(keywords=["component", "react"]),
        actual_outcome="success",
        actual_terminate_reason=None,
    )
    assert r.is_correct is True


def test_language_case_insensitive():
    r = score_item(
        eval_item=_item(),
        predicted_query=_sq(language="javascript"),
        actual_outcome="success",
        actual_terminate_reason=None,
    )
    assert r.is_correct is True


def test_single_field_mismatch_fails():
    r = score_item(
        eval_item=_item(),
        predicted_query=_sq(min_stars=999),
        actual_outcome="success",
        actual_terminate_reason=None,
    )
    assert r.is_correct is False
    assert r.score == 0.0
    assert any("min_stars" in m for m in r.mismatch_reasons)


def test_none_prediction_non_rejection_case_fails():
    r = score_item(
        eval_item=_item(),
        predicted_query=None,
        actual_outcome="validation_failed",
        actual_terminate_reason="validation_failed",
    )
    assert r.is_correct is False


def test_expected_rejection_with_rejected_outcome_is_correct():
    item = {
        **_item(gt=None, expect_rejection=True, item_id="r1"),
        "expected_terminate_reason": "unsupported_intent",
    }
    r = score_item(
        eval_item=item,
        predicted_query=None,
        actual_outcome="rejected",
        actual_terminate_reason="unsupported_intent",
    )
    assert r.is_correct is True
    assert r.score == 1.0


def test_expected_rejection_with_wrong_terminate_reason_is_incorrect():
    # Unsupported and ambiguous are both "rejected" outcomes; the scorer must
    # not conflate them (EVAL.md §8, EVAL_EXECUTION_SPEC §11).
    item = {
        **_item(gt=None, expect_rejection=True, item_id="r3"),
        "expected_terminate_reason": "unsupported_intent",
    }
    r = score_item(
        eval_item=item,
        predicted_query=None,
        actual_outcome="rejected",
        actual_terminate_reason="ambiguous_query",
    )
    assert r.is_correct is False
    assert any("terminate_reason" in m for m in r.mismatch_reasons)


def test_expected_rejection_without_expected_reason_still_accepts_any_rejection():
    # Back-compat: items that don't specify expected_terminate_reason accept
    # any rejection. New items should always include it.
    r = score_item(
        eval_item=_item(gt=None, expect_rejection=True, item_id="r4"),
        predicted_query=None,
        actual_outcome="rejected",
        actual_terminate_reason="ambiguous_query",
    )
    assert r.is_correct is True


def test_expected_rejection_with_success_is_incorrect():
    r = score_item(
        eval_item=_item(gt=None, expect_rejection=True, item_id="r2"),
        predicted_query=_sq(),
        actual_outcome="success",
        actual_terminate_reason=None,
    )
    assert r.is_correct is False


def test_field_results_contain_per_field_bool():
    r = score_item(
        eval_item=_item(),
        predicted_query=_sq(min_stars=999),
        actual_outcome="success",
        actual_terminate_reason=None,
    )
    assert "min_stars" in r.field_results
    assert r.field_results["min_stars"] is False
    assert r.field_results["keywords"] is True


def test_none_vs_empty_list_distinct_for_keywords():
    # Spec: null and missing are not equivalent. For keywords specifically,
    # [] and [] match; [] vs something populated must differ.
    r = score_item(
        eval_item=_item(gt={**_BASE, "keywords": []}),
        predicted_query=_sq(keywords=[]),
        actual_outcome="success",
        actual_terminate_reason=None,
    )
    assert r.is_correct is True


def test_date_comparison_exact():
    r = score_item(
        eval_item=_item(gt={**_BASE, "created_after": "2024-01-01"}),
        predicted_query=_sq(created_after="2024-01-01"),
        actual_outcome="success",
        actual_terminate_reason=None,
    )
    assert r.is_correct is True
