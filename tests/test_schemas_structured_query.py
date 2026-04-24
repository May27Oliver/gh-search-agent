"""Task 3.2 RED: StructuredQuery contract tests.

Covers SCHEMAS.md §1:
- all fields required (no defaults)
- unknown fields rejected
- keywords must be a list (never null)
- sort enum, order enum, limit 1..20, YYYY-MM-DD dates
- sort=null implies order=null
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from gh_search.schemas import StructuredQuery


def _valid_payload(**overrides):
    base = {
        "keywords": ["logistics", "optimization"],
        "language": "Python",
        "created_after": "2024-01-01",
        "created_before": None,
        "min_stars": 100,
        "max_stars": None,
        "sort": "stars",
        "order": "desc",
        "limit": 10,
    }
    base.update(overrides)
    return base


def test_valid_full_payload_parses():
    q = StructuredQuery.model_validate(_valid_payload())
    assert q.keywords == ["logistics", "optimization"]
    assert q.language == "Python"
    assert q.limit == 10


def test_unknown_field_rejected():
    payload = _valid_payload()
    payload["topic"] = "ai"
    with pytest.raises(ValidationError) as exc:
        StructuredQuery.model_validate(payload)
    assert "topic" in str(exc.value)


def test_keywords_null_rejected():
    with pytest.raises(ValidationError):
        StructuredQuery.model_validate(_valid_payload(keywords=None))


def test_keywords_empty_list_accepted():
    q = StructuredQuery.model_validate(_valid_payload(keywords=[]))
    assert q.keywords == []


def test_missing_required_field_rejected():
    payload = _valid_payload()
    del payload["limit"]
    with pytest.raises(ValidationError) as exc:
        StructuredQuery.model_validate(payload)
    assert "limit" in str(exc.value)


def test_missing_nullable_field_rejected():
    # null must be explicit per spec §1: "所有欄位都必須存在，未指定值用 null"
    payload = _valid_payload()
    del payload["language"]
    with pytest.raises(ValidationError) as exc:
        StructuredQuery.model_validate(payload)
    assert "language" in str(exc.value)


def test_invalid_sort_enum_rejected():
    with pytest.raises(ValidationError):
        StructuredQuery.model_validate(_valid_payload(sort="popularity"))


def test_invalid_order_enum_rejected():
    with pytest.raises(ValidationError):
        StructuredQuery.model_validate(_valid_payload(order="up"))


def test_limit_below_range_rejected():
    with pytest.raises(ValidationError):
        StructuredQuery.model_validate(_valid_payload(limit=0))


def test_limit_above_range_rejected():
    with pytest.raises(ValidationError):
        StructuredQuery.model_validate(_valid_payload(limit=21))


def test_date_format_validated():
    with pytest.raises(ValidationError):
        StructuredQuery.model_validate(_valid_payload(created_after="2024/01/01"))


def test_sort_null_requires_order_null():
    with pytest.raises(ValidationError) as exc:
        StructuredQuery.model_validate(_valid_payload(sort=None, order="desc"))
    assert "order" in str(exc.value).lower()


def test_sort_null_order_null_allowed():
    q = StructuredQuery.model_validate(_valid_payload(sort=None, order=None))
    assert q.sort is None
    assert q.order is None


def test_min_stars_negative_rejected():
    with pytest.raises(ValidationError):
        StructuredQuery.model_validate(_valid_payload(min_stars=-1))


def test_roundtrip_json():
    payload = _valid_payload()
    q = StructuredQuery.model_validate(payload)
    dumped = q.model_dump(mode="json")
    assert StructuredQuery.model_validate(dumped) == q
