"""Eval dataset bucket governance.

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
bucket is derived from the source dataset's review fields. Adding a new
unstable question requires only updating the source's review_status — the
manifests and these tests catch the rest.
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


def test_runner_resolves_every_reviewed_qid_to_a_unique_bucket(
    reviewed_index: dict[str, dict],
) -> None:
    """The runner's manifest loader must cover every qid in the reviewed dataset.

    Without this guard, a qid that exists in source but not in any manifest would
    silently default to ``formal_eval`` inside the runner, polluting headline
    accuracy. The qid-equality tests above already pin this from the manifest
    side; this check pins it from the runner side so the loader cannot diverge.
    """
    from gh_search.eval.runner import _load_bucket_index

    bucket_index, _declared = _load_bucket_index(REPO_ROOT / "datasets")
    missing = [qid for qid in reviewed_index if qid not in bucket_index]
    assert not missing, (
        f"every qid in the reviewed dataset must be assigned to a manifest "
        f"bucket; runner-side loader did not find: {sorted(missing)}"
    )


# Strict-mode loader — malformed manifests must fail fast rather than fall
# back to ``formal_eval``, otherwise broken governance silently pollutes
# headline accuracy.


def test_load_bucket_index_raises_on_non_object_payload(tmp_path: Path) -> None:
    bad = tmp_path / "broken_qids.json"
    bad.write_text(json.dumps(["not", "an", "object"]))

    from gh_search.eval.runner import _load_bucket_index

    with pytest.raises(ValueError, match="must be a JSON object"):
        _load_bucket_index(tmp_path)


def test_load_bucket_index_raises_when_bucket_field_is_not_string(tmp_path: Path) -> None:
    bad = tmp_path / "broken_qids.json"
    bad.write_text(json.dumps({"bucket": 42, "qids": []}))

    from gh_search.eval.runner import _load_bucket_index

    with pytest.raises(ValueError, match="invalid 'bucket' field"):
        _load_bucket_index(tmp_path)


def test_load_bucket_index_raises_when_qids_field_is_missing(tmp_path: Path) -> None:
    bad = tmp_path / "broken_qids.json"
    bad.write_text(json.dumps({"bucket": "formal_eval"}))

    from gh_search.eval.runner import _load_bucket_index

    with pytest.raises(ValueError, match="invalid 'qids' field"):
        _load_bucket_index(tmp_path)


def test_load_bucket_index_raises_when_qids_field_is_not_list(tmp_path: Path) -> None:
    bad = tmp_path / "broken_qids.json"
    bad.write_text(json.dumps({"bucket": "formal_eval", "qids": "q001,q002"}))

    from gh_search.eval.runner import _load_bucket_index

    with pytest.raises(ValueError, match="invalid 'qids' field"):
        _load_bucket_index(tmp_path)


def test_load_bucket_index_raises_on_conflicting_qid_assignments(tmp_path: Path) -> None:
    (tmp_path / "a_qids.json").write_text(json.dumps({
        "bucket": "formal_eval", "qids": ["q001"],
    }))
    (tmp_path / "b_qids.json").write_text(json.dumps({
        "bucket": "failure_case_eval", "qids": ["q001"],
    }))

    from gh_search.eval.runner import _load_bucket_index

    with pytest.raises(ValueError, match="multiple manifests"):
        _load_bucket_index(tmp_path)


def test_load_bucket_index_returns_declared_buckets_including_empty_ones(
    tmp_path: Path,
) -> None:
    """A manifest declaring a bucket with zero qids must still surface that
    bucket name in `declared_buckets` — that is what lets the runner emit a
    0/0 entry for it instead of dropping the bucket from the breakdown."""
    (tmp_path / "formal_eval_qids.json").write_text(json.dumps({
        "bucket": "formal_eval", "qids": ["q001"],
    }))
    (tmp_path / "ambiguous_eval_qids.json").write_text(json.dumps({
        "bucket": "ambiguous_or_unexpressible_eval", "qids": [],
    }))

    from gh_search.eval.runner import _load_bucket_index

    qid_to_bucket, declared = _load_bucket_index(tmp_path)
    assert qid_to_bucket == {"q001": "formal_eval"}
    assert declared == frozenset({"formal_eval", "ambiguous_or_unexpressible_eval"})
