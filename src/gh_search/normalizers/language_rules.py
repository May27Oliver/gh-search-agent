"""Language facet contraction (ITER6_LANGUAGE_OVERINFERENCE_SPEC §3, §6.3).

Single source of truth for `language` evidence aliases and downstream
contraction policy. Parser is allowed to infer `language` from world
knowledge (e.g. `react` → JavaScript), but iter6 contracts that inference
when no explicit language token appears in the user query.

Public entry point: `normalize_language_facet(raw_language, user_query)`.
Used by `validate_query._normalize_structured_query()` to keep keyword and
language normalization in the same post-parse snapshot (spec §6.1).

Iter6 deliberately keeps coverage small (§6.4): only languages and aliases
already present in `datasets/eval_dataset_reviewed.json`. Multilingual /
framework-as-language and CJK language tokens are out of scope.
"""
from __future__ import annotations

import re
from types import MappingProxyType
from typing import Mapping

from gh_search.normalizers.keyword_rules import ValidationIssue

LANGUAGE_RULES_VERSION = "lang-rules-v1"


# Token (lowercased) → canonical GitHub language facet.
# Only languages and aliases that actually appear in the eval dataset are
# included (§6.4). Adding new entries belongs in this dict only — never
# inline in validate_query / validator (§3.3 ownership).
_LANGUAGE_EVIDENCE: Mapping[str, str] = MappingProxyType(
    {
        "python": "Python",
        "pythn": "Python",  # typo tolerance (§3.1)
        "go": "Go",
        "golang": "Go",
        "javascript": "JavaScript",
        "javscript": "JavaScript",  # typo tolerance (q024)
        "typescript": "TypeScript",
        "ts": "TypeScript",
        "rust": "Rust",
        "java": "Java",
        "swift": "Swift",
        "c++": "C++",
    }
)


# Tokenize on word boundaries so multi-character punctuation (`!!`, `,`) doesn't
# leave residue. The trailing optional `++` / `#` is so language tokens like
# `c++`, `c#`, `f#` survive tokenization (q016 pattern). We don't try to be
# clever about CJK — explicit-language tokens in the dataset are all ASCII.
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:\+\+|#)?")


def _detect_evidence(user_query: str) -> set[str]:
    """Return the set of canonical languages explicitly mentioned in the query."""
    evidence: set[str] = set()
    for match in _TOKEN_RE.findall(user_query):
        canonical = _LANGUAGE_EVIDENCE.get(match.lower())
        if canonical is not None:
            evidence.add(canonical)
    return evidence


def normalize_language_facet(
    raw_language: str | None,
    user_query: str,
) -> tuple[str | None, list[ValidationIssue]]:
    """Contract parser-inferred `language` against explicit query evidence.

    Returns `(normalized_language, issues)`:

    - `raw_language is None` → pass through, no issues.
    - explicit evidence in `user_query` matches `raw_language` → preserve.
    - no explicit evidence (or evidence mismatches `raw_language`) → clear,
      emit `language_inferred_without_evidence` issue.
    """
    if raw_language is None:
        return None, []

    evidence = _detect_evidence(user_query)
    if raw_language in evidence:
        return raw_language, [
            ValidationIssue(
                code="language_kept_with_explicit_evidence",
                message=f"language={raw_language!r} retained — explicit evidence in query",
                field="language",
                token=raw_language,
            )
        ]

    return None, [
        ValidationIssue(
            code="language_inferred_without_evidence",
            message=(
                f"language={raw_language!r} cleared — no explicit language "
                "token in query, parser inferred from framework/topic"
            ),
            field="language",
            token=raw_language,
        )
    ]


__all__ = [
    "LANGUAGE_RULES_VERSION",
    "normalize_language_facet",
]
