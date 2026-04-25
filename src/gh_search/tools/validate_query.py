"""validate_query tool (TOOLS.md §3, §9, KEYWORD_TUNING_SPEC §8).

Runs the shared keyword canonicalization pipeline (`normalize_keywords`)
before semantic validation so the rest of the loop, the repair step, the
scorer, and the artifact trace all see the same post-normalization keywords.

Iter9 (ITER9_LANGUAGE_OVERINFERENCE_RESIDUAL_SPEC §3) additionally suppresses
`language` facets that have no explicit anchor in `user_query`. The language
evidence map is read directly from `keyword_rules._LANGUAGE_TOKEN_TO_FACET`
to keep a single source of truth (§3.3 read-only SSoT path).
"""
from __future__ import annotations

import re

from gh_search.normalizers import normalize_keywords
from gh_search.normalizers.keyword_rules import _LANGUAGE_TOKEN_TO_FACET
from gh_search.schemas import (
    Control,
    SharedAgentState,
    StructuredQuery,
    TerminateReason,
    ToolName,
    Validation,
    ValidationIssue,
)
from gh_search.validator import validate_structured_query


def validate_query(state: SharedAgentState) -> SharedAgentState:
    if state.structured_query is None:
        validation = Validation(
            is_valid=False,
            errors=[
                ValidationIssue(
                    code="parse_failed",
                    message="structured_query is missing; parse_query did not produce one",
                    field="structured_query",
                )
            ],
            missing_required_fields=[],
        )
        control = Control(
            next_tool=ToolName.FINALIZE,
            should_terminate=True,
            terminate_reason=TerminateReason.VALIDATION_FAILED,
        )
        return state.model_copy(update={"validation": validation, "control": control})

    normalized_sq = _normalize_structured_query(state.structured_query, state.user_query)
    validation = validate_structured_query(normalized_sq)
    if validation.is_valid:
        control = Control(
            next_tool=ToolName.COMPILE_GITHUB_QUERY,
            should_terminate=False,
            terminate_reason=None,
        )
    else:
        control = Control(
            next_tool=ToolName.REPAIR_QUERY,
            should_terminate=False,
            terminate_reason=None,
        )

    return state.model_copy(
        update={
            "structured_query": normalized_sq,
            "validation": validation,
            "control": control,
        }
    )


def _normalize_structured_query(
    sq: StructuredQuery, user_query: str
) -> StructuredQuery:
    normalized_keywords = normalize_keywords(list(sq.keywords), language=sq.language)
    suppressed_language = _suppress_unsupported_language(sq.language, user_query)

    keywords_changed = normalized_keywords != list(sq.keywords)
    language_changed = suppressed_language != sq.language
    if not keywords_changed and not language_changed:
        return sq

    update: dict[str, object] = {}
    if keywords_changed:
        update["keywords"] = normalized_keywords
    if language_changed:
        update["language"] = suppressed_language
    return sq.model_copy(update=update)


# ---------------------------------------------------------------------------
# Iter9 language evidence (§3.1) — read-only SSoT helper.
# ---------------------------------------------------------------------------

# Build canonical → set-of-anchors lookup once. Keys are case-folded canonical
# language names ("python", "javascript", …); values are the raw anchor tokens
# ("python", "py", …) preserving the original alias casing for re.escape.
_CANONICAL_TO_ANCHORS: dict[str, tuple[str, ...]] = {}
for _anchor, _canonical in _LANGUAGE_TOKEN_TO_FACET.items():
    _CANONICAL_TO_ANCHORS.setdefault(_canonical.lower(), ())
    _CANONICAL_TO_ANCHORS[_canonical.lower()] = _CANONICAL_TO_ANCHORS[
        _canonical.lower()
    ] + (_anchor,)
del _anchor, _canonical


def _suppress_unsupported_language(
    language: str | None, user_query: str
) -> str | None:
    """Return `language` only if `user_query` has an explicit anchor for it.

    Implements ITER9 §3.1 matching policy:
      - case-insensitive
      - token-bounded (`(?<![A-Za-z0-9])anchor(?![A-Za-z0-9])`) so `java` does
        not match inside `javascript`, but CJK adjacency is permitted
      - special chars in anchors (`c++`, `c#`) handled via `re.escape`
      - the canonical language reached from the matched anchor must equal the
        `pred.language` (case-insensitive); otherwise clear

    The function never adds new language inferences — it only preserves or
    clears (§3 single principle).
    """
    if language is None:
        return None
    if not isinstance(language, str):
        return None
    target = language.strip()
    if not target:
        return None

    anchors = _CANONICAL_TO_ANCHORS.get(target.lower())
    if not anchors:
        # pred is not a canonical GitHub language we recognize → clear.
        return None

    for anchor in anchors:
        pattern = rf"(?<![A-Za-z0-9]){re.escape(anchor)}(?![A-Za-z0-9])"
        if re.search(pattern, user_query, re.IGNORECASE):
            return language
    return None
