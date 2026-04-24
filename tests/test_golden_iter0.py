"""Golden regression tests for Iteration 0 (EVAL_GPT41MINI_20260424_PLAN §7).

These three items (q012, q015, q025) were the only correct answers in the
baseline `eval_gpt41mini_20260424` run. They are frozen as snapshot tests so
any scorer change or cross-model iteration cannot silently regress them.

The offline pytest below verifies scorer equality against a locked-in
`expected_predicted_structured_query`. For the matrix-level golden gate (each
model row must still produce is_correct=True during eval), see
`scripts/build_model_matrix.py` -> `golden_passed`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from gh_search.eval.scorer import score_item
from gh_search.schemas import StructuredQuery

GOLDEN_PATH = Path(__file__).parent / "golden" / "iter0_cases.json"
GOLDEN_IDS = ("q012", "q015", "q025")


def _load_cases() -> list[dict]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_golden_file_covers_all_three_ids() -> None:
    cases = _load_cases()
    assert {c["id"] for c in cases} == set(GOLDEN_IDS)


@pytest.mark.parametrize("case_id", GOLDEN_IDS)
def test_golden_case_scores_correct(case_id: str) -> None:
    case = next(c for c in _load_cases() if c["id"] == case_id)
    eval_item = {
        "id": case["id"],
        "ground_truth_structured_query": case["ground_truth_structured_query"],
        "expect_rejection": False,
    }
    predicted = StructuredQuery.model_validate(case["expected_predicted_structured_query"])

    result = score_item(
        eval_item=eval_item,
        predicted_query=predicted,
        actual_outcome="success",
        actual_terminate_reason=None,
    )

    assert result.is_correct, (
        f"Golden case {case_id} regressed. mismatches={result.mismatch_reasons}"
    )
    assert result.score == 1.0
    assert all(result.field_results.values())
