"""ITER5_DATE_TUNING_SPEC §8.2 + §8.3: parser prompt date rule contract.

These tests pin the presence of iter5 date rules in `prompts/core/parse-v1.md`
and guard against accidental removal of iter4 keyword policy / other non-date
chapters. They don't attempt to judge LLM behavior — that's validated by
cross-model smoke rerun (§9.2).
"""
from __future__ import annotations

from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PARSE_PROMPT_PATH = _PROJECT_ROOT / "prompts" / "core" / "parse-v1.md"


def _parse_prompt_text() -> str:
    return _PARSE_PROMPT_PATH.read_text(encoding="utf-8")


# §8.2: iter5 date rules must be present.

DATE_RULE_CONTRACT_PHRASES = [
    # today anchor reference
    "Today: YYYY-MM-DD",
    # absolute English boundaries (existing + reinforced)
    'after 2023',
    'before 2020',
    "between Y1 and Y2",
    "from YEAR",
    "in YEAR",
    # Chinese inclusive-start boundaries (iter5 new)
    "YEAR年以后",
    "YEAR年以前",
    '"2023年以后"',
    # Relative time (iter5 new, dataset-backed only)
    "this year",
    "last year",
    "今年",
    "去年",
    # Vague / unmappable rule (iter5 new)
    "vague",
    "not too old",
    "not too new",
    # Typo tolerance (iter5 new)
    "aftr 2022",
]


@pytest.mark.parametrize("phrase", DATE_RULE_CONTRACT_PHRASES)
def test_parse_prompt_contains_iter5_date_rule(phrase: str) -> None:
    text = _parse_prompt_text()
    assert phrase in text, (
        f"iter5 date-rule contract phrase {phrase!r} missing from parse-v1.md"
    )


# §8.3: non-date chapters must stay intact. iter4 phrase policy, language /
# stars / sort / order / limit / keyword policy are all out of iter5 scope.

NON_DATE_CONTRACT_PHRASES = [
    # iter4 phrase policy (named entities we must still merge)
    "spring boot",
    "react native",
    "machine learning",
    "ui kit",
    # schema fields
    "keywords",
    "language",
    "min_stars",
    "max_stars",
    "sort",
    "order",
    "limit",
    # star modifier semantics (must stay as iter4 had them)
    "more than 100",
    "at least 100",
    "under 100",
]


@pytest.mark.parametrize("phrase", NON_DATE_CONTRACT_PHRASES)
def test_parse_prompt_preserves_non_date_chapters(phrase: str) -> None:
    text = _parse_prompt_text()
    assert phrase in text, (
        f"iter5 must not drop non-date content {phrase!r} from parse-v1.md"
    )


# Out-of-scope patterns (§6) must NOT appear as hard rules. We only check for
# the specific spec-forbidden phrasings, not any substring that could legitimately
# appear elsewhere (e.g. "months" on its own is fine).
OUT_OF_SCOPE_PHRASES = [
    "last N months",
    "last N days",
    "past N weeks",
]


@pytest.mark.parametrize("phrase", OUT_OF_SCOPE_PHRASES)
def test_parse_prompt_does_not_introduce_out_of_scope_relative_rules(
    phrase: str,
) -> None:
    text = _parse_prompt_text()
    assert phrase not in text, (
        f"iter5 spec §6 forbids {phrase!r} rule; dataset has no supporting case"
    )
