"""Tests for scripts/build_model_matrix.py.

Covers §4.6 canonical artifact shape, §4.5 cross-provider flag, and the
row-level golden_passed signal used by §10 Iteration gates.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


def _load_module():
    project_root = Path(__file__).resolve().parents[1]
    module_path = project_root / "scripts" / "build_model_matrix.py"
    spec = importlib.util.spec_from_file_location("build_model_matrix", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_model_matrix"] = module
    spec.loader.exec_module(module)
    return module


BMM = _load_module()


def _write_run(
    artifacts_root: Path,
    eval_run_id: str,
    model_name: str,
    per_items: list[dict],
    outcome_counts: dict[str, int],
    correct: int,
    prompt_version: str = "core + appendix-gpt41mini",
    provider_name: str | None = None,
) -> None:
    run_dir = artifacts_root / eval_run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    total = len(per_items)
    summary_payload: dict = {
        "eval_run_id": eval_run_id,
        "model_name": model_name,
        "total": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "outcome_counts": outcome_counts,
    }
    if provider_name is not None:
        summary_payload["provider_name"] = provider_name
    (run_dir / "model_summary.json").write_text(json.dumps(summary_payload))
    run_config_payload: dict = {
        "dataset_path": "datasets/eval_dataset_reviewed.json",
        "model_name": model_name,
        "prompt_version": prompt_version,
        "max_turns": 5,
        "started_at": "2026-04-24T00:00:00+00:00",
    }
    if provider_name is not None:
        run_config_payload["provider_name"] = provider_name
    (run_dir / "run_config.json").write_text(json.dumps(run_config_payload))
    (run_dir / "per_item_results.jsonl").write_text(
        "\n".join(json.dumps(p) for p in per_items) + "\n"
    )


_BASE_GT = {
    "keywords": ["orm", "library"],
    "language": "TypeScript",
    "created_after": None,
    "created_before": None,
    "min_stars": 2001,
    "max_stars": None,
    "sort": "stars",
    "order": "desc",
    "limit": 20,
}


def _item(
    eval_item_id: str,
    is_correct: bool,
    final_outcome: str = "success",
    gt: dict | None = None,
    pred: dict | None = None,
) -> dict:
    gt = gt if gt is not None else _BASE_GT
    pred = pred if pred is not None else gt
    return {
        "eval_item_id": eval_item_id,
        "is_correct": is_correct,
        "final_outcome": final_outcome,
        "terminate_reason": None,
        "ground_truth_structured_query": gt,
        "predicted_structured_query": pred,
        "mismatch_reasons": [] if is_correct else ["stub"],
    }


def test_build_matrix_single_run_flags_single_provider(tmp_path: Path) -> None:
    _write_run(
        artifacts_root=tmp_path / "artifacts" / "eval",
        eval_run_id="eval_gpt41mini_test",
        model_name="gpt-4.1-mini",
        per_items=[
            _item("q012", True),
            _item("q015", True),
            _item("q025", True),
        ],
        outcome_counts={"success": 3},
        correct=3,
    )

    matrix, refs = BMM.build_matrix(
        iteration_id="iter_0_baseline_20260424",
        dataset=Path("datasets/eval_dataset_reviewed.json"),
        run_ids=["eval_gpt41mini_test"],
        artifacts_root=tmp_path / "artifacts" / "eval",
    )

    assert matrix["iteration_id"] == "iter_0_baseline_20260424"
    assert matrix["cross_provider"] is False
    assert len(matrix["rows"]) == 1
    row = matrix["rows"][0]
    assert row["model_name"] == "gpt-4.1-mini"
    assert row["provider"] == "openai"
    assert row["golden_passed"] == "3/3"
    assert row["golden_failed_or_missing"] == []
    assert refs["eval_run_ids"] == ["eval_gpt41mini_test"]


def test_build_matrix_cross_provider_flag(tmp_path: Path) -> None:
    root = tmp_path / "artifacts" / "eval"
    _write_run(
        artifacts_root=root,
        eval_run_id="r_oai",
        model_name="gpt-4.1-mini",
        per_items=[_item("q012", True)],
        outcome_counts={"success": 1},
        correct=1,
    )
    _write_run(
        artifacts_root=root,
        eval_run_id="r_ant",
        model_name="claude-sonnet-4",
        per_items=[_item("q012", True)],
        outcome_counts={"success": 1},
        correct=1,
    )

    matrix, _ = BMM.build_matrix(
        iteration_id="iter_1_gate_relax_20260428",
        dataset=Path("datasets/eval_dataset_reviewed.json"),
        run_ids=["r_oai", "r_ant"],
        artifacts_root=root,
    )

    assert matrix["cross_provider"] is True
    providers = {r["provider"] for r in matrix["rows"]}
    assert providers == {"openai", "anthropic"}


def test_golden_passed_reports_failures(tmp_path: Path) -> None:
    root = tmp_path / "artifacts" / "eval"
    _write_run(
        artifacts_root=root,
        eval_run_id="r_bad",
        model_name="gpt-4.1-mini",
        per_items=[
            _item("q012", True),
            _item("q015", False),
            # q025 missing entirely
        ],
        outcome_counts={"success": 1},
        correct=1,
    )
    matrix, _ = BMM.build_matrix(
        iteration_id="iter_x_20260501",
        dataset=Path("datasets/eval_dataset_reviewed.json"),
        run_ids=["r_bad"],
        artifacts_root=root,
    )
    row = matrix["rows"][0]
    assert row["golden_passed"] == "1/3"
    assert set(row["golden_failed_or_missing"]) == {"q015", "q025"}


def test_per_field_recall_counts_only_non_rejection_items(tmp_path: Path) -> None:
    root = tmp_path / "artifacts" / "eval"
    _write_run(
        artifacts_root=root,
        eval_run_id="r_recall",
        model_name="gpt-4.1-mini",
        per_items=[
            _item("q012", True),  # all fields match
            _item(
                "q002",
                False,
                pred={**_BASE_GT, "language": "JavaScript"},  # language mismatch only
            ),
            # rejection item with null gt should not affect recall denominator
            {
                "eval_item_id": "r1",
                "is_correct": True,
                "final_outcome": "rejected",
                "terminate_reason": "unsupported_intent",
                "ground_truth_structured_query": None,
                "predicted_structured_query": None,
                "mismatch_reasons": [],
            },
        ],
        outcome_counts={"success": 1, "rejected": 1},
        correct=2,
    )
    matrix, _ = BMM.build_matrix(
        iteration_id="iter_x_20260501",
        dataset=Path("datasets/eval_dataset_reviewed.json"),
        run_ids=["r_recall"],
        artifacts_root=root,
    )
    fr = matrix["rows"][0]["per_field_recall"]
    # 2 non-rejection items: q012 matches all fields, q002 mismatches language only
    assert fr["language"] == 0.5
    assert fr["keywords"] == 1.0
    assert fr["min_stars"] == 1.0


def test_write_matrix_produces_canonical_paths(tmp_path: Path) -> None:
    root = tmp_path / "artifacts" / "eval"
    _write_run(
        artifacts_root=root,
        eval_run_id="r1",
        model_name="gpt-4.1-mini",
        per_items=[_item("q012", True)],
        outcome_counts={"success": 1},
        correct=1,
    )
    matrix, refs = BMM.build_matrix(
        iteration_id="iter_0_baseline_20260424",
        dataset=Path("datasets/eval_dataset_reviewed.json"),
        run_ids=["r1"],
        artifacts_root=root,
    )
    out_dir = tmp_path / "artifacts" / "eval" / "iterations" / "iter_0_baseline_20260424"
    BMM.write_matrix(out_dir, matrix, refs)

    assert (out_dir / "model_matrix.json").is_file()
    assert (out_dir / "model_matrix.md").is_file()
    assert (out_dir / "refs.json").is_file()

    md = (out_dir / "model_matrix.md").read_text(encoding="utf-8")
    assert "# Model Matrix — `iter_0_baseline_20260424`" in md
    assert "cross_provider" in md
    assert "golden_passed" in md


def test_unknown_model_gets_unknown_provider(tmp_path: Path) -> None:
    root = tmp_path / "artifacts" / "eval"
    _write_run(
        artifacts_root=root,
        eval_run_id="r_weird",
        model_name="some-future-model-v9",
        per_items=[_item("q012", True)],
        outcome_counts={"success": 1},
        correct=1,
    )
    matrix, _ = BMM.build_matrix(
        iteration_id="iter_x_20260501",
        dataset=Path("datasets/eval_dataset_reviewed.json"),
        run_ids=["r_weird"],
        artifacts_root=root,
    )
    assert matrix["rows"][0]["provider"] == "unknown"
    assert matrix["cross_provider"] is False


def test_matrix_row_prefers_provider_name_from_run_config(tmp_path: Path) -> None:
    """PHASE2_PLAN §3.0: run_config.provider_name is the source of truth.

    Even when the model_name is unrecognised (self-hosted fine-tune, custom
    alias, etc.), matrix rows must carry the provider recorded by the
    runner rather than falling through to `unknown`.
    """
    root = tmp_path / "artifacts" / "eval"
    _write_run(
        artifacts_root=root,
        eval_run_id="r_custom",
        model_name="custom-deepseek-ft-v3",  # not in PROVIDER_BY_MODEL
        per_items=[_item("q012", True)],
        outcome_counts={"success": 1},
        correct=1,
        provider_name="deepseek",
    )
    matrix, _ = BMM.build_matrix(
        iteration_id="iter_x_20260501",
        dataset=Path("datasets/eval_dataset_reviewed.json"),
        run_ids=["r_custom"],
        artifacts_root=root,
    )
    assert matrix["rows"][0]["provider"] == "deepseek"


def test_matrix_row_falls_back_to_static_map_for_legacy_runs(tmp_path: Path) -> None:
    """Iteration 0 runs predate provider_name, so the static map must still
    produce a non-unknown provider for canonical model names."""
    root = tmp_path / "artifacts" / "eval"
    _write_run(
        artifacts_root=root,
        eval_run_id="r_legacy",
        model_name="gpt-4.1-mini",
        per_items=[_item("q012", True)],
        outcome_counts={"success": 1},
        correct=1,
        # no provider_name
    )
    matrix, _ = BMM.build_matrix(
        iteration_id="iter_x_20260501",
        dataset=Path("datasets/eval_dataset_reviewed.json"),
        run_ids=["r_legacy"],
        artifacts_root=root,
    )
    assert matrix["rows"][0]["provider"] == "openai"


def test_matrix_top_level_exposes_prompt_family_not_misleading_prompt_version(
    tmp_path: Path,
) -> None:
    """Cross-provider matrices must not advertise a single model's
    `prompt_version` at the top level — that used to be `rows[0]`'s full
    `core + appendix-<model>`, which silently hid per-row appendix
    divergence. Top-level should only carry the shared core family."""
    root = tmp_path / "artifacts" / "eval"
    _write_run(
        artifacts_root=root,
        eval_run_id="r_oai",
        model_name="gpt-4.1-mini",
        per_items=[_item("q012", True)],
        outcome_counts={"success": 1},
        correct=1,
        prompt_version="core + appendix-gpt-4.1-mini",
    )
    _write_run(
        artifacts_root=root,
        eval_run_id="r_ant",
        model_name="claude-sonnet-4",
        per_items=[_item("q012", True)],
        outcome_counts={"success": 1},
        correct=1,
        prompt_version="core + appendix-claude-sonnet-4",
    )

    matrix, _ = BMM.build_matrix(
        iteration_id="iter_x_20260501",
        dataset=Path("datasets/eval_dataset_reviewed.json"),
        run_ids=["r_oai", "r_ant"],
        artifacts_root=root,
    )

    assert matrix["prompt_family_version"] == "core"
    # Top-level prompt_version must no longer leak any row's appendix.
    assert "prompt_version" not in matrix
    # Row-level prompt_version keeps the full `core + appendix` identifier.
    pvs = {r["prompt_version"] for r in matrix["rows"]}
    assert pvs == {
        "core + appendix-gpt-4.1-mini",
        "core + appendix-claude-sonnet-4",
    }


def test_matrix_flags_mixed_core_versions_visibly(tmp_path: Path) -> None:
    """If rows diverge on the core (not just the appendix), the top-level
    field must show the drift rather than silently picking rows[0]."""
    root = tmp_path / "artifacts" / "eval"
    _write_run(
        artifacts_root=root,
        eval_run_id="r_v1",
        model_name="gpt-4.1-mini",
        per_items=[_item("q012", True)],
        outcome_counts={"success": 1},
        correct=1,
        prompt_version="core + appendix-gpt-4.1-mini",
    )
    _write_run(
        artifacts_root=root,
        eval_run_id="r_v2",
        model_name="claude-sonnet-4",
        per_items=[_item("q012", True)],
        outcome_counts={"success": 1},
        correct=1,
        prompt_version="core-alt + appendix-claude-sonnet-4",
    )

    matrix, _ = BMM.build_matrix(
        iteration_id="iter_x_20260501",
        dataset=Path("datasets/eval_dataset_reviewed.json"),
        run_ids=["r_v1", "r_v2"],
        artifacts_root=root,
    )
    assert matrix["prompt_family_version"] == ["core", "core-alt"]


def test_legacy_bare_prompt_label_stays_as_family(tmp_path: Path) -> None:
    """Iteration 0 legacy runs have a bare `"phase1-v1"` (no `+ appendix`
    suffix). The family extractor should return it verbatim."""
    root = tmp_path / "artifacts" / "eval"
    _write_run(
        artifacts_root=root,
        eval_run_id="r_legacy",
        model_name="gpt-4.1-mini",
        per_items=[_item("q012", True)],
        outcome_counts={"success": 1},
        correct=1,
        prompt_version="phase1-v1",
    )
    matrix, _ = BMM.build_matrix(
        iteration_id="iter_0_baseline_20260424",
        dataset=Path("datasets/eval_dataset_reviewed.json"),
        run_ids=["r_legacy"],
        artifacts_root=root,
    )
    assert matrix["prompt_family_version"] == "phase1-v1"


def test_missing_run_raises(tmp_path: Path) -> None:
    root = tmp_path / "artifacts" / "eval"
    with pytest.raises(FileNotFoundError):
        BMM.build_matrix(
            iteration_id="iter_x_20260501",
            dataset=Path("datasets/eval_dataset_reviewed.json"),
            run_ids=["does_not_exist"],
            artifacts_root=root,
        )
