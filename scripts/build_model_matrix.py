"""Aggregate existing eval runs into a model matrix artifact.

Produces the canonical cross-model iteration artifact required by
EVAL_GPT41MINI_20260424_PLAN §4.6:

  artifacts/eval/iterations/<iteration_id>/
    model_matrix.json
    model_matrix.md
    refs.json

This script is a **post-processing aggregator** — it reads existing
`artifacts/eval/<eval_run_id>/{model_summary,run_config,per_item_results}.json*`
files and does not drive the eval itself. The transitional role is spelled
out in §4.6: use this until `gh-search eval matrix` lands.

Usage:
    python scripts/build_model_matrix.py \\
        --iteration-id iter_0_baseline_20260424 \\
        --dataset datasets/eval_dataset_reviewed.json \\
        --runs eval_gpt41mini_20260424

    python scripts/build_model_matrix.py \\
        --iteration-id iter_1_gate_relax_20260428 \\
        --dataset datasets/eval_dataset_reviewed.json \\
        --runs eval_gpt41mini_iter1 eval_claude_sonnet4_iter1
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from gh_search.eval.scorer import score_item
from gh_search.llm.factory import PROVIDER_BY_MODEL
from gh_search.schemas import StructuredQuery

# `PROVIDER_BY_MODEL` is the single source of truth (PHASE2_PLAN §1.1,
# imported from `gh_search.llm.factory`). Used here as a fallback when a
# pre-Phase-2 `run_config.json` / `model_summary.json` lacks `provider_name`
# — Phase 2+ runners always persist it, so this path only covers legacy
# Iteration 0 artifacts.

# Fields listed in §10 per-field recall. These are the six the plan explicitly
# asks to track; the enum fields (sort/order) and `limit` are included below
# as `extra_field_recall` for completeness without bloating the main row shape.
CORE_FIELDS: tuple[str, ...] = (
    "keywords",
    "language",
    "created_after",
    "created_before",
    "min_stars",
    "max_stars",
)
EXTRA_FIELDS: tuple[str, ...] = ("sort", "order", "limit")

GOLDEN_IDS: tuple[str, ...] = ("q012", "q015", "q025")


@dataclass(frozen=True)
class RunPaths:
    eval_run_id: str
    run_dir: Path
    summary_path: Path
    run_config_path: Path
    per_item_path: Path

    @classmethod
    def from_run_id(cls, eval_run_id: str, artifacts_root: Path) -> "RunPaths":
        run_dir = artifacts_root / eval_run_id
        return cls(
            eval_run_id=eval_run_id,
            run_dir=run_dir,
            summary_path=run_dir / "model_summary.json",
            run_config_path=run_dir / "run_config.json",
            per_item_path=run_dir / "per_item_results.jsonl",
        )

    def check_exists(self) -> None:
        for p in (self.summary_path, self.per_item_path):
            if not p.is_file():
                raise FileNotFoundError(f"missing artifact: {p}")


def _load_per_items(path: Path) -> list[dict]:
    items = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        items.append(json.loads(raw))
    return items


def _per_field_recall(items: Iterable[dict]) -> tuple[dict[str, float], dict[str, float]]:
    """Compute per-field recall by re-running the scorer comparison.

    Denominator: items with a non-null ground_truth_structured_query (i.e.
    non-rejection items). Rejection cases do not contribute to field recall.
    Numerator: items where the field matched ground truth according to scorer.
    """
    core_hits = {f: 0 for f in CORE_FIELDS}
    extra_hits = {f: 0 for f in EXTRA_FIELDS}
    total = 0

    for item in items:
        gt_raw = item.get("ground_truth_structured_query")
        if gt_raw is None:
            continue
        total += 1
        pred_raw = item.get("predicted_structured_query")
        predicted = StructuredQuery.model_validate(pred_raw) if pred_raw else None

        eval_item = {
            "id": item.get("eval_item_id"),
            "ground_truth_structured_query": gt_raw,
            "expect_rejection": False,
        }
        score = score_item(
            eval_item=eval_item,
            predicted_query=predicted,
            actual_outcome=item.get("final_outcome", "success"),
            actual_terminate_reason=item.get("terminate_reason"),
        )
        for f in CORE_FIELDS:
            if score.field_results.get(f):
                core_hits[f] += 1
        for f in EXTRA_FIELDS:
            if score.field_results.get(f):
                extra_hits[f] += 1

    if total == 0:
        return ({f: 0.0 for f in CORE_FIELDS}, {f: 0.0 for f in EXTRA_FIELDS})
    return (
        {f: round(core_hits[f] / total, 4) for f in CORE_FIELDS},
        {f: round(extra_hits[f] / total, 4) for f in EXTRA_FIELDS},
    )


def _golden_passed(items: Iterable[dict]) -> tuple[str, list[str]]:
    passed: list[str] = []
    missing: list[str] = []
    by_id = {it.get("eval_item_id"): it for it in items}
    for gid in GOLDEN_IDS:
        it = by_id.get(gid)
        if it is None:
            missing.append(gid)
            continue
        if it.get("is_correct"):
            passed.append(gid)
    failed_or_missing = [g for g in GOLDEN_IDS if g not in passed]
    return f"{len(passed)}/{len(GOLDEN_IDS)}", failed_or_missing


def _row_for_run(paths: RunPaths) -> dict:
    paths.check_exists()
    summary = json.loads(paths.summary_path.read_text(encoding="utf-8"))
    run_config = (
        json.loads(paths.run_config_path.read_text(encoding="utf-8"))
        if paths.run_config_path.is_file()
        else {}
    )
    items = _load_per_items(paths.per_item_path)

    core_recall, extra_recall = _per_field_recall(items)
    golden_str, golden_failed = _golden_passed(items)
    outcomes = summary.get("outcome_counts", {})
    model_name = summary.get("model_name", "unknown")

    # Phase 2 runners always persist `provider_name` in both run_config
    # and summary; the static-map branch below is legacy-only (Iteration 0
    # artifacts that predate PHASE2_PLAN §3.0).
    provider = (
        run_config.get("provider_name")
        or summary.get("provider_name")
        or PROVIDER_BY_MODEL.get(model_name, "unknown")
    )

    return {
        "model_name": model_name,
        "provider": provider,
        "eval_run_id": paths.eval_run_id,
        "prompt_version": run_config.get("prompt_version"),
        "accuracy": round(summary.get("accuracy", 0.0), 4),
        "correct": summary.get("correct", 0),
        "total": summary.get("total", 0),
        "rejected": outcomes.get("rejected", 0),
        "no_results": outcomes.get("no_results", 0),
        "success": outcomes.get("success", 0),
        "golden_passed": golden_str,
        "golden_failed_or_missing": golden_failed,
        "per_field_recall": core_recall,
        "extra_field_recall": extra_recall,
    }


def build_matrix(
    iteration_id: str,
    dataset: Path,
    run_ids: list[str],
    artifacts_root: Path,
) -> tuple[dict, dict]:
    rows = [_row_for_run(RunPaths.from_run_id(rid, artifacts_root)) for rid in run_ids]

    providers = {r["provider"] for r in rows}
    cross_provider = len(providers - {"unknown"}) >= 2

    matrix = {
        "iteration_id": iteration_id,
        # Top-level advertises only the `core` prompt version shared across
        # rows — the per-model appendix stays on each row's `prompt_version`.
        # A prior version exposed `prompt_version: rows[0].prompt_version`,
        # which silently hid per-row appendix divergence in cross-provider
        # matrices (the aggregate looked like it was "only using gpt's
        # appendix" when in fact each row used its own).
        "prompt_family_version": _prompt_family_version(rows),
        "dataset": str(dataset),
        "dataset_size": rows[0].get("total", 0) if rows else 0,
        "cross_provider": cross_provider,
        "rows": rows,
    }
    refs = {
        "iteration_id": iteration_id,
        "eval_run_ids": run_ids,
        "artifact_paths": {
            r["model_name"]: str((artifacts_root / r["eval_run_id"]).resolve())
            for r in rows
        },
    }
    return matrix, refs


def _prompt_family_version(rows: list[dict]) -> str | list[str] | None:
    """Extract the shared `core` family part across rows.

    Row `prompt_version` typically looks like `"core + appendix-{model}"`;
    legacy rows may be a bare label like `"phase1-v1"`. We keep just the
    chunk before ` + ` so the top-level metadata describes what's actually
    shared across the matrix (the core prompt) without implying a single
    model's appendix applies to every row. If rows disagree on core,
    return the sorted list so the drift is visible rather than hidden.
    """
    families: set[str] = set()
    for r in rows:
        pv = r.get("prompt_version") or ""
        core = pv.split(" + ", 1)[0].strip()
        if core:
            families.add(core)
    if not families:
        return None
    if len(families) == 1:
        return next(iter(families))
    return sorted(families)


def _render_markdown(matrix: dict) -> str:
    rows = matrix["rows"]
    cp = "yes" if matrix.get("cross_provider") else "no (single provider — falsification incomplete)"
    family = matrix.get("prompt_family_version")
    if isinstance(family, list):
        family_str = ", ".join(f"`{f}`" for f in family) + " _(mixed)_"
    else:
        family_str = f"`{family}`"
    lines = [
        f"# Model Matrix — `{matrix['iteration_id']}`",
        "",
        f"- dataset: `{matrix['dataset']}` ({matrix['dataset_size']} items)",
        f"- prompt_family_version: {family_str}",
        f"- cross_provider: **{cp}**",
        "",
        "## Per-model summary",
        "",
        "| model | provider | prompt_version | accuracy | correct | rejected | no_results | golden_passed |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            "| `{m}` | {p} | `{pv}` | {acc:.2%} | {c}/{t} | {rej} | {nor} | {gp} |".format(
                m=r["model_name"],
                p=r["provider"],
                pv=r.get("prompt_version") or "—",
                acc=r["accuracy"],
                c=r["correct"],
                t=r["total"],
                rej=r["rejected"],
                nor=r["no_results"],
                gp=r["golden_passed"],
            )
        )

    lines += ["", "## Per-field recall (core §10)", "",
              "| model | keywords | language | created_after | created_before | min_stars | max_stars |",
              "|---|---|---|---|---|---|---|"]
    for r in rows:
        fr = r["per_field_recall"]
        lines.append(
            "| `{m}` | {k:.2%} | {l:.2%} | {ca:.2%} | {cb:.2%} | {mns:.2%} | {mxs:.2%} |".format(
                m=r["model_name"],
                k=fr["keywords"],
                l=fr["language"],
                ca=fr["created_after"],
                cb=fr["created_before"],
                mns=fr["min_stars"],
                mxs=fr["max_stars"],
            )
        )

    failed = [
        f"- `{r['model_name']}`: {', '.join(r['golden_failed_or_missing']) or 'all pass'}"
        for r in rows
    ]
    lines += ["", "## Golden cases (q012 / q015 / q025)", ""] + failed

    if not matrix.get("cross_provider"):
        lines += [
            "",
            "> **Warning**: matrix has rows from a single provider only. Plan §4.5 requires",
            "> cross-provider falsification before any model-specific prompt change is promoted",
            "> into the `core` prompt layer.",
        ]

    return "\n".join(lines) + "\n"


def write_matrix(out_dir: Path, matrix: dict, refs: dict) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "model_matrix.json").write_text(
        json.dumps(matrix, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "model_matrix.md").write_text(
        _render_markdown(matrix),
        encoding="utf-8",
    )
    (out_dir / "refs.json").write_text(
        json.dumps(refs, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Aggregate eval runs into a model matrix artifact")
    p.add_argument(
        "--iteration-id",
        required=True,
        help="e.g. iter_0_baseline_20260424 (format iter_{N}_{slug}_{YYYYMMDD})",
    )
    p.add_argument(
        "--dataset",
        required=True,
        type=Path,
        help="path to dataset json used by the eval runs",
    )
    p.add_argument(
        "--runs",
        required=True,
        nargs="+",
        help="one or more eval_run_ids under artifacts/eval/",
    )
    p.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("artifacts/eval"),
        help="root of per-run eval artifacts (default: artifacts/eval)",
    )
    p.add_argument(
        "--iterations-root",
        type=Path,
        default=Path("artifacts/eval/iterations"),
        help="root of iteration artifacts (default: artifacts/eval/iterations)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    matrix, refs = build_matrix(
        iteration_id=args.iteration_id,
        dataset=args.dataset,
        run_ids=args.runs,
        artifacts_root=args.artifacts_root,
    )
    out_dir = args.iterations_root / args.iteration_id
    write_matrix(out_dir, matrix, refs)

    n_rows = len(matrix["rows"])
    print(
        f"[{args.iteration_id}] wrote {n_rows} row(s) to {out_dir}/model_matrix.{{json,md}}"
    )
    if not matrix.get("cross_provider") and n_rows > 0:
        print(
            "  warning: single-provider matrix; §4.5 requires >=2 providers for falsification",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
