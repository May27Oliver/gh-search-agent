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
    normalized_min_stars, normalized_max_stars = _normalize_star_bounds(
        sq.min_stars, sq.max_stars, user_query
    )

    keywords_changed = normalized_keywords != list(sq.keywords)
    language_changed = suppressed_language != sq.language
    min_stars_changed = normalized_min_stars != sq.min_stars
    max_stars_changed = normalized_max_stars != sq.max_stars
    if not (
        keywords_changed
        or language_changed
        or min_stars_changed
        or max_stars_changed
    ):
        return sq

    update: dict[str, object | None] = {}
    if keywords_changed:
        update["keywords"] = normalized_keywords
    if language_changed:
        update["language"] = suppressed_language
    if min_stars_changed:
        update["min_stars"] = normalized_min_stars
    if max_stars_changed:
        update["max_stars"] = normalized_max_stars
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


# ---------------------------------------------------------------------------
# Iter10 numeric evidence (§3) — query-driven star-bound rewrite.
# ---------------------------------------------------------------------------

# Order: longer/more-specific alternatives first within each group so regex
# alternation picks the correct comparator. ASCII tokens use word boundaries
# to prevent matches inside larger words ("minute", "starwars"); CJK
# comparators rely on natural script boundaries.
_COMPARATOR_NUM = re.compile(
    r"""
    (?:
        (?P<excl_lower>\bmore\s+than\b|\bover\b|超過|>(?!=))
      | (?P<excl_upper>\bless\s+than\b|\bunder\b|少於|<(?!=))
      | (?P<incl_lower>\bat\s+least\b|\bminimum\b|\bmin\b|>=)
      | (?P<incl_upper>\bat\s+most\b|\bmaximum\b|\bmax\b|<=)
    )
    \s*
    (?P<num>\d+)
    (?P<suffix>[kK])?
    """,
    re.IGNORECASE | re.VERBOSE,
)
_STARS_ANCHOR = re.compile(r"star|星", re.IGNORECASE)


def _normalize_star_bounds(
    min_stars: int | None,
    max_stars: int | None,
    user_query: str,
) -> tuple[int | None, int | None]:
    """Recompute (min_stars, max_stars) from explicit user_query evidence.

    Implements ITER10 §3 query-driven rewrite:
      - require a stars anchor (`star*` / `星`) in the query; without it,
        any incoming numeric bound is cleared (vague-popularity rule §3.1)
      - within an anchored query, comparator + number drives the bound:
          exclusive: `over N` / `more than N` / `超過 N` / `> N`  → N + 1
                     `under N` / `less than N` / `少於 N` / `< N` → N − 1
          inclusive: `min N` / `at least N` / `>= N` / `minimum N` → N
                     `max N` / `at most N` / `<= N` / `maximum N` → N
      - numeric token: plain integer, optional `k` suffix (× 1000)
      - contradictory ranges are preserved verbatim (§3.3); logical
        consistency is not enforced

    Incoming `min_stars` / `max_stars` are intentionally ignored — the
    function is a deterministic recomputation, not a guarded patch.
    """
    if not _STARS_ANCHOR.search(user_query):
        return (None, None)

    new_min: int | None = None
    new_max: int | None = None
    for match in _COMPARATOR_NUM.finditer(user_query):
        num = int(match.group("num"))
        if match.group("suffix"):
            num *= 1000
        if match.group("excl_lower") is not None:
            new_min = num + 1
        elif match.group("excl_upper") is not None:
            new_max = num - 1
        elif match.group("incl_lower") is not None:
            new_min = num
        elif match.group("incl_upper") is not None:
            new_max = num
    return (new_min, new_max)
