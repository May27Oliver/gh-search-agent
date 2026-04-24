"""Retrieval artifact shape (PHASE2_PLAN §3.1).

Centralizes how a session's GitHub search hits are serialized for both
human-audit artifacts and machine-aggregated per_item_results entries.
Separating summary (short, inline) from artifact (full, on-disk) keeps
per_item_results scannable without losing the full payload.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict

from gh_search.github import Repository
from gh_search.schemas import Execution, ExecutionStatus

DEFAULT_SUMMARY_LIMIT = 5


def summarize_repositories(
    repos: Iterable[Repository], limit: int = DEFAULT_SUMMARY_LIMIT
) -> list[dict]:
    return [_as_dict(r) for r in list(repos)[:limit]]


def build_retrieval_artifact(
    repos: Iterable[Repository],
    compiled_query: str | None,
    execution: Execution,
) -> dict:
    full = [_as_dict(r) for r in repos]
    return {
        "compiled_query": compiled_query,
        "execution_status": execution.status.value,
        "response_status": execution.response_status,
        "result_count": execution.result_count,
        "repositories": full,
    }


def _as_dict(repo: Repository) -> dict:
    data = asdict(repo)
    return {
        "name": data["name"],
        "url": data["url"],
        "stars": data["stars"],
        "language": data["language"],
        "description": data.get("description"),
    }


def has_retrieval_data(execution: Execution) -> bool:
    """Only `success` and `no_results` reached GitHub; others have no repos."""
    return execution.status in (ExecutionStatus.SUCCESS, ExecutionStatus.NO_RESULTS)
