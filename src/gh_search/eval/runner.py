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
from datetime import datetime, timezone
from pathlib import Path

from gh_search.agent import run_agent_loop
from gh_search.cli import _derive_final_outcome
from gh_search.eval.scorer import score_item
from gh_search.github import GitHubClient, Repository
from gh_search.llm import LLMJsonCall
from gh_search.logger import SessionLogger
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


@dataclass(frozen=True)
class SmokeSummary:
    eval_run_id: str
    model_name: str
    provider_name: str
    total: int
    correct: int
    accuracy: float
    outcome_counts: dict[str, int]


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
) -> SmokeSummary:
    dataset = json.loads(Path(dataset_path).read_text())
    run_dir = eval_artifacts_root / eval_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if prompt_version is None:
        prompt_version = f"core-v1 + appendix-{model_name}-v1"

    _write_run_config(
        run_dir, dataset_path, model_name, provider_name, prompt_version, max_turns
    )

    per_item_path = run_dir / "per_item_results.jsonl"
    per_item_path.write_text("")
    per_item_json_path = run_dir / "per_item_results.json"

    outcome_counts: dict[str, int] = {}
    correct_count = 0
    per_item_entries: list[dict] = []

    with per_item_path.open("a", encoding="utf-8") as per_item_fp:
        for item in dataset:
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
            if score.is_correct:
                correct_count += 1

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

    total = len(dataset)
    accuracy = correct_count / total if total else 0.0
    summary = SmokeSummary(
        eval_run_id=eval_run_id,
        model_name=model_name,
        total=total,
        correct=correct_count,
        accuracy=accuracy,
        outcome_counts=outcome_counts,
        provider_name=provider_name,
    )

    (run_dir / "model_summary.json").write_text(
        json.dumps(
            {
                "eval_run_id": eval_run_id,
                "model_name": model_name,
                "provider_name": provider_name,
                "total": total,
                "correct": correct_count,
                "accuracy": accuracy,
                "outcome_counts": outcome_counts,
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
) -> None:
    (run_dir / "run_config.json").write_text(
        json.dumps(
            {
                "dataset_path": str(dataset_path),
                "model_name": model_name,
                "provider_name": provider_name,
                "prompt_version": prompt_version,
                "max_turns": max_turns,
                "started_at": _now(),
            },
            indent=2,
        )
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
    retrieved_summary = (
        summarize_repositories(retrieved_repos)
        if has_retrieval_data(final_state.execution)
        else []
    )
    return {
        "eval_run_id": eval_run_id,
        "eval_item_id": item["id"],
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
    run_log = RunLog(
        session_id=session_id,
        run_id=run_id,
        run_type="eval",
        user_query=item["input_query"],
        model_name=model_name,
        provider_name=provider_name,
        prompt_version=prompt_version,
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
    )
    (session_logger.session_dir / "eval_result.json").write_text(
        eval_result.model_dump_json(indent=2)
    )


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
