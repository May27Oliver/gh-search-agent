"""Smoke eval runner (EVAL.md §14, EVAL_EXECUTION_SPEC §9, §14).

One eval_item x one model = one full session run. Each item produces the
canonical session logs plus an eval_result.json; the runner aggregates
per_item_results.jsonl, a human-friendly per_item_results.json, and
model_summary.json.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from gh_search.agent import run_agent_loop
from gh_search.cli import _derive_final_outcome
from gh_search.eval.scorer import score_item
from gh_search.github import GitHubClient, Repository
from gh_search.llm import LLMJsonCall
from gh_search.logger import SessionLogger
from gh_search.normalizers import KEYWORD_RULES_VERSION, normalize_keywords
from gh_search.retrieval import (
    build_retrieval_artifact,
    has_retrieval_data,
    summarize_repositories,
)
from gh_search.schemas import (
    EvalResult,
    FinalState,
    RunLog,
    SharedAgentState,
    StructuredQuery,
)


HEADLINE_BUCKET = "formal_eval"


@dataclass(frozen=True)
class BucketStats:
    """單一 bucket 的成績統計（不可變）。

    為什麼要把單一 bucket 的成績單獨存起來：
    一份 eval 跑完之後，30 題會分散在不同 bucket（例如 `formal_eval`、
    `failure_case_eval`、`ambiguous_or_unexpressible_eval`）。每個 bucket
    本來就要用不同方式打分、不同方式報告：

    - `formal_eval`：算進 headline accuracy 的主分數
    - `failure_case_eval`：已知壞掉的題，**跑、紀錄，但不算 headline**
    - `ambiguous_or_unexpressible_eval`：保守處理是否正確，未來改 outcome-based

    如果只用一組 (total, correct, accuracy) 把所有題目加總起來，不穩定的題
    （例如語意無法被 schema 表達、或 reviewer 也標不出 ground truth 的題）
    會把分數拉低，但**外人看不出是模型差還是題目壞**。把每個 bucket 各自存
    一份 `BucketStats`，再交給 `SmokeSummary` 聚成 `headline_*`（只算
    formal）和 `processed_*`（全部 bucket）兩套，就能把這兩件事拆開看。

    這個 dataclass 只是「**一個 bucket 的成績**」的容器，沒有方法、沒有
    狀態 — frozen 確保它在 summary 構造完之後不會被誰偷改。
    """

    total: int
    correct: int
    accuracy: float


@dataclass(frozen=True)
class ClusterStats:
    """單一 paraphrase cluster 的成績（不可變）。

    Paraphrase 桶的核心契約是「同 cluster 裡每一句不同寫法都要落到同一個
    `StructuredQuery` target」。BucketStats 報的是每題 per-paraphrase 的
    對錯計數，但**真正在衡量 robustness 的單位是 cluster**：4 句改寫只要
    有一句歪掉，這個 cluster 就還沒被當作 robust。

    欄位語意：
    - ``total``：cluster 內 paraphrase 數量
    - ``correct``：對 GT exact match 的 paraphrase 數
    - ``all_match``：cluster 過關判準（所有 paraphrase 都對 GT 才 True）
    - ``predicted_variants``：cluster 內出現的相異預測數量。配合
      ``all_match`` 可以辨別：

      | all_match | predicted_variants | 含義 |
      | --------- | ------------------ | --- |
      | True      | 1                  | cluster 完美過關 |
      | False     | 1                  | 一致但錯：parser 規則本身要修 |
      | False     | >1                 | 不一致：robustness 不足，需加 alias / normalizer |

    判讀變數計算用 scorer 同一套 `normalize_keywords()`，所以
    ``[react, component]`` 和 ``[component, react]`` 算同一 variant；
    null prediction 視為自己的 variant。
    """

    cluster_id: str
    total: int
    correct: int
    all_match: bool
    predicted_variants: int


@dataclass(frozen=True)
class SmokeSummary:
    eval_run_id: str
    model_name: str
    provider_name: str
    processed_total: int
    processed_correct: int
    processed_accuracy: float
    headline_total: int
    headline_correct: int
    headline_accuracy: float
    outcome_counts: dict[str, int]
    bucket_breakdown: dict[str, BucketStats]
    cluster_breakdown: dict[str, ClusterStats]


@dataclass(frozen=True)
class EvalDataset:
    """Dataset payload plus optional metadata shared across every eval item.

    `declared_buckets` is the universe of bucket names declared by the
    sibling `*_qids.json` manifests, *including buckets whose qid list is
    empty*. Carrying this lets the runner pre-populate `bucket_breakdown`
    with 0/0 entries for declared-but-unused buckets, so downstream
    consumers never have to distinguish "missing key" from "no items".
    """

    items: list[dict]
    reference_date: date | None = None
    declared_buckets: frozenset[str] = frozenset()


def run_smoke_eval(
    dataset_path: Path,
    llm: LLMJsonCall,
    github: GitHubClient,
    log_root: Path,
    eval_artifacts_root: Path,
    eval_run_id: str,
    model_name: str,
    provider_name: str,
    prompt_version: str | None = None,
    max_turns: int = 5,
    reference_date: date | None = None,
) -> SmokeSummary:
    """Run the full agent loop for each dataset item and aggregate scores."""
    dataset = _load_eval_dataset(dataset_path)
    effective_reference_date = (
        reference_date if reference_date is not None else dataset.reference_date
    )
    run_dir = eval_artifacts_root / eval_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if prompt_version is None:
        prompt_version = f"core + appendix-{model_name}"

    _write_run_config(
        run_dir,
        dataset_path,
        model_name,
        provider_name,
        prompt_version,
        max_turns,
        effective_reference_date,
    )

    per_item_path = run_dir / "per_item_results.jsonl"
    per_item_path.write_text("")
    per_item_json_path = run_dir / "per_item_results.json"

    outcome_counts: dict[str, int] = {}
    bucket_totals: dict[str, list[int]] = {}
    # cluster_tallies[cluster_id] = {"total": int, "correct": int, "variant_keys": set}
    cluster_tallies: dict[str, dict] = {}
    per_item_entries: list[dict] = []

    with per_item_path.open("a", encoding="utf-8") as per_item_fp:
        for item in dataset.items:
            session_id = f"sess_{uuid.uuid4().hex[:12]}"
            run_id = f"run_{uuid.uuid4().hex[:12]}"
            session_logger = SessionLogger(session_id=session_id, log_root=log_root)

            started_at = _now()
            results: list[Repository] = []
            final_state = run_agent_loop(
                user_query=item["input_query"],
                run_id=run_id,
                llm=llm,
                github=github,
                max_turns=max_turns,
                results_sink=results,
                session_logger=session_logger,
                reference_date=effective_reference_date,
            )
            ended_at = _now()

            outcome = _derive_final_outcome(final_state)
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

            retrieval_artifact_path = None
            if has_retrieval_data(final_state.execution):
                payload = build_retrieval_artifact(
                    repos=results,
                    compiled_query=final_state.compiled_query,
                    execution=final_state.execution,
                )
                retrieval_artifact_path = session_logger.write_retrieval_artifact(payload)

            score = score_item(
                eval_item=item,
                predicted_query=final_state.structured_query,
                actual_outcome=outcome,
                actual_terminate_reason=(
                    final_state.control.terminate_reason.value
                    if final_state.control.terminate_reason is not None
                    else None
                ),
            )
            stats = bucket_totals.setdefault(score.bucket, [0, 0])
            stats[0] += 1
            if score.is_correct:
                stats[1] += 1

            cluster_id = item.get("cluster_id")
            if cluster_id is not None:
                tally = cluster_tallies.setdefault(
                    cluster_id,
                    {"total": 0, "correct": 0, "variant_keys": set()},
                )
                tally["total"] += 1
                if score.is_correct:
                    tally["correct"] += 1
                tally["variant_keys"].add(
                    _normalized_prediction_key(final_state.structured_query)
                )

            _write_session_finalization(
                session_logger=session_logger,
                session_id=session_id,
                run_id=run_id,
                item=item,
                final_state=final_state,
                started_at=started_at,
                ended_at=ended_at,
                outcome=outcome,
                model_name=model_name,
                provider_name=provider_name,
                prompt_version=prompt_version,
                predicted_query=final_state.structured_query,
                score=score,
            )

            entry = _per_item_entry(
                eval_run_id=eval_run_id,
                item=item,
                model_name=model_name,
                provider_name=provider_name,
                run_id=run_id,
                session_id=session_id,
                log_root=log_root,
                final_state=final_state,
                outcome=outcome,
                score=score,
                retrieved_repos=results,
                retrieval_artifact_path=retrieval_artifact_path,
            )
            per_item_entries.append(entry)
            per_item_fp.write(json.dumps(entry) + "\n")

    per_item_json_path.write_text(json.dumps(per_item_entries, indent=2))

    # Pre-populate every bucket the manifests declare (even with zero qids), so
    # downstream consumers don't have to disambiguate "missing key" from
    # "0 items". HEADLINE_BUCKET is always present so headline_* is always
    # well-defined; defensively also include any bucket that items actually
    # landed in (which should already be a subset of declared_buckets).
    all_bucket_names = (
        dataset.declared_buckets
        | {HEADLINE_BUCKET}
        | set(bucket_totals.keys())
    )
    bucket_breakdown: dict[str, BucketStats] = {}
    for name in sorted(all_bucket_names):
        if name in bucket_totals:
            t, c = bucket_totals[name]
            bucket_breakdown[name] = BucketStats(
                total=t, correct=c, accuracy=(c / t if t else 0.0)
            )
        else:
            bucket_breakdown[name] = BucketStats(total=0, correct=0, accuracy=0.0)
    processed_total = sum(stats.total for stats in bucket_breakdown.values())
    processed_correct = sum(stats.correct for stats in bucket_breakdown.values())
    processed_accuracy = processed_correct / processed_total if processed_total else 0.0
    headline = bucket_breakdown.get(
        HEADLINE_BUCKET, BucketStats(total=0, correct=0, accuracy=0.0)
    )

    cluster_breakdown: dict[str, ClusterStats] = {}
    for cluster_id, tally in sorted(cluster_tallies.items()):
        total = tally["total"]
        correct = tally["correct"]
        cluster_breakdown[cluster_id] = ClusterStats(
            cluster_id=cluster_id,
            total=total,
            correct=correct,
            all_match=(total > 0 and correct == total),
            predicted_variants=len(tally["variant_keys"]),
        )

    summary = SmokeSummary(
        eval_run_id=eval_run_id,
        model_name=model_name,
        provider_name=provider_name,
        processed_total=processed_total,
        processed_correct=processed_correct,
        processed_accuracy=processed_accuracy,
        headline_total=headline.total,
        headline_correct=headline.correct,
        headline_accuracy=headline.accuracy,
        outcome_counts=outcome_counts,
        bucket_breakdown=bucket_breakdown,
        cluster_breakdown=cluster_breakdown,
    )

    (run_dir / "model_summary.json").write_text(
        json.dumps(
            {
                "eval_run_id": eval_run_id,
                "model_name": model_name,
                "provider_name": provider_name,
                # legacy aliases — kept so build_model_matrix.py and other
                # downstream consumers keep working without changes
                "total": processed_total,
                "correct": processed_correct,
                "accuracy": processed_accuracy,
                # explicit "what we ran" — across every bucket
                "processed_total": processed_total,
                "processed_correct": processed_correct,
                "processed_accuracy": processed_accuracy,
                # explicit "headline accuracy" — formal_eval bucket only
                "headline_total": headline.total,
                "headline_correct": headline.correct,
                "headline_accuracy": headline.accuracy,
                "outcome_counts": outcome_counts,
                "bucket_breakdown": {
                    name: {
                        "total": stats.total,
                        "correct": stats.correct,
                        "accuracy": stats.accuracy,
                    }
                    for name, stats in bucket_breakdown.items()
                },
                "cluster_breakdown": {
                    cluster_id: {
                        "total": stats.total,
                        "correct": stats.correct,
                        "all_match": stats.all_match,
                        "predicted_variants": stats.predicted_variants,
                    }
                    for cluster_id, stats in cluster_breakdown.items()
                },
            },
            indent=2,
        )
    )

    return summary


def _write_run_config(
    run_dir: Path,
    dataset_path: Path,
    model_name: str,
    provider_name: str,
    prompt_version: str,
    max_turns: int,
    reference_date: date | None,
) -> None:
    """Persist eval-level metadata shared by every item in the run."""
    (run_dir / "run_config.json").write_text(
        json.dumps(
            {
                "dataset_path": str(dataset_path),
                "model_name": model_name,
                "provider_name": provider_name,
                "prompt_version": prompt_version,
                "max_turns": max_turns,
                "reference_date": (
                    reference_date.isoformat() if reference_date is not None else None
                ),
                "started_at": _now(),
            },
            indent=2,
        )
    )


def _load_bucket_index(
    manifests_dir: Path,
    dataset_path: Path | None = None,
) -> tuple[dict[str, str], frozenset[str]]:
    """Read every ``*_qids.json`` manifest in a directory.

    Returns ``(qid_to_bucket, declared_buckets)``:

    - ``qid_to_bucket``: mapping from qid to the bucket name that owns it
    - ``declared_buckets``: every bucket name declared by any manifest that
      passed the dataset filter, **including buckets whose qid list is empty**

    Manifests are the single source of truth for which bucket a qid lives in.
    Five classes of error must surface immediately rather than silently fall
    back to ``formal_eval`` (which would pollute headline accuracy):

    1. malformed manifest payload (not a JSON object)
    2. ``bucket`` field missing or not a string
    3. ``qids`` field missing or not a list
    4. when ``dataset_path`` is given: ``source_dataset`` field missing or
       not a string
    5. the same qid declared by two manifests with conflicting buckets

    Bucket isolation: when ``dataset_path`` is given, only manifests whose
    ``source_dataset`` basename matches ``dataset_path.name`` are loaded.
    Otherwise a paraphrase manifest sitting in the same directory as the
    reviewed-dataset manifests would inject ``paraphrase_eval`` into a
    reviewed-dataset run's ``bucket_breakdown`` as ``0/0`` — a phantom
    bucket that the dataset never had any items in. Passing ``None``
    keeps the legacy "load every manifest in the directory" behaviour,
    used by governance tests that exercise loader invariants without
    binding to a specific dataset.
    """
    qid_to_bucket: dict[str, str] = {}
    declared_buckets: set[str] = set()
    if not manifests_dir.exists():
        return qid_to_bucket, frozenset(declared_buckets)
    for path in sorted(manifests_dir.glob("*_qids.json")):
        with path.open(encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            raise ValueError(
                f"manifest {path} must be a JSON object, "
                f"got {type(payload).__name__}"
            )
        bucket = payload.get("bucket")
        if not isinstance(bucket, str):
            raise ValueError(
                f"manifest {path} has invalid 'bucket' field: expected str, "
                f"got {type(bucket).__name__}"
            )
        qids = payload.get("qids")
        if not isinstance(qids, list):
            raise ValueError(
                f"manifest {path} has invalid 'qids' field: expected list, "
                f"got {type(qids).__name__}"
            )
        if dataset_path is not None:
            source = payload.get("source_dataset")
            if not isinstance(source, str):
                raise ValueError(
                    f"manifest {path} requires a 'source_dataset' string "
                    f"when loaded for a specific dataset; "
                    f"got {type(source).__name__}"
                )
            if Path(source).name != Path(dataset_path).name:
                continue
        declared_buckets.add(bucket)
        for qid in qids:
            if qid in qid_to_bucket and qid_to_bucket[qid] != bucket:
                raise ValueError(
                    f"qid {qid!r} appears in multiple manifests with conflicting "
                    f"buckets: {qid_to_bucket[qid]!r} and {bucket!r}"
                )
            qid_to_bucket[qid] = bucket
    return qid_to_bucket, frozenset(declared_buckets)


def _load_eval_dataset(
    dataset_path: Path,
    manifests_dir: Path | None = None,
) -> EvalDataset:
    """Load eval dataset items plus optional file-level metadata.

    Each item dict is augmented with a ``bucket`` key sourced from qid manifests
    in ``manifests_dir`` (defaults to ``dataset_path.parent``). Items whose qid
    is not in any manifest fall back to ``formal_eval`` so smoke / ad-hoc
    datasets keep their original headline semantics.
    """
    raw = json.loads(Path(dataset_path).read_text())
    if not isinstance(raw, dict):
        raise ValueError(
            f"dataset must be an object with 'metadata' and 'items', got {type(raw).__name__}"
        )

    items = raw.get("items")
    if not isinstance(items, list):
        raise ValueError("dataset object must contain an 'items' list")

    metadata = raw.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("dataset metadata must be an object when present")

    reference_date_raw = metadata.get("reference_date")
    reference_date = (
        date.fromisoformat(reference_date_raw)
        if isinstance(reference_date_raw, str) and reference_date_raw
        else None
    )

    if manifests_dir is None:
        manifests_dir = Path(dataset_path).parent
    qid_to_bucket, declared_buckets = _load_bucket_index(
        manifests_dir, dataset_path=Path(dataset_path)
    )
    items_with_bucket = [
        {**item, "bucket": qid_to_bucket.get(item.get("id"), HEADLINE_BUCKET)}
        for item in items
    ]
    return EvalDataset(
        items=items_with_bucket,
        reference_date=reference_date,
        declared_buckets=declared_buckets,
    )


def _per_item_entry(
    *,
    eval_run_id: str,
    item: dict,
    model_name: str,
    provider_name: str,
    run_id: str,
    session_id: str,
    log_root: Path,
    final_state: SharedAgentState,
    outcome: str,
    score,
    retrieved_repos: list[Repository],
    retrieval_artifact_path: Path | None,
) -> dict:
    """Build the JSONL row emitted for one evaluated dataset item."""
    retrieved_summary = (
        summarize_repositories(retrieved_repos)
        if has_retrieval_data(final_state.execution)
        else []
    )
    return {
        "eval_run_id": eval_run_id,
        "eval_item_id": item["id"],
        "bucket": item.get("bucket", HEADLINE_BUCKET),
        "cluster_id": item.get("cluster_id"),
        "rewrite_kind": item.get("rewrite_kind"),
        "model_name": model_name,
        "provider_name": provider_name,
        "run_id": run_id,
        "session_id": session_id,
        "session_log_path": str((log_root / "sessions" / session_id).resolve()),
        "is_correct": score.is_correct,
        "score": score.score,
        "final_outcome": outcome,
        "terminate_reason": score.terminate_reason,
        "ground_truth_structured_query": item.get("ground_truth_structured_query"),
        "predicted_structured_query": (
            final_state.structured_query.model_dump(mode="json")
            if final_state.structured_query is not None
            else None
        ),
        "mismatch_reasons": score.mismatch_reasons,
        "compiled_query": final_state.compiled_query,
        "retrieved_repositories": retrieved_summary,
        "retrieved_repositories_path": (
            str(retrieval_artifact_path.resolve())
            if retrieval_artifact_path is not None
            else None
        ),
    }


def _write_session_finalization(
    *,
    session_logger: SessionLogger,
    session_id: str,
    run_id: str,
    item: dict,
    final_state: SharedAgentState,
    started_at: str,
    ended_at: str,
    outcome: str,
    model_name: str,
    provider_name: str,
    prompt_version: str,
    predicted_query: StructuredQuery | None,
    score,
) -> None:
    """Write `run.json`, `final_state.json`, and `eval_result.json` for one item."""
    run_log = RunLog(
        session_id=session_id,
        run_id=run_id,
        run_type="eval",
        user_query=item["input_query"],
        model_name=model_name,
        provider_name=provider_name,
        prompt_version=prompt_version,
        keyword_rules_version=KEYWORD_RULES_VERSION,
        final_outcome=outcome,
        terminate_reason=(
            final_state.control.terminate_reason.value
            if final_state.control.terminate_reason is not None
            else None
        ),
        started_at=started_at,
        ended_at=ended_at,
        log_version="1",
    )
    fs = FinalState(
        session_id=session_id,
        run_id=run_id,
        state_type="final",
        turn_index=final_state.turn_index,
        state_payload=final_state,
        created_at=ended_at,
    )
    session_logger.finalize(run_log=run_log, final_state=fs)

    gt_raw = item.get("ground_truth_structured_query")
    gt_model = StructuredQuery.model_validate(gt_raw) if gt_raw is not None else None
    eval_result = EvalResult(
        run_id=run_id,
        session_id=session_id,
        eval_item_id=item["id"],
        model_name=model_name,
        ground_truth_structured_query=gt_model,
        predicted_structured_query=predicted_query,
        score=score.score,
        is_correct=score.is_correct,
        created_at=_now(),
        bucket=item.get("bucket", HEADLINE_BUCKET),
        cluster_id=item.get("cluster_id"),
    )
    (session_logger.session_dir / "eval_result.json").write_text(
        eval_result.model_dump_json(indent=2)
    )


def _now() -> str:
    """Return the current UTC timestamp in ISO 8601 form."""
    return datetime.now(tz=timezone.utc).isoformat()


def _normalized_prediction_key(query: StructuredQuery | None) -> tuple:
    """Return a hashable key representing a prediction for variant counting.

    Two predictions hash to the same key iff they are equivalent under the
    scorer's normalization rules — keywords are routed through
    ``normalize_keywords()`` then sorted, and enum values are unwrapped.
    A ``None`` prediction (parser refused / errored) gets its own marker so
    it counts as a distinct variant. Used by paraphrase cluster aggregation
    to compute ``predicted_variants``.
    """
    if query is None:
        return ("__no_prediction__",)
    keywords = tuple(
        sorted(normalize_keywords(list(query.keywords), language=query.language))
    )
    return (
        keywords,
        (query.language or "").lower() if query.language else None,
        query.created_after,
        query.created_before,
        query.min_stars,
        query.max_stars,
        query.sort.value if query.sort is not None else None,
        query.order.value if query.order is not None else None,
        query.limit,
    )
