"""Tests for keyword_rules.py — single source of truth for keyword canonicalization.

Covers KEYWORD_TUNING_SPEC.md §3-§7 rules:
- technical phrase merge (§4)
- plural / singular lemmatization (§5)
- language leak removal (§6.1)
- modifier stopword removal (§3.2, §6.2)
- alias / multilingual canonicalization (§7)
- structured ValidationIssue output (§8.0.5)
"""
from __future__ import annotations

import pytest

from gh_search.normalizers.keyword_rules import (
    KEYWORD_RULES_VERSION,
    ValidationIssue,
    canonicalize_keyword_token,
    find_keyword_violations,
    normalize_keywords,
)


# ---------------------------------------------------------------------------
# ValidationIssue schema
# ---------------------------------------------------------------------------


class TestValidationIssue:
    def test_required_and_optional_fields(self):
        issue = ValidationIssue(code="language_leak", message="language leaked to keywords")
        assert issue.code == "language_leak"
        assert issue.message == "language leaked to keywords"
        assert issue.field is None
        assert issue.token is None
        assert issue.replacement is None

    def test_full_payload(self):
        issue = ValidationIssue(
            code="alias_applied",
            message="alias applied",
            field="keywords",
            token="pythn",
            replacement="python",
        )
        assert issue.field == "keywords"
        assert issue.token == "pythn"
        assert issue.replacement == "python"

    def test_unknown_field_rejected(self):
        # Extra fields are forbidden to keep the single source of truth tight.
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ValidationIssue(code="c", message="m", extra="no")  # type: ignore[call-arg]

    def test_code_is_required(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ValidationIssue(message="no code")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Module-level contract
# ---------------------------------------------------------------------------


class TestModuleContract:
    def test_keyword_rules_version_constant(self):
        assert KEYWORD_RULES_VERSION == "kw-rules-v1"

    def test_public_exports(self):
        from gh_search.normalizers import keyword_rules

        for name in (
            "KEYWORD_RULES_VERSION",
            "ValidationIssue",
            "canonicalize_keyword_token",
            "normalize_keywords",
            "find_keyword_violations",
        ):
            assert hasattr(keyword_rules, name), f"missing public symbol: {name}"


# ---------------------------------------------------------------------------
# canonicalize_keyword_token — single-token alias / plural / case
# ---------------------------------------------------------------------------


class TestCanonicalizeKeywordToken:
    def test_lowercases(self):
        assert canonicalize_keyword_token("SCRAPING") == "scraping"

    def test_trims_whitespace(self):
        assert canonicalize_keyword_token("  crawler  ") == "crawler"

    def test_plural_lemmatizes_whitelist(self):
        assert canonicalize_keyword_token("frameworks") == "framework"
        assert canonicalize_keyword_token("libraries") == "library"
        assert canonicalize_keyword_token("engines") == "engine"
        assert canonicalize_keyword_token("examples") == "example"
        assert canonicalize_keyword_token("utilities") == "utility"
        assert canonicalize_keyword_token("libs") == "library"

    def test_alias_substitution(self):
        assert canonicalize_keyword_token("pythn") == "python"
        assert canonicalize_keyword_token("javscript") == "javascript"
        assert canonicalize_keyword_token("frameework") == "framework"
        assert canonicalize_keyword_token("rect") == "react"

    def test_multilingual_alias(self):
        assert canonicalize_keyword_token("爬蟲") == "scraping"
        assert canonicalize_keyword_token("框架") == "framework"
        assert canonicalize_keyword_token("微服务") == "microservice"

    def test_no_general_stemming(self):
        # Only the whitelist is lemmatized; unrelated words must stay intact.
        assert canonicalize_keyword_token("status") == "status"
        assert canonicalize_keyword_token("analytics") == "analytics"


# ---------------------------------------------------------------------------
# normalize_keywords — full pipeline
# ---------------------------------------------------------------------------


class TestNormalizeKeywords:
    def test_idempotent_on_clean_input(self):
        out = normalize_keywords(["scraping", "crawler"])
        assert out == ["scraping", "crawler"]

    def test_lowercases_all_tokens(self):
        out = normalize_keywords(["SCRAPING", "Crawler"])
        assert out == ["scraping", "crawler"]

    def test_plural_canonicalization(self):
        out = normalize_keywords(["frameworks", "libraries", "engines"])
        assert out == ["framework", "library", "engine"]

    def test_removes_modifier_stopwords(self):
        out = normalize_keywords(["popular", "scraping", "top", "best", "trending"])
        assert out == ["scraping"]

    def test_removes_language_leak_when_language_matches(self):
        out = normalize_keywords(["python", "scraping"], language="Python")
        assert out == ["scraping"]

    def test_removes_language_leak_case_insensitive(self):
        out = normalize_keywords(["GoLang", "cli"], language="Go")
        assert out == ["cli"]

    def test_keeps_language_token_when_language_field_is_none(self):
        # Without a language facet, we don't know whether `python` is a topic
        # or a language name. Conservative: keep it.
        out = normalize_keywords(["python", "scraping"], language=None)
        assert "python" in out and "scraping" in out

    def test_merges_technical_phrase_from_split_tokens(self):
        out = normalize_keywords(["spring", "boot", "starter"])
        assert "spring boot" in out
        assert "spring" not in out
        assert "boot" not in out
        assert "starter" in out

    def test_merges_react_native(self):
        out = normalize_keywords(["react", "native", "template"])
        assert "react native" in out
        assert "react" not in out
        assert "native" not in out

    def test_preserves_existing_phrase_keyword(self):
        out = normalize_keywords(["machine learning", "toolkit"])
        assert "machine learning" in out
        assert "toolkit" in out

    def test_alias_then_merge(self):
        # `rect` → `react`, then `react` + `native` → `react native`
        out = normalize_keywords(["rect", "native"])
        assert out == ["react native"]

    def test_dedupes_after_normalization(self):
        out = normalize_keywords(["framework", "frameworks", "Framework"])
        assert out == ["framework"]

    def test_strips_and_skips_empty_tokens(self):
        out = normalize_keywords(["  ", "scraping", ""])
        assert out == ["scraping"]

    def test_multilingual_canonicalization(self):
        out = normalize_keywords(["爬蟲", "框架"])
        assert out == ["scraping", "framework"]

    def test_order_preserves_first_occurrence(self):
        out = normalize_keywords(["crawler", "scraping", "crawler"])
        assert out == ["crawler", "scraping"]

    def test_empty_input_returns_empty_list(self):
        assert normalize_keywords([]) == []

    def test_does_not_mutate_input(self):
        original = ["python", "scraping"]
        snapshot = list(original)
        normalize_keywords(original, language="Python")
        assert original == snapshot


# ---------------------------------------------------------------------------
# find_keyword_violations — structured issues for validator / repair / logs
# ---------------------------------------------------------------------------


class TestFindKeywordViolations:
    def test_returns_empty_list_for_clean_keywords(self):
        issues = find_keyword_violations(["scraping", "crawler"])
        assert issues == []

    def test_language_leak_issue(self):
        issues = find_keyword_violations(["python", "scraping"], language="Python")
        codes = [i.code for i in issues]
        assert "language_leak" in codes
        lang_issue = next(i for i in issues if i.code == "language_leak")
        assert lang_issue.token == "python"

    def test_modifier_stopword_issue(self):
        issues = find_keyword_violations(["popular", "scraping"])
        codes = [i.code for i in issues]
        assert "modifier_stopword" in codes

    def test_phrase_split_issue(self):
        issues = find_keyword_violations(["spring", "boot"])
        codes = [i.code for i in issues]
        assert "phrase_split" in codes
        phrase_issue = next(i for i in issues if i.code == "phrase_split")
        assert phrase_issue.replacement == "spring boot"

    def test_plural_drift_issue(self):
        issues = find_keyword_violations(["frameworks"])
        codes = [i.code for i in issues]
        assert "plural_drift" in codes
        issue = next(i for i in issues if i.code == "plural_drift")
        assert issue.token == "frameworks"
        assert issue.replacement == "framework"

    def test_alias_applied_issue(self):
        issues = find_keyword_violations(["pythn"])
        codes = [i.code for i in issues]
        assert "alias_applied" in codes
        issue = next(i for i in issues if i.code == "alias_applied")
        assert issue.token == "pythn"
        assert issue.replacement == "python"

    def test_all_issues_are_validation_issue_instances(self):
        issues = find_keyword_violations(
            ["python", "popular", "frameworks", "pythn"],
            language="Python",
        )
        assert issues  # non-empty
        assert all(isinstance(i, ValidationIssue) for i in issues)
        # Field should always be 'keywords' for keyword-related violations
        assert all(i.field == "keywords" for i in issues)

    def test_does_not_raise_on_empty_input(self):
        assert find_keyword_violations([]) == []

    def test_language_leak_not_flagged_when_language_is_none(self):
        issues = find_keyword_violations(["python", "scraping"], language=None)
        codes = [i.code for i in issues]
        assert "language_leak" not in codes


# ---------------------------------------------------------------------------
# Cross-function consistency
# ---------------------------------------------------------------------------


class TestConsistency:
    @pytest.mark.parametrize(
        "raw,language,expected",
        [
            (["Python", "SCRAPING"], "Python", ["scraping"]),
            (["popular", "golang", "cli"], "Go", ["cli"]),
            (["spring", "boot", "popular"], None, ["spring boot"]),
            (["frameworks"], None, ["framework"]),
            (["pythn", "scraping"], None, ["python", "scraping"]),
        ],
    )
    def test_normalize_keywords_matches_expected(self, raw, language, expected):
        assert normalize_keywords(raw, language=language) == expected

    def test_normalize_idempotent(self):
        once = normalize_keywords(["Python", "frameworks", "popular"], language="Python")
        twice = normalize_keywords(once, language="Python")
        assert once == twice
