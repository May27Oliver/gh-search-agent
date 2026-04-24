"""GitHub query compiler — pure domain service (TOOLS.md §8).

Maps a validated StructuredQuery to the GitHub Search API `q` parameter string.
sort / order / limit are HTTP params and are emitted by the GitHub client from
the same StructuredQuery; they are intentionally NOT part of the q string.
"""
from __future__ import annotations

from gh_search.schemas import StructuredQuery


def compile_github_query(sq: StructuredQuery) -> str:
    parts: list[str] = []
    if sq.keywords:
        parts.append(" ".join(sq.keywords))
    if sq.language is not None:
        parts.append(f"language:{sq.language}")
    if sq.created_after is not None:
        parts.append(f"created:>={sq.created_after}")
    if sq.created_before is not None:
        parts.append(f"created:<={sq.created_before}")
    if sq.min_stars is not None:
        parts.append(f"stars:>={sq.min_stars}")
    if sq.max_stars is not None:
        parts.append(f"stars:<={sq.max_stars}")
    return " ".join(parts)
