"""Keyword canonicalization — single entry point (KEYWORD_TUNING_SPEC §8).

`normalize_keywords` and `find_keyword_violations` are the only functions that
may rewrite or flag `StructuredQuery.keywords`. Parser post-processing, the
validate_query tool, the repair_query tool, the scorer, and run/turn artifacts
all share this module — no local lowercase, sort, merge, or lemmatize is
allowed elsewhere (§8.3).
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field

KEYWORD_RULES_VERSION = "kw-rules-v1"


class ValidationIssue(BaseModel):
    """Structured validation output shared by all validators (§8.0.5)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(...)
    message: str = Field(...)
    field: str | None = None
    token: str | None = None
    replacement: str | None = None


# ---------------------------------------------------------------------------
# Frozen dictionaries (§4.2.1, §5.2, §6, §7.2)
# ---------------------------------------------------------------------------

_PLURAL_MAP: Mapping[str, str] = MappingProxyType(
    {
        "frameworks": "framework",
        "libraries": "library",
        "libs": "library",
        "engines": "engine",
        "examples": "example",
        "utilities": "utility",
    }
)

_ALIAS_MAP: Mapping[str, str] = MappingProxyType(
    {
        # typo canonicalization
        "pythn": "python",
        "javscript": "javascript",
        "frameework": "framework",
        "rect": "react",
        "aftr": "after",
        "starz": "stars",
        "strs": "stars",
        "repoz": "repos",
        # abbreviation canonicalization
        "js": "javascript",
        "ts": "typescript",
        "py": "python",
        "rb": "ruby",
        "pg": "postgresql",
        "postgres": "postgresql",
        # multilingual canonicalization (§7.2)
        "爬蟲": "scraping",
        "框架": "framework",
        "微服务": "microservice",
        "熱門": "popular",
        "排序": "sorted",
        "サンプル": "sample",
        "プロジェクト": "project",
        "日本語": "japanese",
    }
)

# Language names that must not appear in `keywords` when `language` facet is
# set to the matching value (§6.1). Values are canonical GitHub language names.
_LANGUAGE_TOKEN_TO_FACET: Mapping[str, str] = MappingProxyType(
    {
        "python": "Python",
        "py": "Python",
        "javascript": "JavaScript",
        "js": "JavaScript",
        "typescript": "TypeScript",
        "ts": "TypeScript",
        "java": "Java",
        "kotlin": "Kotlin",
        "swift": "Swift",
        "go": "Go",
        "golang": "Go",
        "rust": "Rust",
        "ruby": "Ruby",
        "c++": "C++",
        "cpp": "C++",
        "c#": "C#",
    }
)

# Modifier stopwords that never belong in `keywords` (§3.2, §6.2).
_MODIFIER_STOPWORDS: frozenset[str] = frozenset(
    {
        "popular",
        "top",
        "best",
        "trending",
        "recent",
        "newest",
        "cool",
        "good",
        "small",
        "open source",
        "most starred",
        "ranked by stars",
        "sorted by stars",
    }
)

# Technical phrases that must stay as a single keyword if present or be
# re-assembled from adjacent split tokens (§4.2.1).
_TECHNICAL_PHRASES: tuple[str, ...] = (
    "ruby on rails",
    "spring boot",
    "react native",
    "react component",
    "vue 3",
    "state management",
    "machine learning",
    "graphql server",
    "game engine",
    "web framework",
    "admin dashboard",
    "ui kit",
    "microservice framework",
    "chatbot library",
    "testing framework",
    "orm library",
)

# Longest-first ordering so bag-style merging consumes "ruby on rails" before
# any shorter subsequence has a chance to split it.
_PHRASES_LONGEST_FIRST: tuple[tuple[str, ...], ...] = tuple(
    tuple(phrase.split())
    for phrase in sorted(_TECHNICAL_PHRASES, key=lambda p: -len(p.split()))
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def canonicalize_keyword_token(token: str) -> str:
    """Lowercase + trim + apply alias / plural maps to a single token or phrase."""
    base = token.strip().lower()
    if not base:
        return ""
    if base in _ALIAS_MAP:
        base = _ALIAS_MAP[base]
    if base in _PLURAL_MAP:
        base = _PLURAL_MAP[base]
    return base


def normalize_keywords(
    keywords: list[str],
    *,
    language: str | None = None,
) -> list[str]:
    """Canonicalize a keyword list — single entry point for runtime + scorer.

    Pipeline (deterministic, order-preserving, idempotent):
    1. strip / lowercase each token
    2. apply alias + plural maps per token
    3. drop modifier stopwords
    4. drop language leak when `language` facet is set
    5. greedy-merge adjacent tokens that form a technical phrase
    6. dedupe preserving first occurrence
    """
    # Stage 1 + 2: per-token canonicalization, dropping empty strings.
    canonical: list[str] = []
    for raw in keywords:
        token = canonicalize_keyword_token(raw)
        if token:
            canonical.append(token)

    # Stage 3 + 4: drop stopwords and language leak.
    language_canonical = language.strip() if isinstance(language, str) else None
    filtered: list[str] = []
    for token in canonical:
        if token in _MODIFIER_STOPWORDS:
            continue
        if language_canonical and _is_language_leak(token, language_canonical):
            continue
        filtered.append(token)

    # Stage 5: greedy phrase merge.
    merged = _merge_phrases(filtered)

    # Stage 6: dedupe preserving first occurrence.
    seen: set[str] = set()
    result: list[str] = []
    for token in merged:
        if token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def find_keyword_violations(
    keywords: list[str],
    *,
    language: str | None = None,
) -> list[ValidationIssue]:
    """Report which canonicalization rules the raw keyword list triggered.

    Pure reporting — callers combine these with semantic validation to decide
    routing. No caller is allowed to produce string adapters.
    """
    issues: list[ValidationIssue] = []
    language_canonical = language.strip() if isinstance(language, str) else None

    for raw in keywords:
        stripped = raw.strip().lower() if isinstance(raw, str) else ""
        if not stripped:
            continue

        if stripped in _ALIAS_MAP:
            issues.append(
                ValidationIssue(
                    code="alias_applied",
                    message=f"alias '{stripped}' -> '{_ALIAS_MAP[stripped]}'",
                    field="keywords",
                    token=stripped,
                    replacement=_ALIAS_MAP[stripped],
                )
            )
            continue

        if stripped in _PLURAL_MAP:
            issues.append(
                ValidationIssue(
                    code="plural_drift",
                    message=f"plural '{stripped}' -> '{_PLURAL_MAP[stripped]}'",
                    field="keywords",
                    token=stripped,
                    replacement=_PLURAL_MAP[stripped],
                )
            )
            continue

        if stripped in _MODIFIER_STOPWORDS:
            issues.append(
                ValidationIssue(
                    code="modifier_stopword",
                    message=f"modifier stopword '{stripped}' should not be a keyword",
                    field="keywords",
                    token=stripped,
                )
            )
            continue

        if language_canonical and _is_language_leak(stripped, language_canonical):
            issues.append(
                ValidationIssue(
                    code="language_leak",
                    message=(
                        f"language token '{stripped}' leaked into keywords while "
                        f"language='{language_canonical}'"
                    ),
                    field="keywords",
                    token=stripped,
                )
            )
            continue

    # Phrase-split detection operates on the already-canonicalized tokens so
    # that aliases ('rect' -> 'react') participate in phrase matching.
    canonical_tokens = [canonicalize_keyword_token(k) for k in keywords]
    canonical_tokens = [t for t in canonical_tokens if t]
    for phrase in _TECHNICAL_PHRASES:
        parts = phrase.split()
        if len(parts) < 2:
            continue
        if all(p in canonical_tokens for p in parts) and phrase not in canonical_tokens:
            issues.append(
                ValidationIssue(
                    code="phrase_split",
                    message=f"technical phrase '{phrase}' was split across tokens",
                    field="keywords",
                    replacement=phrase,
                )
            )

    return issues


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_language_leak(token: str, language_facet: str) -> bool:
    mapped = _LANGUAGE_TOKEN_TO_FACET.get(token)
    if mapped is None:
        return False
    return mapped.lower() == language_facet.lower()


def _merge_phrases(tokens: list[str]) -> list[str]:
    """Multiset-merge tokens that form a technical phrase.

    Order-independent: a phrase is detected when all its parts are present in
    the token bag, regardless of how the parser emitted them. This keeps the
    scorer invariant under keyword order (EVAL.md §7) while still letting the
    phrase dictionary protect technical phrases.
    """
    remaining = list(tokens)
    merged: list[str] = []
    for phrase_parts in _PHRASES_LONGEST_FIRST:
        while _contains_all(remaining, phrase_parts):
            for part in phrase_parts:
                remaining.remove(part)
            merged.append(" ".join(phrase_parts))
    return merged + remaining


def _contains_all(bag: list[str], parts: tuple[str, ...]) -> bool:
    needed: dict[str, int] = {}
    for part in parts:
        needed[part] = needed.get(part, 0) + 1
    counts: dict[str, int] = {}
    for token in bag:
        counts[token] = counts.get(token, 0) + 1
    return all(counts.get(p, 0) >= n for p, n in needed.items())
