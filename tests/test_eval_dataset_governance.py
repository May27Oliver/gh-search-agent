"""Eval dataset bucket governance (SEMANTIC_PARSING_HARNESS_PR_PLAN PR1).

Source-driven equality between qid manifests and the reviewed dataset:

- formal manifest      == every qid with review_status=approved
- failure manifest     == every qid with review_status=needs_revision and
                          recommended_dataset=failure_case
- ambiguous manifest   == every qid with review_status=needs_revision and
                          recommended_dataset=ambiguous_or_unexpressible

Plus three structural invariants:

- the three manifests are disjoint
- every qid named in a manifest resolves to an item in the reviewed dataset
- every needs_revision item in source declares a supported
  recommended_dataset (governance leak guard — without this, an entry
  with review_status=needs_revision but no recommended_dataset would slip
  past all three equality tests)

These tests deliberately do not name any qid string; the membership of each
bucket is derived from the source dataset's review fields. Adding a fifth
unstable question requires only updating the source's review_status — the
manifests and these tests catch the rest.

PR1 also does not touch the runner / scorer; the cutover is PR2 (Eval
Bucket Plumbing).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEWED_DATASET = REPO_ROOT / "datasets" / "eval_dataset_reviewed.json"
FORMAL_MANIFEST = REPO_ROOT / "datasets" / "formal_eval_qids.json"
AMBIGUOUS_MANIFEST = REPO_ROOT / "datasets" / "ambiguous_eval_qids.json"
FAILURE_MANIFEST = REPO_ROOT / "datasets" / "failure_eval_qids.json"

SUPPORTED_NEEDS_REVISION_BUCKETS = frozenset(
    {"failure_case", "ambiguous_or_unexpressible"}
)

EXPECTED_BUCKETS: dict[Path, str] = {
    FORMAL_MANIFEST: "formal_eval",
    AMBIGUOUS_MANIFEST: "ambiguous_or_unexpressible_eval",
    FAILURE_MANIFEST: "failure_case_eval",
}


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def reviewed_index() -> dict[str, dict]:
    payload = _load_json(REVIEWED_DATASET)
    return {item["id"]: item for item in payload["items"]}


@pytest.fixture(scope="module")
def formal_qids() -> list[str]:
    return list(_load_json(FORMAL_MANIFEST)["qids"])


@pytest.fixture(scope="module")
def ambiguous_qids() -> list[str]:
    return list(_load_json(AMBIGUOUS_MANIFEST)["qids"])


@pytest.fixture(scope="module")
def failure_qids() -> list[str]:
    return list(_load_json(FAILURE_MANIFEST)["qids"])


@pytest.mark.parametrize("manifest_path,expected_bucket", list(EXPECTED_BUCKETS.items()))
def test_manifest_schema(manifest_path: Path, expected_bucket: str) -> None:
    payload = _load_json(manifest_path)
    assert payload["bucket"] == expected_bucket
    assert payload["source_dataset"] == "datasets/eval_dataset_reviewed.json"
    assert isinstance(payload["qids"], list)
    assert all(isinstance(q, str) for q in payload["qids"])
    assert len(payload["qids"]) == len(set(payload["qids"])), "qids must be unique"


def test_formal_equals_approved_set(
    formal_qids: list[str], reviewed_index: dict[str, dict]
) -> None:
    approved = {
        qid for qid, item in reviewed_index.items()
        if item["review_status"] == "approved"
    }
    formal = set(formal_qids)
    missing = approved - formal
    extra = formal - approved
    assert not missing and not extra, (
        "formal manifest must equal the approved set in source. "
        f"missing from formal: {sorted(missing)}; "
        f"extra in formal: {sorted(extra)}"
    )


def test_failure_equals_failure_case_recommendations(
    failure_qids: list[str], reviewed_index: dict[str, dict]
) -> None:
    expected = {
        qid for qid, item in reviewed_index.items()
        if item["review_status"] == "needs_revision"
        and item.get("recommended_dataset") == "failure_case"
    }
    failure = set(failure_qids)
    missing = expected - failure
    extra = failure - expected
    assert not missing and not extra, (
        "failure manifest must equal the needs_revision items recommended "
        "for failure_case. "
        f"missing from failure: {sorted(missing)}; "
        f"extra in failure: {sorted(extra)}"
    )


def test_ambiguous_equals_ambiguous_recommendations(
    ambiguous_qids: list[str], reviewed_index: dict[str, dict]
) -> None:
    expected = {
        qid for qid, item in reviewed_index.items()
        if item["review_status"] == "needs_revision"
        and item.get("recommended_dataset") == "ambiguous_or_unexpressible"
    }
    ambiguous = set(ambiguous_qids)
    missing = expected - ambiguous
    extra = ambiguous - expected
    assert not missing and not extra, (
        "ambiguous manifest must equal the needs_revision items recommended "
        "for ambiguous_or_unexpressible. "
        f"missing from ambiguous: {sorted(missing)}; "
        f"extra in ambiguous: {sorted(extra)}"
    )


def test_every_needs_revision_qid_has_supported_recommendation(
    reviewed_index: dict[str, dict],
) -> None:
    unresolved = {
        qid: item.get("recommended_dataset")
        for qid, item in reviewed_index.items()
        if item["review_status"] == "needs_revision"
        and item.get("recommended_dataset") not in SUPPORTED_NEEDS_REVISION_BUCKETS
    }
    assert not unresolved, (
        "every needs_revision item must declare a supported recommended_dataset "
        f"(one of {sorted(SUPPORTED_NEEDS_REVISION_BUCKETS)}); found unresolved: "
        f"{unresolved}"
    )


def test_buckets_are_disjoint(
    formal_qids: list[str], ambiguous_qids: list[str], failure_qids: list[str]
) -> None:
    formal = set(formal_qids)
    ambiguous = set(ambiguous_qids)
    failure = set(failure_qids)
    assert formal.isdisjoint(ambiguous), (
        f"formal/ambiguous overlap: {sorted(formal & ambiguous)}"
    )
    assert formal.isdisjoint(failure), (
        f"formal/failure overlap: {sorted(formal & failure)}"
    )
    assert ambiguous.isdisjoint(failure), (
        f"ambiguous/failure overlap: {sorted(ambiguous & failure)}"
    )


def test_all_manifest_qids_resolve(
    formal_qids: list[str],
    ambiguous_qids: list[str],
    failure_qids: list[str],
    reviewed_index: dict[str, dict],
) -> None:
    for qid in (*formal_qids, *ambiguous_qids, *failure_qids):
        assert qid in reviewed_index, f"{qid} is not present in reviewed dataset"
