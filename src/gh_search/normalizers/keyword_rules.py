"""Keyword canonicalization — single entry point.

Governing specs:

- `KEYWORD_TUNING_SPEC §8` (iter2) — original single-source-of-truth contract,
  shared pipeline across `validate_query`, `repair_query`, scorer, and
  run/turn artifacts. No local lowercase, sort, merge, or lemmatize is
  allowed elsewhere (§8.3).
- `ITER4_PHRASE_POLICY_SPEC §3, §7` — Stage -1 (multi-word stopword
  pre-drop), Stage 0 (whitespace split), Stage 3.5 (post-split bag-remove),
  Stage 2 (qualifier-injection guard), and the pruned named-entity phrase
  dict.

`normalize_keywords` and `find_keyword_violations` are the only functions that
may rewrite or flag `StructuredQuery.keywords`. They share Stage -1 / Stage 0
tokenization (`_tokenize`) so the transformation and its audit trail cannot
diverge on multi-word parser output.
"""
from __future__ import annotations

import re
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
        # Iter4 (ITER4_PHRASE_POLICY_SPEC §7.3): added to support the q004
        # phrase-only blocker. `projects` / `implementations` are NOT here —
        # iter7 handles them as decoration drops via _DECORATION_STOPWORDS,
        # not as plural rewrites. `templates` -> `template` plural drift is
        # still deferred (ITER7 §2.3).
        "tools": "tool",
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

# Multi-word slice of the stopword set. Kept as a separate frozen view so the
# Stage -1 / Stage 3.5 lookups in normalize_keywords stay O(1) and don't have
# to re-filter on every call (ITER4_PHRASE_POLICY_SPEC §3.4).
_MULTI_WORD_STOPWORDS: frozenset[str] = frozenset(
    s for s in _MODIFIER_STOPWORDS if " " in s
)

# Decoration stopwords (ITER7_DECORATION_CLEANUP_SPEC §3.1) — single-token
# parser noise that does not carry topic semantics. Dropped at Stage 3 of
# normalize_keywords; reported by find_keyword_violations under the distinct
# `decoration_stopword` code so DEC-bucket telemetry stays separable from
# intent-modifier drops. Kept narrow on purpose: `project`/`japanese`/
# `templates` are deferred per §3.2 / §3.3 / §2.3.
_DECORATION_STOPWORDS: frozenset[str] = frozenset(
    {
        "implementations",
        "projects",
    }
)

# Technical phrases that must stay as a single keyword if present or be
# re-assembled from adjacent split tokens (§4.2.1).
#
# Iter4 (ITER4_PHRASE_POLICY_SPEC §7.2): pruned to **named entities only** —
# product names and compound terms that lose meaning when split. Removed
# adjective+noun pairs (web framework, testing framework, game engine, admin
# dashboard, microservice framework, react component, graphql server, orm
# library, chatbot library) because dataset GT consistently splits those.
_TECHNICAL_PHRASES: tuple[str, ...] = (
    "ruby on rails",
    "spring boot",
    "react native",
    "vue 3",
    "state management",
    "machine learning",
    "ui kit",
)

# Longest-first ordering so bag-style merging consumes "ruby on rails" before
# any shorter subsequence has a chance to split it. After iter4 pruning there
# are no overlapping subsequences among the 7 named entities; the sort is a
# forward-compatibility guard for when new phrases are added.
_PHRASES_LONGEST_FIRST: tuple[tuple[str, ...], ...] = tuple(
    tuple(phrase.split())
    for phrase in sorted(_TECHNICAL_PHRASES, key=lambda p: -len(p.split()))
)

# Qualifier-injection guard (ITER4 deep-review H3): tokens shaped like GitHub
# structured-search qualifiers (`stars:>=0`, `fork:true`, `language:c++`)
# would be interpolated into the `q=` parameter by `compiler.py` and bypass
# the structured facets. Dropped by Stage 2 of `normalize_keywords` and
# reported as `qualifier_in_keyword` by `find_keyword_violations`.
_QUALIFIER_TOKEN_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*:.+")


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


def _tokenize(keywords: list[str]) -> tuple[list[str], list[str]]:
    """Apply Stage -1 (multi-word stopword exact drop) + Stage 0 (whitespace split).

    Shared by `normalize_keywords` and `find_keyword_violations` so the
    transformation and its audit trail always see the same sub-token view.

    Returns
    -------
    dropped : list[str]
        Raw entries (lower-cased, stripped) that Stage -1 removed because
        they exactly matched a multi-word stopword. Callers may use this to
        emit audit events for the drop.
    sub_tokens : list[str]
        Flat sub-token list produced by Stage 0 whitespace split over the
        entries that survived Stage -1.
    """
    dropped: list[str] = []
    sub_tokens: list[str] = []
    for raw in keywords:
        if not isinstance(raw, str):
            continue
        key = raw.strip().lower()
        if key in _MULTI_WORD_STOPWORDS:
            dropped.append(key)
            continue
        for part in raw.split():
            sub_tokens.append(part)
    return dropped, sub_tokens


def normalize_keywords(
    keywords: list[str],
    *,
    language: str | None = None,
) -> list[str]:
    """Canonicalize a keyword list — single entry point for runtime + scorer.

    Pipeline (deterministic, order-independent phrase detection, idempotent),
    per ITER4_PHRASE_POLICY_SPEC §3 + §7.1:

    - Stage -1: drop raw entries that exactly match a multi-word stopword
      (before Stage 0 would shred them into sub-tokens).
    - Stage 0:  split multi-word input strings on whitespace so per-token
      rules fire on every sub-token (parser may emit e.g. ['web frameworks']).
    - Stage 1:  strip / lowercase each sub-token; apply alias + plural maps.
    - Stage 2:  drop qualifier-shaped tokens ('foo:bar') that would otherwise
      become GitHub structural modifiers when interpolated into `q=`.
    - Stage 3:  drop single-word modifier stopwords + language-leak tokens
      (when the `language` facet is set).
    - Stage 3.5: drop multi-word stopwords whose parts all landed in the bag
      after Stage 0 split (handles e.g. 'open source logistics').
    - Stage 5:  greedy-merge adjacent tokens that form a technical phrase.
      Output places merged phrases first, then remaining tokens in their
      input order (see `_merge_phrases`).
    - Stage 6:  dedupe preserving first occurrence.
    """
    _, sub_tokens = _tokenize(keywords)

    # Stage 1 + Stage 2: per-token canonicalize; drop empties and qualifier
    # tokens that would inject GitHub query modifiers.
    canonical: list[str] = []
    for raw in sub_tokens:
        token = canonicalize_keyword_token(raw)
        if not token:
            continue
        if _QUALIFIER_TOKEN_RE.match(token):
            continue
        canonical.append(token)

    # Stage 3: drop single-word modifier stopwords, decoration stopwords, and
    # language-leak tokens. Modifier and decoration sets stay separate so the
    # find_keyword_violations trace can distinguish DEC-bucket drops from
    # intent-modifier drops (ITER7_DECORATION_CLEANUP_SPEC §3.1).
    language_canonical = language.strip() if isinstance(language, str) else None
    filtered: list[str] = []
    for token in canonical:
        if token in _MODIFIER_STOPWORDS:
            continue
        if token in _DECORATION_STOPWORDS:
            continue
        if language_canonical and _is_language_leak(token, language_canonical):
            continue
        filtered.append(token)

    # Stage 3.5: drop multi-word stopwords whose parts all landed in the bag.
    filtered = _drop_multi_word_stopwords(filtered)

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
    routing. Shares `_tokenize` (Stage -1 + Stage 0) with `normalize_keywords`
    so the audit trail cannot diverge from the actual transformation on
    multi-word parser output (ITER4 deep-review C1 / H2 / M4).

    Per-token rules are evaluated independently: one token may emit multiple
    issues (e.g. `js` with `language="JavaScript"` emits both `alias_applied`
    and `language_leak`).
    """
    issues: list[ValidationIssue] = []
    language_canonical = language.strip() if isinstance(language, str) else None

    # Stage -1: report multi-word stopwords that matched whole raw entries.
    dropped, sub_tokens = _tokenize(keywords)
    for phrase in dropped:
        issues.append(
            ValidationIssue(
                code="modifier_stopword",
                message=f"modifier stopword '{phrase}' should not be a keyword",
                field="keywords",
                token=phrase,
            )
        )

    # Stage 1 / 2 / 3 equivalents, per sub-token. No early `continue` — any
    # single token may legitimately trigger several rules.
    for raw in sub_tokens:
        stripped = raw.strip().lower()
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

        if stripped in _MODIFIER_STOPWORDS:
            issues.append(
                ValidationIssue(
                    code="modifier_stopword",
                    message=f"modifier stopword '{stripped}' should not be a keyword",
                    field="keywords",
                    token=stripped,
                )
            )

        if stripped in _DECORATION_STOPWORDS:
            issues.append(
                ValidationIssue(
                    code="decoration_stopword",
                    message=f"decoration token '{stripped}' should not be a keyword",
                    field="keywords",
                    token=stripped,
                )
            )

        # Language-leak check is evaluated on the canonicalized form so that
        # aliases ('js' -> 'javascript') participate in leak detection.
        canonical = canonicalize_keyword_token(raw)
        if language_canonical and _is_language_leak(canonical, language_canonical):
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

        if _QUALIFIER_TOKEN_RE.match(stripped):
            issues.append(
                ValidationIssue(
                    code="qualifier_in_keyword",
                    message=(
                        f"qualifier-shaped token '{stripped}' would become a "
                        "GitHub structural modifier"
                    ),
                    field="keywords",
                    token=stripped,
                )
            )

    # Canonicalized bag for Stage 3.5 and phrase-split detection.
    canonical_tokens = [canonicalize_keyword_token(t) for t in sub_tokens]
    canonical_tokens = [t for t in canonical_tokens if t]

    # Stage 3.5: multi-word stopwords assembled after Stage 0 split.
    already_reported = {
        i.token for i in issues if i.code == "modifier_stopword" and i.token
    }
    for phrase in _MULTI_WORD_STOPWORDS:
        if phrase in already_reported:
            continue
        parts = tuple(phrase.split())
        if _contains_all(canonical_tokens, parts):
            issues.append(
                ValidationIssue(
                    code="modifier_stopword",
                    message=f"modifier stopword '{phrase}' should not be a keyword",
                    field="keywords",
                    token=phrase,
                )
            )

    # Phrase-split detection: named-entity phrase was split across tokens.
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


def _drop_multi_word_stopwords(tokens: list[str]) -> list[str]:
    """Stage 3.5 helper — returns a new list with multi-word stopwords removed.

    Uses the same "all parts present in bag" detection as `_merge_phrases`
    but removes rather than merges. Produces a new list (does not mutate the
    caller's `tokens`) to stay consistent with the rest of the pipeline.
    """
    remaining = list(tokens)
    for phrase in _MULTI_WORD_STOPWORDS:
        parts = tuple(phrase.split())
        while _contains_all(remaining, parts):
            for part in parts:
                remaining.remove(part)
    return remaining


def _merge_phrases(tokens: list[str]) -> list[str]:
    """Multiset-merge tokens that form a technical phrase.

    Detection is order-independent: a phrase matches when all its parts are
    present in the token bag, regardless of the parser's emission order.

    Output layout is **merged-phrases-first, then remaining tokens in their
    input order**. This is intentional (the scorer does `sorted(...)` which
    erases order anyway) but the `KeywordNormalizationTrace.normalized_keywords`
    field surfaces this layout in logs, so treat the ordering as
    "phrases-first, originals-preserved-relative" rather than "identical to
    input order".
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
