"""Task 3.8 RED: smoke eval runner (EVAL.md §14, EVAL_EXECUTION_SPEC §9-§14)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from gh_search.eval.runner import run_smoke_eval
from gh_search.github import Repository
from gh_search.llm import LLMResponse


_LLM_SCRIPT = [
    # smoke_001: supported, parse react libs
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
    # smoke_003: unsupported intent
    {"intent_status": "unsupported", "reason": "asks about tweets", "should_terminate": True},
]


def _scripted_llm():
    import json

    calls = iter(_LLM_SCRIPT)

    def fn(_sys, _user, _schema):
        payload = next(calls)
        return LLMResponse(raw_text=json.dumps(payload), parsed=payload)

    return fn


def _fake_github():
    g = MagicMock()
    g.search_repositories.return_value = [
        Repository(name="a/b", url="https://github.com/a/b", stars=200, language="Python")
    ]
    return g


def test_smoke_runner_produces_summary_and_per_item(tmp_path: Path):
    dataset = Path("datasets/smoke_eval_dataset.json")
    log_root = tmp_path / "logs"
    eval_root = tmp_path / "eval"

    summary = run_smoke_eval(
        dataset_path=dataset,
        llm=_scripted_llm(),
        github=_fake_github(),
        log_root=log_root,
        eval_artifacts_root=eval_root,
        eval_run_id="smoke_run_1",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )

    assert summary.total == 3
    assert summary.correct == 3  # all three hand-scripted to match
    assert summary.accuracy == 1.0
    assert summary.model_name == "gpt-4.1-mini"

    # Per-model artifacts
    run_dir = eval_root / "smoke_run_1"
    assert (run_dir / "run_config.json").exists()
    assert (run_dir / "model_summary.json").exists()
    assert (run_dir / "per_item_results.json").exists()
    per_item = (run_dir / "per_item_results.jsonl").read_text().strip().splitlines()
    assert len(per_item) == 3
    for line in per_item:
        entry = json.loads(line)
        assert entry["eval_run_id"] == "smoke_run_1"
        assert entry["model_name"] == "gpt-4.1-mini"
        assert entry["is_correct"] is True
        assert "session_id" in entry and "run_id" in entry

    per_item_json = json.loads((run_dir / "per_item_results.json").read_text())
    assert len(per_item_json) == 3
    assert [entry["eval_item_id"] for entry in per_item_json] == ["smoke_001", "smoke_002", "smoke_003"]
    assert per_item_json == [json.loads(line) for line in per_item]


def test_smoke_runner_session_logs_per_item(tmp_path: Path):
    dataset = Path("datasets/smoke_eval_dataset.json")
    log_root = tmp_path / "logs"

    run_smoke_eval(
        dataset_path=dataset,
        llm=_scripted_llm(),
        github=_fake_github(),
        log_root=log_root,
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="smoke_run_2",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )

    sessions = list((log_root / "sessions").iterdir())
    assert len(sessions) == 3
    for s in sessions:
        assert (s / "run.json").exists()
        assert (s / "turns.jsonl").exists()
        assert (s / "final_state.json").exists()
        # eval_result.json required for eval runs per LOGGING.md §5
        assert (s / "eval_result.json").exists()


def test_smoke_runner_detects_wrong_prediction(tmp_path: Path):
    # LLM returns a non-matching query for item 1 to exercise incorrect path.
    bad_script = [
        {"intent_status": "supported", "reason": None, "should_terminate": False},
        {
            "keywords": ["wrong"],
            "language": None,
            "created_after": None,
            "created_before": None,
            "min_stars": None,
            "max_stars": None,
            "sort": None,
            "order": None,
            "limit": 10,
        },
        # item 2
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
        # item 3
        {
            "intent_status": "unsupported",
            "reason": "tweets",
            "should_terminate": True,
        },
    ]
    import json

    calls = iter(bad_script)

    def llm(_s, _u, _sc):
        payload = next(calls)
        return LLMResponse(raw_text=json.dumps(payload), parsed=payload)

    summary = run_smoke_eval(
        dataset_path=Path("datasets/smoke_eval_dataset.json"),
        llm=llm,
        github=_fake_github(),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="smoke_run_3",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )

    assert summary.total == 3
    assert summary.correct == 2
    assert summary.accuracy < 1.0


def test_smoke_runner_reports_outcome_categories(tmp_path: Path):
    summary = run_smoke_eval(
        dataset_path=Path("datasets/smoke_eval_dataset.json"),
        llm=_scripted_llm(),
        github=_fake_github(),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="smoke_run_4",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )

    # Must at least distinguish success, rejected, etc. per PHASE1_PLAN §3.8.
    assert "success" in summary.outcome_counts
    assert "rejected" in summary.outcome_counts
    assert summary.outcome_counts["success"] >= 1
    assert summary.outcome_counts["rejected"] >= 1
