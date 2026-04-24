"""Retrieval logging & auditability (PHASE2_PLAN §3.1).

Locks in the PHASE2 acceptance criteria:

- `Repository.description` is populated from the GitHub payload so
  retrieval summaries can include `description`.
- Each eval session persists an independent `retrieved_repositories.json`
  next to the session's `run.json`.
- `per_item_results` carries `compiled_query`, a top-5
  `retrieved_repositories` summary, and `retrieved_repositories_path`
  pointing at the full artifact.
- Failed / rejected runs don't write bogus retrieval data.
- The full retrieval payload (not just `result_count`) is preserved.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import responses

from gh_search.eval.runner import run_smoke_eval
from gh_search.github import GitHubClient, Repository
from gh_search.llm import LLMResponse
from gh_search.retrieval import (
    build_retrieval_artifact,
    has_retrieval_data,
    summarize_repositories,
)
from gh_search.schemas import Execution, ExecutionStatus


SEARCH_URL = "https://api.github.com/search/repositories"


# ---------------------------------------------------------------------------
# GitHub client: description flows through normalization
# ---------------------------------------------------------------------------


@responses.activate
def test_github_client_populates_description_from_payload():
    responses.add(
        responses.GET,
        SEARCH_URL,
        json={
            "total_count": 1,
            "incomplete_results": False,
            "items": [
                {
                    "full_name": "octo/cat",
                    "html_url": "https://github.com/octo/cat",
                    "stargazers_count": 42,
                    "language": "Go",
                    "description": "feline adventures",
                }
            ],
        },
        status=200,
    )
    client = GitHubClient(token=None)
    repos = client.search_repositories(query="cats", sort=None, order=None, per_page=1)

    assert repos[0].description == "feline adventures"


@responses.activate
def test_github_client_description_defaults_to_none_when_missing():
    responses.add(
        responses.GET,
        SEARCH_URL,
        json={
            "total_count": 1,
            "incomplete_results": False,
            "items": [
                {
                    "full_name": "octo/cat",
                    "html_url": "https://github.com/octo/cat",
                    "stargazers_count": 1,
                    "language": None,
                }
            ],
        },
        status=200,
    )
    client = GitHubClient(token=None)
    repos = client.search_repositories(query="x", sort=None, order=None, per_page=1)
    assert repos[0].description is None


# ---------------------------------------------------------------------------
# retrieval helpers: summary + artifact shape
# ---------------------------------------------------------------------------


def _repo(name="a/b", desc="d"):
    return Repository(
        name=name,
        url=f"https://github.com/{name}",
        stars=100,
        language="Python",
        description=desc,
    )


def test_summarize_repositories_caps_at_top_five_by_default():
    repos = [_repo(f"a/b{i}") for i in range(10)]
    summary = summarize_repositories(repos)
    assert len(summary) == 5
    assert summary[0]["name"] == "a/b0"


def test_summarize_repositories_row_shape_has_required_fields():
    summary = summarize_repositories([_repo("a/b", "hello")])
    row = summary[0]
    assert set(row.keys()) == {"name", "url", "stars", "language", "description"}
    assert row["description"] == "hello"


def test_build_retrieval_artifact_preserves_full_payload():
    repos = [_repo(f"a/b{i}") for i in range(7)]
    execution = Execution(
        status=ExecutionStatus.SUCCESS, response_status=200, result_count=7
    )
    artifact = build_retrieval_artifact(
        repos=repos, compiled_query="rails stars:>100", execution=execution
    )
    assert artifact["compiled_query"] == "rails stars:>100"
    assert artifact["execution_status"] == "success"
    assert artifact["result_count"] == 7
    assert len(artifact["repositories"]) == 7  # full payload, not just top-5


def test_has_retrieval_data_only_true_for_success_or_no_results():
    success = Execution(status=ExecutionStatus.SUCCESS, response_status=200, result_count=3)
    no_res = Execution(status=ExecutionStatus.NO_RESULTS, response_status=200, result_count=0)
    failed = Execution(status=ExecutionStatus.FAILED, response_status=None, result_count=0)
    not_started = Execution(
        status=ExecutionStatus.NOT_STARTED, response_status=None, result_count=None
    )
    assert has_retrieval_data(success) is True
    assert has_retrieval_data(no_res) is True
    assert has_retrieval_data(failed) is False
    assert has_retrieval_data(not_started) is False


# ---------------------------------------------------------------------------
# End-to-end: eval runner writes per-session retrieval artifact
# ---------------------------------------------------------------------------


_LLM_SCRIPT = [
    # smoke_001: supported, parse react
    {"intent_status": "supported", "reason": None, "should_terminate": False},
    {
        "keywords": ["react", "component", "library"],
        "language": None,
        "created_after": None,
        "created_before": None,
        "min_stars": None,
        "max_stars": None,
        "sort": "stars",
        "order": "desc",
        "limit": 10,
    },
    # smoke_002: supported, parse logistics
    {"intent_status": "supported", "reason": None, "should_terminate": False},
    {
        "keywords": ["logistics", "optimization"],
        "language": "Python",
        "created_after": "2024-01-01",
        "created_before": None,
        "min_stars": 100,
        "max_stars": None,
        "sort": None,
        "order": None,
        "limit": 10,
    },
    # smoke_003: unsupported
    {"intent_status": "unsupported", "reason": "asks about tweets", "should_terminate": True},
]


def _scripted_llm():
    calls = iter(_LLM_SCRIPT)

    def fn(_sys, _user, _schema):
        payload = next(calls)
        return LLMResponse(raw_text=json.dumps(payload), parsed=payload)

    return fn


def _fake_github_with_many_repos(count: int = 8):
    g = MagicMock()
    g.search_repositories.return_value = [
        Repository(
            name=f"org/repo-{i}",
            url=f"https://github.com/org/repo-{i}",
            stars=100 - i,
            language="Python",
            description=f"desc {i}",
        )
        for i in range(count)
    ]
    return g


def test_eval_runner_writes_retrieval_artifact_per_session(tmp_path: Path):
    dataset = Path("datasets/smoke_eval_dataset.json")
    log_root = tmp_path / "logs"

    run_smoke_eval(
        dataset_path=dataset,
        llm=_scripted_llm(),
        github=_fake_github_with_many_repos(count=8),
        log_root=log_root,
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="smoke_retrieval_1",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )

    # Every session that reached GitHub must have a retrieval artifact.
    sessions = sorted((log_root / "sessions").iterdir())
    assert len(sessions) == 3

    reached_github = [s for s in sessions if (s / "retrieved_repositories.json").exists()]
    rejected = [s for s in sessions if not (s / "retrieved_repositories.json").exists()]
    assert len(reached_github) == 2  # smoke_001 + smoke_002
    assert len(rejected) == 1  # smoke_003 was rejected pre-execute

    artifact = json.loads((reached_github[0] / "retrieved_repositories.json").read_text())
    # Full payload, not just a count
    assert artifact["result_count"] == 8
    assert len(artifact["repositories"]) == 8
    assert artifact["compiled_query"] is not None
    assert artifact["repositories"][0]["description"] == "desc 0"


def test_per_item_results_carry_retrieval_summary_and_path(tmp_path: Path):
    dataset = Path("datasets/smoke_eval_dataset.json")
    log_root = tmp_path / "logs"

    run_smoke_eval(
        dataset_path=dataset,
        llm=_scripted_llm(),
        github=_fake_github_with_many_repos(count=8),
        log_root=log_root,
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="smoke_retrieval_2",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )

    entries = [
        json.loads(line)
        for line in (
            tmp_path / "eval" / "smoke_retrieval_2" / "per_item_results.jsonl"
        )
        .read_text()
        .strip()
        .splitlines()
    ]
    assert len(entries) == 3

    success_entries = [e for e in entries if e["final_outcome"] == "success"]
    assert success_entries, "expected at least one success row"

    for entry in success_entries:
        assert entry["compiled_query"]  # populated, not None
        # Summary capped at 5 entries
        assert len(entry["retrieved_repositories"]) == 5
        row = entry["retrieved_repositories"][0]
        assert set(row.keys()) == {"name", "url", "stars", "language", "description"}

        # Path is absolute and points at the session's artifact
        path = Path(entry["retrieved_repositories_path"])
        assert path.is_absolute()
        assert path.exists()
        assert path.name == "retrieved_repositories.json"
        assert path.parent.name == entry["session_id"]


def test_per_item_results_skip_retrieval_for_rejected_runs(tmp_path: Path):
    dataset = Path("datasets/smoke_eval_dataset.json")

    run_smoke_eval(
        dataset_path=dataset,
        llm=_scripted_llm(),
        github=_fake_github_with_many_repos(count=3),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="smoke_retrieval_3",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )

    entries = [
        json.loads(line)
        for line in (
            tmp_path / "eval" / "smoke_retrieval_3" / "per_item_results.jsonl"
        )
        .read_text()
        .strip()
        .splitlines()
    ]
    rejected = [e for e in entries if e["final_outcome"] == "rejected"]
    assert rejected
    for entry in rejected:
        assert entry["retrieved_repositories"] == []
        assert entry["retrieved_repositories_path"] is None
