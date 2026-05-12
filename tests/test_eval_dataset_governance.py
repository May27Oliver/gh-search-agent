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
PARAPHRASE_DATASET = REPO_ROOT / "datasets" / "eval_dataset_paraphrase.json"
FORMAL_MANIFEST = REPO_ROOT / "datasets" / "formal_eval_qids.json"
AMBIGUOUS_MANIFEST = REPO_ROOT / "datasets" / "ambiguous_eval_qids.json"
FAILURE_MANIFEST = REPO_ROOT / "datasets" / "failure_eval_qids.json"
PARAPHRASE_MANIFEST = REPO_ROOT / "datasets" / "paraphrase_eval_qids.json"

SUPPORTED_NEEDS_REVISION_BUCKETS = frozenset(
    {"failure_case", "ambiguous_or_unexpressible"}
)

# (bucket name, source_dataset path string) keyed by manifest path.
EXPECTED_BUCKETS: dict[Path, tuple[str, str]] = {
    FORMAL_MANIFEST: ("formal_eval", "datasets/eval_dataset_reviewed.json"),
    AMBIGUOUS_MANIFEST: (
        "ambiguous_or_unexpressible_eval",
        "datasets/eval_dataset_reviewed.json",
    ),
    FAILURE_MANIFEST: ("failure_case_eval", "datasets/eval_dataset_reviewed.json"),
    PARAPHRASE_MANIFEST: ("paraphrase_eval", "datasets/eval_dataset_paraphrase.json"),
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


@pytest.mark.parametrize(
    "manifest_path,expected_bucket,expected_source",
    [
        (path, bucket, source)
        for path, (bucket, source) in EXPECTED_BUCKETS.items()
    ],
)
def test_manifest_schema(
    manifest_path: Path, expected_bucket: str, expected_source: str
) -> None:
    payload = _load_json(manifest_path)
    assert payload["bucket"] == expected_bucket
    assert payload["source_dataset"] == expected_source
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

    Uses the dataset-filtered loader so a future non-reviewed manifest in the
    same directory can't satisfy this check by accident.
    """
    from gh_search.eval.runner import _load_bucket_index

    bucket_index, _declared = _load_bucket_index(
        REPO_ROOT / "datasets", dataset_path=REVIEWED_DATASET
    )
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


# Paraphrase dataset governance — same shape of source-driven equality as the
# reviewed dataset's manifests, plus structural invariants specific to the
# many-to-one paraphrase contract: same ground truth across a cluster, and at
# least one token-level + one sentence-level rewrite per cluster.


@pytest.fixture(scope="module")
def paraphrase_items() -> list[dict]:
    payload = _load_json(PARAPHRASE_DATASET)
    return list(payload["items"])


@pytest.fixture(scope="module")
def paraphrase_qids() -> list[str]:
    return list(_load_json(PARAPHRASE_MANIFEST)["qids"])


def test_paraphrase_manifest_covers_dataset(
    paraphrase_items: list[dict], paraphrase_qids: list[str]
) -> None:
    """Manifest qids must equal the dataset's qid set — same source-driven
    equality contract as the reviewed manifests."""
    dataset_qids = {item["id"] for item in paraphrase_items}
    manifest_qids = set(paraphrase_qids)
    missing = dataset_qids - manifest_qids
    extra = manifest_qids - dataset_qids
    assert not missing and not extra, (
        "paraphrase manifest must equal the paraphrase dataset qid set. "
        f"missing from manifest: {sorted(missing)}; "
        f"extra in manifest: {sorted(extra)}"
    )


def test_paraphrase_qids_do_not_overlap_reviewed_manifests(
    paraphrase_qids: list[str],
    formal_qids: list[str],
    ambiguous_qids: list[str],
    failure_qids: list[str],
) -> None:
    """Paraphrase qids live in their own namespace and must not collide with
    any reviewed dataset bucket. Naming should prevent this, but it's cheap
    to pin so a future qid-naming change can't silently break governance."""
    paraphrase = set(paraphrase_qids)
    reviewed = set(formal_qids) | set(ambiguous_qids) | set(failure_qids)
    overlap = paraphrase & reviewed
    assert not overlap, (
        f"paraphrase qids must not overlap with reviewed-dataset buckets; "
        f"found overlap: {sorted(overlap)}"
    )


def test_intra_cluster_ground_truth_is_consistent(
    paraphrase_items: list[dict],
) -> None:
    """Every paraphrase in a cluster must share one canonical
    ``ground_truth_structured_query``. Without this, the cluster's all_match
    judgment becomes meaningless — paraphrases would be scored against
    different targets and "convergence" wouldn't measure anything stable."""
    by_cluster: dict[str, list[dict]] = {}
    for item in paraphrase_items:
        cluster_id = item.get("cluster_id")
        assert cluster_id is not None, (
            f"paraphrase item {item['id']!r} is missing cluster_id"
        )
        by_cluster.setdefault(cluster_id, []).append(item)

    for cluster_id, items in by_cluster.items():
        gts = [item.get("ground_truth_structured_query") for item in items]
        first = gts[0]
        for other_gt, item in zip(gts[1:], items[1:]):
            assert other_gt == first, (
                f"cluster {cluster_id!r} has inconsistent ground_truth_structured_query: "
                f"item {item['id']!r} disagrees with the cluster canonical target"
            )


def test_each_cluster_has_token_and_sentence_rewrites(
    paraphrase_items: list[dict],
) -> None:
    """Each cluster must include at least one token-level and one
    sentence-level rewrite, otherwise the cluster is just synonyms of one
    sentence shape and doesn't exercise the harder paraphrase failure mode
    (whole-sentence reordering)."""
    by_cluster: dict[str, set[str]] = {}
    for item in paraphrase_items:
        cluster_id = item["cluster_id"]
        by_cluster.setdefault(cluster_id, set()).add(item.get("rewrite_kind", ""))

    for cluster_id, kinds in by_cluster.items():
        assert "token" in kinds, (
            f"cluster {cluster_id!r} is missing a token-level rewrite "
            f"(rewrite_kind=token); found {sorted(kinds)}"
        )
        assert "sentence" in kinds, (
            f"cluster {cluster_id!r} is missing a sentence-level rewrite "
            f"(rewrite_kind=sentence); found {sorted(kinds)}"
        )


def test_paraphrase_items_have_paraphrase_eval_bucket_after_load() -> None:
    """End-to-end: when the runner loads the paraphrase dataset, every item
    must be tagged with bucket=paraphrase_eval via the manifest."""
    from gh_search.eval.runner import _load_eval_dataset

    dataset = _load_eval_dataset(PARAPHRASE_DATASET)
    assert dataset.items, "paraphrase dataset must contain items"
    for item in dataset.items:
        assert item["bucket"] == "paraphrase_eval", (
            f"item {item['id']!r} expected bucket=paraphrase_eval, got {item['bucket']!r}"
        )


# source_dataset filtering — when loading manifests for a specific dataset,
# only manifests whose source_dataset matches must be considered. Otherwise
# every sibling manifest in datasets/ pollutes the breakdown universe.


def test_load_bucket_index_filters_by_source_dataset(tmp_path: Path) -> None:
    """Two datasets in the same directory, each with its own manifest, must
    not see each other's buckets."""
    from gh_search.eval.runner import _load_bucket_index

    (tmp_path / "ds_a.json").write_text(json.dumps({"items": []}))
    (tmp_path / "ds_b.json").write_text(json.dumps({"items": []}))
    (tmp_path / "for_a_qids.json").write_text(json.dumps({
        "bucket": "bucket_a",
        "source_dataset": "datasets/ds_a.json",
        "qids": ["qid_for_a"],
    }))
    (tmp_path / "for_b_qids.json").write_text(json.dumps({
        "bucket": "bucket_b",
        "source_dataset": "datasets/ds_b.json",
        "qids": ["qid_for_b"],
    }))

    a_index, a_declared = _load_bucket_index(tmp_path, dataset_path=tmp_path / "ds_a.json")
    assert a_index == {"qid_for_a": "bucket_a"}
    assert a_declared == frozenset({"bucket_a"})

    b_index, b_declared = _load_bucket_index(tmp_path, dataset_path=tmp_path / "ds_b.json")
    assert b_index == {"qid_for_b": "bucket_b"}
    assert b_declared == frozenset({"bucket_b"})


def test_load_bucket_index_raises_when_source_dataset_missing_in_filtered_mode(
    tmp_path: Path,
) -> None:
    """When the caller binds the loader to a specific dataset, every
    manifest in the directory must declare ``source_dataset`` so the
    filter can decide. A manifest without it is treated as a governance
    bug — silently including it would re-introduce the phantom-bucket
    problem the filter exists to prevent."""
    from gh_search.eval.runner import _load_bucket_index

    (tmp_path / "ds.json").write_text(json.dumps({"items": []}))
    (tmp_path / "incomplete_qids.json").write_text(json.dumps({
        "bucket": "some_bucket",
        "qids": ["q"],
    }))

    with pytest.raises(ValueError, match="requires a 'source_dataset' string"):
        _load_bucket_index(tmp_path, dataset_path=tmp_path / "ds.json")


def test_load_bucket_index_without_dataset_filter_keeps_legacy_behaviour(
    tmp_path: Path,
) -> None:
    """When no ``dataset_path`` is given (governance tests that exercise
    loader invariants without dataset binding), the filter is bypassed and
    every well-formed manifest in the directory is loaded. The ``qids``
    list and bucket names must still be validated as usual."""
    from gh_search.eval.runner import _load_bucket_index

    (tmp_path / "a_qids.json").write_text(json.dumps({
        "bucket": "bucket_a", "qids": ["q1"],
    }))
    (tmp_path / "b_qids.json").write_text(json.dumps({
        "bucket": "bucket_b", "qids": ["q2"],
    }))

    index, declared = _load_bucket_index(tmp_path)
    assert index == {"q1": "bucket_a", "q2": "bucket_b"}
    assert declared == frozenset({"bucket_a", "bucket_b"})
