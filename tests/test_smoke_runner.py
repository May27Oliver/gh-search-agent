"""Task 3.8 RED: smoke eval runner (EVAL.md §14, EVAL_EXECUTION_SPEC §9-§14)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gh_search.eval.runner import _load_eval_dataset, run_smoke_eval
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

    # smoke items are not in any qid manifest, so they default to formal_eval —
    # processed_* and headline_* must match for a smoke run
    assert summary.processed_total == 3
    assert summary.processed_correct == 3
    assert summary.processed_accuracy == 1.0
    assert summary.headline_total == 3
    assert summary.headline_correct == 3
    assert summary.headline_accuracy == 1.0
    assert summary.model_name == "gpt-4.1-mini"
    assert summary.bucket_breakdown["formal_eval"].total == 3
    assert summary.bucket_breakdown["formal_eval"].correct == 3

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

    assert summary.processed_total == 3
    assert summary.processed_correct == 2
    assert summary.processed_accuracy < 1.0


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


# ITER5_DATE_TUNING_SPEC §8.1.2: dataset metadata pins the annotation
# reference date (q013/q017 annotate relative dates against 2026-04-23) and
# must be threaded through run_smoke_eval → run_agent_loop → parse_query.


def test_dataset_reference_date_matches_dataset_notes():
    dataset = _load_eval_dataset(Path("datasets/eval_dataset_reviewed.json"))
    assert dataset.reference_date == date(2026, 4, 23)


def test_load_eval_dataset_rejects_legacy_top_level_list(tmp_path: Path):
    dataset_path = tmp_path / "legacy.json"
    dataset_path.write_text(json.dumps([{"id": "x", "input_query": "q"}]))

    with pytest.raises(ValueError, match="dataset must be an object"):
        _load_eval_dataset(dataset_path)


def test_run_smoke_eval_passes_reference_date_to_loop(tmp_path: Path, monkeypatch):
    seen_reference_dates: list = []

    from gh_search.schemas import (
        Control,
        Execution,
        ExecutionStatus,
        IntentStatus,
        IntentionJudge,
        SharedAgentState,
        StructuredQuery,
        ToolName,
        Validation,
    )

    def fake_loop(**kwargs):
        seen_reference_dates.append(kwargs.get("reference_date"))
        # Build a minimal terminal state for the runner to serialize
        return SharedAgentState(
            run_id=kwargs["run_id"],
            turn_index=1,
            max_turns=kwargs.get("max_turns", 5),
            user_query=kwargs["user_query"],
            intention_judge=IntentionJudge(
                intent_status=IntentStatus.SUPPORTED,
                reason=None,
                should_terminate=False,
            ),
            structured_query=StructuredQuery(
                keywords=[],
                language=None,
                created_after=None,
                created_before=None,
                min_stars=None,
                max_stars=None,
                sort=None,
                order=None,
                limit=10,
            ),
            validation=Validation(is_valid=True, errors=[], missing_required_fields=[]),
            compiled_query=None,
            execution=Execution(
                status=ExecutionStatus.SUCCESS,
                response_status=200,
                result_count=0,
            ),
            control=Control(
                next_tool=None,
                should_terminate=True,
                terminate_reason=None,
            ),
        )

    monkeypatch.setattr("gh_search.eval.runner.run_agent_loop", fake_loop)

    run_smoke_eval(
        dataset_path=Path("datasets/smoke_eval_dataset.json"),
        llm=_scripted_llm(),
        github=_fake_github(),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="smoke_today_1",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )

    expected = _load_eval_dataset(Path("datasets/smoke_eval_dataset.json")).reference_date
    assert seen_reference_dates, "run_agent_loop not invoked"
    assert all(t == expected for t in seen_reference_dates), (
        f"expected all calls to get {expected}, got {seen_reference_dates}"
    )


# Bucket plumbing — runner reads qid manifests, attaches `bucket` to each
# in-memory item, and aggregates per-bucket so failure / ambiguous scores
# cannot pollute headline accuracy.


def test_load_eval_dataset_attaches_bucket_from_manifests():
    """Reviewed dataset items must carry the bucket their manifest assigns them."""
    dataset = _load_eval_dataset(Path("datasets/eval_dataset_reviewed.json"))
    by_id = {item["id"]: item for item in dataset.items}
    # 4 needs_revision qids land in failure_case_eval; rest land in formal_eval.
    assert by_id["q010"]["bucket"] == "failure_case_eval"
    assert by_id["q020"]["bucket"] == "failure_case_eval"
    assert by_id["q021"]["bucket"] == "failure_case_eval"
    assert by_id["q029"]["bucket"] == "failure_case_eval"
    assert by_id["q001"]["bucket"] == "formal_eval"
    assert by_id["q027"]["bucket"] == "formal_eval"


def test_load_eval_dataset_defaults_unmanifested_items_to_formal_eval():
    """Smoke dataset items have no manifest entry → fall back to formal_eval.

    This preserves the old smoke runner contract (every item counts toward
    headline) for ad-hoc / regression datasets that don't ship a manifest.
    """
    dataset = _load_eval_dataset(Path("datasets/smoke_eval_dataset.json"))
    for item in dataset.items:
        assert item["bucket"] == "formal_eval"


def _write_two_bucket_fixtures(tmp_path: Path) -> Path:
    """Create a synthetic 2-item dataset + matching manifests in tmp_path.

    item_a → formal_eval, item_b → failure_case_eval. Used to verify that a
    failure-bucket item answered wrong cannot pull headline accuracy down.
    """
    gt = {
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
    dataset_path = tmp_path / "two_bucket_dataset.json"
    dataset_path.write_text(json.dumps({
        "metadata": {},
        "items": [
            {
                "id": "item_a",
                "input_query": "react component libraries",
                "case_type": "normal",
                "language": "en",
                "ground_truth_structured_query": gt,
            },
            {
                "id": "item_b",
                "input_query": "react component libraries",
                "case_type": "normal",
                "language": "en",
                "ground_truth_structured_query": gt,
            },
        ],
    }))
    (tmp_path / "formal_eval_qids.json").write_text(json.dumps({
        "bucket": "formal_eval",
        "description": "synthetic",
        "source_dataset": str(dataset_path),
        "qids": ["item_a"],
    }))
    (tmp_path / "failure_eval_qids.json").write_text(json.dumps({
        "bucket": "failure_case_eval",
        "description": "synthetic",
        "source_dataset": str(dataset_path),
        "qids": ["item_b"],
    }))
    return dataset_path


def test_failure_bucket_wrong_answer_does_not_lower_headline(tmp_path: Path):
    """Headline accuracy must reflect formal bucket only.

    Scenario: item_a (formal) gets the right answer; item_b (failure) gets a
    wrong prediction. Headline must remain 1/1 = 100%, while processed drops
    to 1/2 = 50%.
    """
    dataset_path = _write_two_bucket_fixtures(tmp_path)

    correct_query = {
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
    wrong_query = {**correct_query, "keywords": ["nope"]}
    script = [
        # item_a: supported, parse correct
        {"intent_status": "supported", "reason": None, "should_terminate": False},
        correct_query,
        # item_b: supported, parse wrong
        {"intent_status": "supported", "reason": None, "should_terminate": False},
        wrong_query,
    ]
    calls = iter(script)

    def llm(_s, _u, _sc):
        payload = next(calls)
        return LLMResponse(raw_text=json.dumps(payload), parsed=payload)

    summary = run_smoke_eval(
        dataset_path=dataset_path,
        llm=llm,
        github=_fake_github(),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="bucket_run_1",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )

    assert summary.headline_total == 1
    assert summary.headline_correct == 1
    assert summary.headline_accuracy == 1.0

    assert summary.processed_total == 2
    assert summary.processed_correct == 1
    assert summary.processed_accuracy == 0.5

    assert summary.bucket_breakdown["formal_eval"].correct == 1
    assert summary.bucket_breakdown["formal_eval"].total == 1
    assert summary.bucket_breakdown["failure_case_eval"].correct == 0
    assert summary.bucket_breakdown["failure_case_eval"].total == 1


def test_model_summary_json_contains_legacy_and_new_fields(tmp_path: Path):
    """`model_summary.json` keeps legacy keys aliased to processed_* for
    backwards compat (build_model_matrix.py reads them) and adds explicit
    headline_* + bucket_breakdown."""
    run_smoke_eval(
        dataset_path=Path("datasets/smoke_eval_dataset.json"),
        llm=_scripted_llm(),
        github=_fake_github(),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="summary_shape_1",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )

    payload = json.loads(
        (tmp_path / "eval" / "summary_shape_1" / "model_summary.json").read_text()
    )
    # legacy aliases preserved
    assert payload["total"] == payload["processed_total"]
    assert payload["correct"] == payload["processed_correct"]
    assert payload["accuracy"] == payload["processed_accuracy"]
    # new explicit fields present
    assert "headline_total" in payload
    assert "headline_correct" in payload
    assert "headline_accuracy" in payload
    # bucket breakdown shape
    assert "bucket_breakdown" in payload
    assert "formal_eval" in payload["bucket_breakdown"]
    formal = payload["bucket_breakdown"]["formal_eval"]
    assert {"total", "correct", "accuracy"} <= set(formal)


def test_per_item_jsonl_carries_bucket_field(tmp_path: Path):
    run_smoke_eval(
        dataset_path=Path("datasets/smoke_eval_dataset.json"),
        llm=_scripted_llm(),
        github=_fake_github(),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="per_item_bucket_1",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )
    lines = (
        tmp_path / "eval" / "per_item_bucket_1" / "per_item_results.jsonl"
    ).read_text().strip().splitlines()
    assert lines, "per_item_results.jsonl should not be empty"
    for line in lines:
        entry = json.loads(line)
        assert entry["bucket"] == "formal_eval"


def test_eval_result_json_carries_bucket_field(tmp_path: Path):
    log_root = tmp_path / "logs"
    run_smoke_eval(
        dataset_path=Path("datasets/smoke_eval_dataset.json"),
        llm=_scripted_llm(),
        github=_fake_github(),
        log_root=log_root,
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="eval_result_bucket_1",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )
    sessions = list((log_root / "sessions").iterdir())
    assert sessions, "expected at least one session directory"
    for session_dir in sessions:
        payload = json.loads((session_dir / "eval_result.json").read_text())
        assert payload["bucket"] == "formal_eval"


def test_load_eval_dataset_carries_declared_buckets():
    """Reviewed dataset's three governance manifests declare three buckets;
    loader must surface them all (including the empty ambiguous bucket) so
    the runner can pre-populate breakdown entries. The paraphrase manifest
    sitting in the same directory must NOT leak in — its source_dataset
    points at a different dataset, so it's a phantom bucket here."""
    dataset = _load_eval_dataset(Path("datasets/eval_dataset_reviewed.json"))
    assert dataset.declared_buckets == frozenset({
        "formal_eval",
        "failure_case_eval",
        "ambiguous_or_unexpressible_eval",
    })


def test_load_eval_dataset_paraphrase_excludes_reviewed_buckets():
    """Symmetric guard: when loading the paraphrase dataset, the reviewed
    manifests must not leak in as phantom 0/0 buckets."""
    dataset = _load_eval_dataset(Path("datasets/eval_dataset_paraphrase.json"))
    assert dataset.declared_buckets == frozenset({"paraphrase_eval"})


def test_reviewed_run_bucket_breakdown_excludes_paraphrase_bucket(tmp_path: Path):
    """Regression: prior to source_dataset filtering, every manifest in
    ``datasets/`` was loaded for every run, so a reviewed-dataset run's
    bucket_breakdown contained a phantom ``paraphrase_eval: 0/0`` entry.
    This pins the fix end-to-end."""
    summary = run_smoke_eval(
        dataset_path=Path("datasets/smoke_eval_dataset.json"),
        llm=_scripted_llm(),
        github=_fake_github(),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="no_paraphrase_leak",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )
    assert "paraphrase_eval" not in summary.bucket_breakdown


def test_summary_includes_declared_but_empty_bucket(tmp_path: Path):
    """A bucket declared in manifests with zero qids must still appear in
    the summary (and model_summary.json) as 0/0/0.0, so downstream consumers
    don't have to disambiguate "missing key" from "no items"."""
    dataset_path = _write_two_bucket_fixtures(tmp_path)
    # Add a third manifest that declares a bucket with zero qids.
    (tmp_path / "ambiguous_eval_qids.json").write_text(json.dumps({
        "bucket": "ambiguous_or_unexpressible_eval",
        "description": "synthetic empty bucket",
        "source_dataset": str(dataset_path),
        "qids": [],
    }))

    correct_query = {
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
    script = [
        {"intent_status": "supported", "reason": None, "should_terminate": False},
        correct_query,
        {"intent_status": "supported", "reason": None, "should_terminate": False},
        correct_query,
    ]
    calls = iter(script)

    def llm(_s, _u, _sc):
        payload = next(calls)
        return LLMResponse(raw_text=json.dumps(payload), parsed=payload)

    summary = run_smoke_eval(
        dataset_path=dataset_path,
        llm=llm,
        github=_fake_github(),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="empty_bucket_run",
        model_name="gpt-4.1-mini",
        provider_name="openai",
    )

    empty = summary.bucket_breakdown.get("ambiguous_or_unexpressible_eval")
    assert empty is not None, (
        "declared bucket with zero qids must still appear in summary"
    )
    assert empty.total == 0
    assert empty.correct == 0
    assert empty.accuracy == 0.0

    payload = json.loads(
        (tmp_path / "eval" / "empty_bucket_run" / "model_summary.json").read_text()
    )
    assert "ambiguous_or_unexpressible_eval" in payload["bucket_breakdown"]
    assert payload["bucket_breakdown"]["ambiguous_or_unexpressible_eval"] == {
        "total": 0,
        "correct": 0,
        "accuracy": 0.0,
    }


def test_runner_raises_when_a_sibling_manifest_is_malformed(tmp_path: Path):
    """If a manifest in the dataset's sibling directory is broken, the runner
    must fail fast — silently skipping it would let the affected qids fall
    back to ``formal_eval`` and pollute headline accuracy."""
    dataset_path = _write_two_bucket_fixtures(tmp_path)
    # Corrupt the formal manifest written by the fixture helper.
    (tmp_path / "formal_eval_qids.json").write_text(json.dumps({
        "bucket": 42,  # invalid type
        "qids": ["item_a"],
    }))

    with pytest.raises(ValueError, match="invalid 'bucket' field"):
        _load_eval_dataset(dataset_path)


def test_run_smoke_eval_accepts_explicit_reference_date_override(tmp_path: Path, monkeypatch):
    seen_reference_dates: list = []

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

    def fake_loop(**kwargs):
        seen_reference_dates.append(kwargs.get("reference_date"))
        return SharedAgentState(
            run_id=kwargs["run_id"],
            turn_index=1,
            max_turns=kwargs.get("max_turns", 5),
            user_query=kwargs["user_query"],
            intention_judge=IntentionJudge(
                intent_status=IntentStatus.SUPPORTED,
                reason=None,
                should_terminate=False,
            ),
            structured_query=StructuredQuery(
                keywords=[],
                language=None,
                created_after=None,
                created_before=None,
                min_stars=None,
                max_stars=None,
                sort=None,
                order=None,
                limit=10,
            ),
            validation=Validation(is_valid=True, errors=[], missing_required_fields=[]),
            compiled_query=None,
            execution=Execution(
                status=ExecutionStatus.SUCCESS,
                response_status=200,
                result_count=0,
            ),
            control=Control(
                next_tool=None,
                should_terminate=True,
                terminate_reason=None,
            ),
        )

    monkeypatch.setattr("gh_search.eval.runner.run_agent_loop", fake_loop)

    override = date(2030, 1, 1)
    run_smoke_eval(
        dataset_path=Path("datasets/smoke_eval_dataset.json"),
        llm=_scripted_llm(),
        github=_fake_github(),
        log_root=tmp_path / "logs",
        eval_artifacts_root=tmp_path / "eval",
        eval_run_id="smoke_today_2",
        model_name="gpt-4.1-mini",
        provider_name="openai",
        reference_date=override,
    )

    assert all(t == override for t in seen_reference_dates)
