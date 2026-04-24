"""Deterministic normalizers for structured query fields.

Single source of truth (KEYWORD_TUNING_SPEC §8) — parser, validator, repair,
scorer, and logs must all go through this package for keyword canonicalization
instead of rolling their own lowercase / sort / merge logic.
"""
from gh_search.normalizers.keyword_rules import (
    KEYWORD_RULES_VERSION,
    ValidationIssue,
    canonicalize_keyword_token,
    find_keyword_violations,
    normalize_keywords,
)

__all__ = [
    "KEYWORD_RULES_VERSION",
    "ValidationIssue",
    "canonicalize_keyword_token",
    "find_keyword_violations",
    "normalize_keywords",
]
