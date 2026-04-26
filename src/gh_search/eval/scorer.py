"""Deterministic scorer for StructuredQuery predictions.

Primary metric is normalized exact match (EVAL.md §7, KEYWORD_TUNING_SPEC §8.3):
  - keywords are compared after `normalize_keywords(..., language=)` on BOTH
    sides — scorer never does its own lowercase / sort / merge / lemmatize
  - string fields (language) compared case-insensitive
  - dates compared as YYYY-MM-DD strings
  - ints and enums compared exactly
  - for rejected items, final_outcome must be 'rejected'
"""
from __future__ import annotations

from dataclasses import dataclass, field

from gh_search.normalizers import normalize_keywords
from gh_search.schemas import StructuredQuery

_FIELDS = (
    "keywords",
    "language",
    "created_after",
    "created_before",
    "min_stars",
    "max_stars",
    "sort",
    "order",
    "limit",
)

REJECTED_OUTCOMES = {"rejected"}


@dataclass(frozen=True)
class ScoreResult:
    is_correct: bool
    score: float
    score_type: str
    field_results: dict[str, bool] = field(default_factory=dict)
    mismatch_reasons: list[str] = field(default_factory=list)
    terminate_reason: str | None = None


def score_item(
    eval_item: dict,
    predicted_query: StructuredQuery | None,
    actual_outcome: str,
    actual_terminate_reason: str | None,
) -> ScoreResult:
    """Score one eval item using exact-match rules for normal and rejected cases."""
    if eval_item.get("expect_rejection", False):
        mismatches: list[str] = []
        if actual_outcome not in REJECTED_OUTCOMES:
            mismatches.append(f"expected rejection, got outcome={actual_outcome}")
        expected_reason = eval_item.get("expected_terminate_reason")
        if expected_reason is not None and actual_terminate_reason != expected_reason:
            mismatches.append(
                f"terminate_reason mismatch: expected={expected_reason!r} "
                f"got={actual_terminate_reason!r}"
            )
        ok = not mismatches
        return ScoreResult(
            is_correct=ok,
            score=1.0 if ok else 0.0,
            score_type="rejected_exact_match",
            field_results={},
            mismatch_reasons=mismatches,
            terminate_reason=actual_terminate_reason,
        )

    gt_raw = eval_item.get("ground_truth_structured_query")
    if gt_raw is None:
        return ScoreResult(
            is_correct=False,
            score=0.0,
            score_type="normalized_exact_match",
            mismatch_reasons=["ground_truth_structured_query is null"],
            terminate_reason=actual_terminate_reason,
        )
    gt = StructuredQuery.model_validate(gt_raw)

    if predicted_query is None:
        return ScoreResult(
            is_correct=False,
            score=0.0,
            score_type="normalized_exact_match",
            field_results={f: False for f in _FIELDS},
            mismatch_reasons=["predicted_structured_query is null"],
            terminate_reason=actual_terminate_reason,
        )

    field_results, mismatches = _compare(gt, predicted_query)
    is_correct = all(field_results.values())
    return ScoreResult(
        is_correct=is_correct,
        score=1.0 if is_correct else 0.0,
        score_type="normalized_exact_match",
        field_results=field_results,
        mismatch_reasons=mismatches,
        terminate_reason=actual_terminate_reason,
    )


def _compare(gt: StructuredQuery, pred: StructuredQuery) -> tuple[dict[str, bool], list[str]]:
    """Compare each `StructuredQuery` field and collect mismatch reasons."""
    results: dict[str, bool] = {}
    mismatches: list[str] = []

    # keywords: route both sides through the shared normalizer so parser,
    # validator, and scorer can never disagree on canonicalization
    # (KEYWORD_TUNING_SPEC §8.3).
    gt_kw = sorted(normalize_keywords(list(gt.keywords), language=gt.language))
    pr_kw = sorted(normalize_keywords(list(pred.keywords), language=pred.language))
    results["keywords"] = gt_kw == pr_kw
    if not results["keywords"]:
        mismatches.append(
            f"keywords: gt={gt_kw} pred={pr_kw} (raw gt={gt.keywords} pred={pred.keywords})"
        )

    # language: case-insensitive, null-safe
    results["language"] = _eq_case_insensitive(gt.language, pred.language)
    if not results["language"]:
        mismatches.append(f"language: gt={gt.language!r} pred={pred.language!r}")

    # other scalars: strict equality
    for field_name in ("created_after", "created_before", "min_stars", "max_stars", "limit"):
        gv = getattr(gt, field_name)
        pv = getattr(pred, field_name)
        results[field_name] = gv == pv
        if not results[field_name]:
            mismatches.append(f"{field_name}: gt={gv!r} pred={pv!r}")

    # enums: compare by value
    results["sort"] = _enum_eq(gt.sort, pred.sort)
    if not results["sort"]:
        mismatches.append(f"sort: gt={gt.sort} pred={pred.sort}")

    results["order"] = _enum_eq(gt.order, pred.order)
    if not results["order"]:
        mismatches.append(f"order: gt={gt.order} pred={pred.order}")

    return results, mismatches


def _eq_case_insensitive(a: str | None, b: str | None) -> bool:
    """Compare nullable strings case-insensitively."""
    if a is None or b is None:
        return a is None and b is None
    return a.lower() == b.lower()


def _enum_eq(a, b) -> bool:
    """Compare enum-like values by `.value` when present."""
    av = a.value if hasattr(a, "value") else a
    bv = b.value if hasattr(b, "value") else b
    return av == bv
