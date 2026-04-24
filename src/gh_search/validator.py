"""Semantic validator for StructuredQuery (TOOLS.md §9).

Schema-level checks (types, enums, required fields, date format, sort/order
consistency) live in StructuredQuery itself. This module only carries the
remaining semantic invariants.
"""
from __future__ import annotations

from gh_search.schemas import StructuredQuery, Validation


def validate_structured_query(sq: StructuredQuery) -> Validation:
    errors: list[str] = []

    if sq.min_stars is not None and sq.max_stars is not None and sq.min_stars > sq.max_stars:
        errors.append(
            f"min_stars ({sq.min_stars}) must be <= max_stars ({sq.max_stars})"
        )

    if (
        sq.created_after is not None
        and sq.created_before is not None
        and sq.created_after > sq.created_before
    ):
        errors.append(
            f"created_after ({sq.created_after}) must be <= created_before ({sq.created_before})"
        )

    if _has_no_effective_condition(sq):
        errors.append("at least one effective search condition is required")

    return Validation(is_valid=not errors, errors=errors, missing_required_fields=[])


def _has_no_effective_condition(sq: StructuredQuery) -> bool:
    return (
        not sq.keywords
        and sq.language is None
        and sq.created_after is None
        and sq.created_before is None
        and sq.min_stars is None
        and sq.max_stars is None
    )
