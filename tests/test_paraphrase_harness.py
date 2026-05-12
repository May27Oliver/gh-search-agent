"""Paraphrase harness — runner-side cluster aggregation.

End-to-end checks that confirm the paraphrase contract:

- per-paraphrase scores still flow through the normal bucket aggregation
  (paraphrase_eval bucket gets per-item counts)
- per-cluster `cluster_breakdown` tracks the many-to-one judgment:
    * `all_match` only when every paraphrase matches GT
    * `predicted_variants` distinguishes "consistent but wrong" from
      "inconsistent across paraphrases"
- a paraphrase-only run leaves headline_* zeroed (no formal items),
  CLI surfaces that as "headline=n/a" rather than 0/0 (0.00%)

These tests use scripted LLM responses so cluster outcomes are
deterministic and we can assert exact counts.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gh_search.cli import main
from gh_search.eval.runner import run_smoke_eval
from gh_search.github import Repository
from gh_search.llm import LLMResponse
from gh_search.schemas import (
    Control,
    Execution,
    ExecutionStatus,
    IntentStatus,
    IntentionJudge,
    SharedAgentState,
    StructuredQuery,
    Validation,
)


PARAPHRASE_DATASET = Path("datasets/eval_dataset_paraphrase.json")


_STARS_LB_500_GT = {
    "keywords": ["react", "component", "library"],
    "language": None,
    "created_after": None,
    "created_before": None,
    "min_stars": 501,
    "max_stars": None,
    "sort": None,
    "order": None,
    "limit": 10,
}

_RANK_POP_GT = {
    "keywords": ["react", "component", "library"],
    "language": None,
    "created_after": None,
    "created_before": None,
    "min_stars": None,
    "max_stars": None,
    "sort": "stars",
    "order": "desc",
    "limit": 10,
}

_INTENT_SUPPORTED = {"intent_status": "supported", "reason": None, "should_terminate": False}


def _fake_github():
    g = MagicMock()
    g.search_repositories.return_value = [
        Repository(name="a/b", url="https://github.com/a/b", stars=600, language=None)
    ]
    return g


def _scripted_llm(script: list[dict]):
    """Build an LLMJsonCall that returns each scripted dict in order."""
    calls = iter(script)

    def fn(_sys, _user, _schema):
        payload = next(calls)
        return LLMResponse(raw_text=json.dumps(payload), parsed=payload)

    return fn


def _expand_for_all_correct() -> list[dict]:
    """Script the LLM to return correct intent + parse for every item.

    Dataset order: 4 stars_lower_bound_500 items, then 4 ranking_intent_popular.
    Each supported normal item consumes 2 LLM calls (intent + parse).
    """
    return [
        _INTENT_SUPPORTED, _STARS_LB_500_GT,
        _INTENT_SUPPORTED, _STARS_LB_500_GT,
        _INTENT_SUPPORTED, _STARS_LB_500_GT,
        _INTENT_SUPPORTED, _STARS_LB_500_GT,
        _INTENT_SUPPORTED, _RANK_POP_GT,
        _INTENT_SUPPORTED, _RANK_POP_GT,
        _INTENT_SUPPORTED, _RANK_POP_GT,
        _INTENT_SUPPORTED, _RANK_POP_GT,
    ]


def _fake_terminal_state(
    *, run_id: str, user_query: str, predicted: StructuredQuery
) -> SharedAgentState:
    """Build a synthetic terminal SharedAgentState that bypasses the real
    agent loop (and its hardening rules in validate_query). Used to drive
    the runner directly with a specific predicted query so cluster
    aggregation can be tested in isolation from parser behavior."""
    return SharedAgentState(
        run_id=run_id,
        turn_index=1,
        max_turns=5,
        user_query=user_query,
        intention_judge=IntentionJudge(
            intent_status=IntentStatus.SUPPORTED,
            reason=None,
            should_terminate=False,
        ),
        structured_query=predicted,
        validation=Validation(is_valid=True, errors=[], missing_required_fields=[]),
        compiled_query=None,
        execution=Execution(
            status=ExecutionStatus.SUCCESS,
            response_status=200,
            result_count=0,
        ),
        control=Control(next_tool=None, should_terminate=True, terminate_reason=None),
    )


def _make_loop_with_predictions(predictions_by_query: dict[str, dict]):
    """Return a fake `run_agent_loop` that yields a scripted prediction for
    each item, identified by `user_query`. Bypasses validate_query so the
    test controls the prediction exactly, including "wrong" ones the real
    hardening would otherwise rescue."""

    def fake_loop(**kwargs):
        user_query = kwargs["user_query"]
        if user_query not in predictions_by_query:
            raise AssertionError(
                f"test fixture missing prediction for user_query={user_query!r}"
            )
        return _fake_terminal_state(
            run_id=kwargs["run_id"],
            user_query=user_query,
            predicted=StructuredQuery.model_validate(predictions_by_query[user_query]),
        )

    return fake_loop


_STARS_LB_500_QUERIES = [
    "react component libraries with more than 500 stars",
    "react component libraries with over 500 stars",
    "react component libraries with > 500 stars",
    "找一些 star 超過 500 的 react component library",
]
_RANK_POP_QUERIES = [
    "popular react component libraries",
    "top react component libraries",
    "most starred react component libraries",
    "react component libraries ranked by stars",
]


def test_paraphrase_run_clusters_pass_when_all_paraphrases_correct(tmp_path: Path):
    summary = run_smoke_eval(
        dataset_path=PARAPHRASE_DATASET,
        llm=_scripted_llm(_expand_for_all_correct()),
        github=_fake_github(),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="paraphrase_all_correct",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )

    assert set(summary.cluster_breakdown) == {
        "stars_lower_bound_500",
        "ranking_intent_popular",
    }
    for cluster_id, stats in summary.cluster_breakdown.items():
        assert stats.total == 4, cluster_id
        assert stats.correct == 4, cluster_id
        assert stats.all_match is True, cluster_id
        assert stats.predicted_variants == 1, cluster_id


def test_paraphrase_cluster_fails_when_any_paraphrase_wrong(tmp_path: Path, monkeypatch):
    """One wrong paraphrase in cluster B → cluster B all_match=False,
    correct=3/4, predicted_variants=2.

    Bypasses the real agent loop via monkeypatch so validate_query's
    ranking-intent hardening rule can't rescue the wrong prediction —
    we are testing cluster aggregation, not parser robustness.
    """
    wrong_rank = {**_RANK_POP_GT, "keywords": ["nope"]}
    predictions = {
        _STARS_LB_500_QUERIES[0]: _STARS_LB_500_GT,
        _STARS_LB_500_QUERIES[1]: _STARS_LB_500_GT,
        _STARS_LB_500_QUERIES[2]: _STARS_LB_500_GT,
        _STARS_LB_500_QUERIES[3]: _STARS_LB_500_GT,
        _RANK_POP_QUERIES[0]: _RANK_POP_GT,
        _RANK_POP_QUERIES[1]: _RANK_POP_GT,
        _RANK_POP_QUERIES[2]: _RANK_POP_GT,
        _RANK_POP_QUERIES[3]: wrong_rank,  # last paraphrase fails
    }
    monkeypatch.setattr(
        "gh_search.eval.runner.run_agent_loop",
        _make_loop_with_predictions(predictions),
    )

    summary = run_smoke_eval(
        dataset_path=PARAPHRASE_DATASET,
        llm=_scripted_llm([]),  # unused — agent loop is mocked
        github=_fake_github(),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="paraphrase_one_wrong",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )

    cluster_a = summary.cluster_breakdown["stars_lower_bound_500"]
    cluster_b = summary.cluster_breakdown["ranking_intent_popular"]

    assert cluster_a.all_match is True
    assert cluster_a.correct == 4
    assert cluster_a.predicted_variants == 1

    assert cluster_b.all_match is False
    assert cluster_b.correct == 3
    assert cluster_b.total == 4
    assert cluster_b.predicted_variants == 2


def test_consistently_wrong_cluster_has_one_variant_but_no_match(
    tmp_path: Path, monkeypatch
):
    """Cluster A predictions are all identical but all wrong: all_match=False
    AND predicted_variants=1. Diagnostic signal that the parser is stable
    across paraphrases but the rule itself needs fixing — distinct from the
    "robustness failure" mode where predicted_variants>1.

    Bypasses the real agent loop so validate_query's star-bounds hardening
    rule can't rescue the wrong prediction.
    """
    consistent_wrong = {**_STARS_LB_500_GT, "keywords": ["nope"]}
    predictions = {
        _STARS_LB_500_QUERIES[0]: consistent_wrong,
        _STARS_LB_500_QUERIES[1]: consistent_wrong,
        _STARS_LB_500_QUERIES[2]: consistent_wrong,
        _STARS_LB_500_QUERIES[3]: consistent_wrong,
        _RANK_POP_QUERIES[0]: _RANK_POP_GT,
        _RANK_POP_QUERIES[1]: _RANK_POP_GT,
        _RANK_POP_QUERIES[2]: _RANK_POP_GT,
        _RANK_POP_QUERIES[3]: _RANK_POP_GT,
    }
    monkeypatch.setattr(
        "gh_search.eval.runner.run_agent_loop",
        _make_loop_with_predictions(predictions),
    )

    summary = run_smoke_eval(
        dataset_path=PARAPHRASE_DATASET,
        llm=_scripted_llm([]),
        github=_fake_github(),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="paraphrase_consistent_wrong",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )

    cluster_a = summary.cluster_breakdown["stars_lower_bound_500"]
    assert cluster_a.all_match is False
    assert cluster_a.correct == 0
    assert cluster_a.total == 4
    assert cluster_a.predicted_variants == 1


def test_paraphrase_run_does_not_populate_headline(tmp_path: Path):
    """Paraphrase-only dataset has no formal_eval items, so headline_* must
    stay at zero — paraphrase is its own robustness dimension and does not
    contribute to the main accuracy number."""
    summary = run_smoke_eval(
        dataset_path=PARAPHRASE_DATASET,
        llm=_scripted_llm(_expand_for_all_correct()),
        github=_fake_github(),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="paraphrase_headline_check",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )

    assert summary.headline_total == 0
    assert summary.headline_correct == 0
    assert summary.headline_accuracy == 0.0
    # processed_* still reflects every item that ran
    assert summary.processed_total == 8
    assert summary.processed_correct == 8


def test_model_summary_json_includes_cluster_breakdown(tmp_path: Path, monkeypatch):
    """`cluster_breakdown` must round-trip into model_summary.json so
    downstream consumers don't have to re-parse session artifacts."""
    wrong_rank = {**_RANK_POP_GT, "keywords": ["nope"]}
    predictions = {
        _STARS_LB_500_QUERIES[0]: _STARS_LB_500_GT,
        _STARS_LB_500_QUERIES[1]: _STARS_LB_500_GT,
        _STARS_LB_500_QUERIES[2]: _STARS_LB_500_GT,
        _STARS_LB_500_QUERIES[3]: _STARS_LB_500_GT,
        _RANK_POP_QUERIES[0]: _RANK_POP_GT,
        _RANK_POP_QUERIES[1]: _RANK_POP_GT,
        _RANK_POP_QUERIES[2]: _RANK_POP_GT,
        _RANK_POP_QUERIES[3]: wrong_rank,
    }
    monkeypatch.setattr(
        "gh_search.eval.runner.run_agent_loop",
        _make_loop_with_predictions(predictions),
    )

    run_smoke_eval(
        dataset_path=PARAPHRASE_DATASET,
        llm=_scripted_llm([]),
        github=_fake_github(),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="paraphrase_summary_json",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )
    payload = json.loads(
        (tmp_path / "eval" / "paraphrase_summary_json" / "model_summary.json").read_text()
    )
    assert "cluster_breakdown" in payload
    rank = payload["cluster_breakdown"]["ranking_intent_popular"]
    assert rank == {"total": 4, "correct": 3, "all_match": False, "predicted_variants": 2}


def test_per_item_jsonl_carries_cluster_id_and_rewrite_kind(tmp_path: Path):
    """Per-item artifact must surface cluster_id and rewrite_kind so future
    failure analysis can slice by paraphrase shape (token vs sentence vs
    multilingual) without re-loading the source dataset."""
    run_smoke_eval(
        dataset_path=PARAPHRASE_DATASET,
        llm=_scripted_llm(_expand_for_all_correct()),
        github=_fake_github(),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="paraphrase_per_item_bucket",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )
    lines = (
        tmp_path / "eval" / "paraphrase_per_item_bucket" / "per_item_results.jsonl"
    ).read_text().strip().splitlines()
    assert len(lines) == 8
    rewrite_kinds = set()
    for line in lines:
        entry = json.loads(line)
        assert entry["bucket"] == "paraphrase_eval"
        assert entry["cluster_id"] in {
            "stars_lower_bound_500",
            "ranking_intent_popular",
        }
        assert entry["rewrite_kind"] in {"canonical", "token", "sentence"}
        rewrite_kinds.add(entry["rewrite_kind"])
    # spec requirement: each cluster needs both token + sentence rewrites,
    # so all three kinds should be present across the dataset
    assert {"canonical", "token", "sentence"} <= rewrite_kinds


# CLI display-layer fix: when a dataset contains no formal_eval items,
# the headline=0/0 (0.00%) reading is misleading. Surface "n/a" instead.


@patch("gh_search.cli._resolve_llm")
@patch("gh_search.cli.GitHubClient")
@patch("gh_search.eval.runner.run_smoke_eval")
def test_cli_prints_headline_na_when_dataset_has_no_formal_items(
    mock_run_smoke_eval, mock_github_cls, mock_resolve_llm,
    monkeypatch, tmp_path, capsys,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    mock_resolve_llm.return_value = MagicMock(
        call=MagicMock(), provider_name="openai", model_name="gpt-4.1-mini",
    )
    mock_github_cls.return_value = MagicMock()
    mock_run_smoke_eval.return_value = MagicMock(
        eval_run_id="paraphrase_run",
        model_name="gpt-4.1-mini",
        processed_total=8,
        processed_correct=8,
        processed_accuracy=1.0,
        headline_total=0,
        headline_correct=0,
        headline_accuracy=0.0,
        outcome_counts={"success": 8},
        bucket_breakdown={},
        cluster_breakdown={},
    )

    rc = main(["smoke"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "headline=n/a" in out, f"expected n/a marker in output, got:\n{out}"
    # The misleading reading would be the literal "headline=0/0 (0.00%)" line;
    # checking the substring "(0.00%)" alone matches "(100.00%)" too, so be
    # precise about the failure mode we want to rule out.
    assert "headline=0/0" not in out, (
        f"misleading headline=0/0 must not appear when headline is n/a; output:\n{out}"
    )


@patch("gh_search.cli._resolve_llm")
@patch("gh_search.cli.GitHubClient")
@patch("gh_search.eval.runner.run_smoke_eval")
def test_cli_still_prints_headline_percent_when_dataset_has_formal_items(
    mock_run_smoke_eval, mock_github_cls, mock_resolve_llm,
    monkeypatch, tmp_path, capsys,
):
    """Sanity inverse: when headline_total > 0, the percent-style line stays."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    mock_resolve_llm.return_value = MagicMock(
        call=MagicMock(), provider_name="openai", model_name="gpt-4.1-mini",
    )
    mock_github_cls.return_value = MagicMock()
    mock_run_smoke_eval.return_value = MagicMock(
        eval_run_id="mixed_run",
        model_name="gpt-4.1-mini",
        processed_total=4,
        processed_correct=3,
        processed_accuracy=0.75,
        headline_total=2,
        headline_correct=2,
        headline_accuracy=1.0,
        outcome_counts={"success": 3, "rejected": 1},
        bucket_breakdown={},
        cluster_breakdown={},
    )

    main(["smoke"])
    out = capsys.readouterr().out
    assert "headline=2/2" in out
    assert "100.00%" in out
    assert "headline=n/a" not in out
