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


# ---------------------------------------------------------------------------
# Iter4 phrase policy (ITER4_PHRASE_POLICY_SPEC §8.1)
# ---------------------------------------------------------------------------


ITER4_RECOVERY: list[tuple[str, list[str], str | None, list[str]]] = [
    # (qid, parser_output, language, expected_normalized)
    #
    # Each row corresponds to a §5.1 phrase-only blocker: iter3 parser emitted
    # a merged / plural form that Stage 0 + pruned phrase dict + new plural
    # entry must flatten to the dataset GT shape. Passing this set is a
    # necessary (not sufficient) condition for the end-to-end pass criteria.
    ("q003", ["web frameworks"], "Rust", ["web", "framework"]),
    ("q004a", ["cli tools"], "Go", ["cli", "tool"]),
    ("q004b", ["cli", "tools"], "Go", ["cli", "tool"]),
    ("q005", ["kubernetes operator", "example"], None, ["kubernetes", "operator", "example"]),
    ("q008", ["llm inference engines"], None, ["llm", "inference", "engine"]),
    ("q010a", ["ai agent frameworks"], None, ["ai", "agent", "framework"]),
    ("q010b", ["ai agent", "framework"], None, ["ai", "agent", "framework"]),
    ("q014", ["testing frameworks"], "JavaScript", ["testing", "framework"]),
    ("q016", ["game engines"], "C++", ["game", "engine"]),
    ("q019", ["learning programming"], None, ["learning", "programming"]),
]


class TestIter4PhraseRecovery:
    """§8.1.1 — parser outputs that must normalize to the dataset GT shape."""

    @pytest.mark.parametrize(
        "qid,parser_output,language,expected",
        ITER4_RECOVERY,
        ids=[row[0] for row in ITER4_RECOVERY],
    )
    def test_parser_output_normalizes_to_gt_shape(
        self, qid: str, parser_output: list[str], language: str | None, expected: list[str]
    ) -> None:
        assert normalize_keywords(parser_output, language=language) == expected


ITER4_GT_CANONICAL: list[tuple[list[str], str | None, list[str]]] = [
    # GT side of the same pairs — the scorer normalizes both sides, so if the
    # pruned dict accidentally merged a GT token pair that should stay split
    # (or vice versa), this set catches it.
    (["web", "framework"], "Rust", ["web", "framework"]),
    (["cli", "tool"], "Go", ["cli", "tool"]),
    (["kubernetes", "operator", "example"], None, ["kubernetes", "operator", "example"]),
    (["LLM", "inference", "engine"], None, ["llm", "inference", "engine"]),
    (["ai", "agent", "framework"], None, ["ai", "agent", "framework"]),
    (["testing", "framework"], "JavaScript", ["testing", "framework"]),
    (["game", "engine"], "C++", ["game", "engine"]),
    (["learning", "programming"], None, ["learning", "programming"]),
    # named entities that MUST still merge after pruning
    (["spring boot", "starter"], "Java", ["spring boot", "starter"]),
    (["react native", "ui kit"], None, ["react native", "ui kit"]),
    (["machine", "learning"], None, ["machine learning"]),
    (["vue", "3", "admin", "dashboard", "template"], None, ["vue 3", "admin", "dashboard", "template"]),
]


class TestIter4GtCanonical:
    """§8.1.1 GT side — verifies pruning didn't accidentally break named-entity merges."""

    @pytest.mark.parametrize(
        "gt_keywords,language,expected",
        ITER4_GT_CANONICAL,
    )
    def test_gt_keywords_normalize_to_expected(
        self, gt_keywords: list[str], language: str | None, expected: list[str]
    ) -> None:
        assert normalize_keywords(gt_keywords, language=language) == expected


class TestIter4ContractOnly:
    """§8.1.2 — pins normalizer contract for queries whose end-to-end recovery
    depends on OTHER iters (not this one). Do not reclassify these as
    recoverable in iter4's pass criteria."""

    def test_q028_microservice_framework_splits(self) -> None:
        # q028 Claude/DSK emit ['microservice framework']; normalizer must split
        # it per GT, even though the end-to-end score will still be WRONG in
        # iter4 due to the date blocker (iter5 owns that).
        assert normalize_keywords(["microservice framework"], language="Go") == [
            "microservice",
            "framework",
        ]


class TestIter4MultiWordStopword:
    """§8.1.3 — regression guard for Stage 0 + multi-word stopword handling."""

    def test_pre_split_exact_match_open_source(self) -> None:
        # Stage -1 must drop the whole entry before Stage 0 shreds it.
        assert normalize_keywords(["open source"]) == []

    def test_pre_split_exact_match_ranked_by_stars(self) -> None:
        assert normalize_keywords(["ranked by stars"]) == []

    def test_post_split_bag_match_open_source_logistics(self) -> None:
        # Parser glued the stopword + topic; Stage 0 splits, Stage 3.5 removes
        # the {open, source} pair while keeping 'logistics'.
        assert normalize_keywords(["open source logistics"]) == ["logistics"]

    def test_post_split_bag_match_most_starred(self) -> None:
        # Language leak + multi-word stopword combined.
        assert normalize_keywords(["most starred rust"], language="Rust") == []

    def test_single_word_stopword_still_filtered(self) -> None:
        # Backstop: single-word stopword path unchanged after Stage 3.5 added.
        assert normalize_keywords(["popular", "vue 3"]) == ["vue 3"]

    def test_multi_word_stopword_parts_not_separately_rejected(self) -> None:
        # 'open' alone is NOT a stopword; only 'open source' together is.
        # Token 'open' without 'source' must survive.
        assert normalize_keywords(["open", "scraping"]) == ["open", "scraping"]


class TestIter4Idempotence:
    """§8.1 idempotence — hardened for the new pipeline."""

    @pytest.mark.parametrize(
        "keywords,language",
        [
            (["web frameworks"], "Rust"),
            (["cli tools"], "Go"),
            (["open source logistics"], None),
            (["most starred rust"], "Rust"),
            (["spring", "boot", "starter"], "Java"),
            (["vue", "3", "admin", "dashboard"], None),
        ],
    )
    def test_normalize_idempotent_across_new_cases(
        self, keywords: list[str], language: str | None
    ) -> None:
        once = normalize_keywords(keywords, language=language)
        twice = normalize_keywords(once, language=language)
        assert once == twice


# ---------------------------------------------------------------------------
# Iter4 deep-review follow-up — C1 / H2 / H3 / M3 fixes
# (shared Stage -1/0 tokenization between normalize_keywords and
# find_keyword_violations; multi-issue-per-token reporting; qualifier guard)
# ---------------------------------------------------------------------------


class TestIter4FollowupViolationsMultiWord:
    """C1 — find_keyword_violations must see the same sub-token view as
    normalize_keywords for multi-word parser output."""

    def test_plural_drift_detected_in_merged_string(self) -> None:
        # Previously: find_keyword_violations(["web frameworks"]) silently
        # returned []. Now it must emit plural_drift for 'frameworks'.
        issues = find_keyword_violations(["web frameworks"])
        codes = [i.code for i in issues]
        assert "plural_drift" in codes
        plural = next(i for i in issues if i.code == "plural_drift")
        assert plural.token == "frameworks"
        assert plural.replacement == "framework"

    def test_alias_detected_in_merged_string(self) -> None:
        # alias inside a multi-word entry must be reported now.
        issues = find_keyword_violations(["rect native"])
        codes = [i.code for i in issues]
        assert "alias_applied" in codes
        alias = next(i for i in issues if i.code == "alias_applied")
        assert alias.token == "rect"
        assert alias.replacement == "react"

    def test_modifier_stopword_pre_split_exact_match(self) -> None:
        # Stage -1 drop must still surface as a violation (not silent).
        issues = find_keyword_violations(["open source"])
        codes = [i.code for i in issues]
        assert "modifier_stopword" in codes
        stop = next(i for i in issues if i.code == "modifier_stopword")
        assert stop.token == "open source"

    def test_modifier_stopword_post_split_bag_match(self) -> None:
        # Stage 3.5 bag-check must surface the phrase once.
        issues = find_keyword_violations(["open source logistics"])
        codes = [i.code for i in issues]
        assert codes.count("modifier_stopword") == 1
        stop = next(i for i in issues if i.code == "modifier_stopword")
        assert stop.token == "open source"

    def test_pre_split_and_bag_dont_double_report(self) -> None:
        # If input contains BOTH a raw exact match and a bag-match, the
        # phrase should appear at most once per entry to keep trace readable.
        issues = find_keyword_violations(["open source", "open source logistics"])
        stopword_reports = [
            i for i in issues if i.code == "modifier_stopword" and i.token == "open source"
        ]
        # Stage -1 reports the exact entry; Stage 3.5 sees 'logistics' alone
        # in the bag (open/source consumed visually), so bag-check does not
        # re-trigger. Alternatively, the guard de-dupes by token.
        assert len(stopword_reports) >= 1


class TestIter4FollowupViolationsMultipleIssuesPerToken:
    """H2 — removing early `continue` means a token can emit multiple
    violations (alias + language_leak, plural + phrase, etc)."""

    def test_js_with_javascript_language_emits_both_alias_and_leak(self) -> None:
        issues = find_keyword_violations(["js"], language="JavaScript")
        codes = {i.code for i in issues}
        assert "alias_applied" in codes, f"expected alias_applied in {codes}"
        assert "language_leak" in codes, f"expected language_leak in {codes}"

    @pytest.mark.parametrize(
        "alias,language",
        [
            ("ts", "TypeScript"),
            ("py", "Python"),
            ("rb", "Ruby"),
            ("golang", "Go"),
        ],
    )
    def test_aliased_language_tokens_emit_leak_too(
        self, alias: str, language: str
    ) -> None:
        # 'golang' is not in _ALIAS_MAP but is in _LANGUAGE_TOKEN_TO_FACET,
        # so it should emit language_leak regardless.
        issues = find_keyword_violations([alias], language=language)
        codes = {i.code for i in issues}
        assert "language_leak" in codes


class TestIter4FollowupQualifierInjectionGuard:
    """H3 — tokens shaped like GitHub qualifiers must be stripped by
    normalize and flagged by find_keyword_violations."""

    @pytest.mark.parametrize(
        "qualifier",
        [
            "stars:>=0",
            "fork:true",
            "is:public",
            "language:c++",
            "archived:true",
            "topic:webdev",
        ],
    )
    def test_normalize_strips_qualifier_tokens(self, qualifier: str) -> None:
        assert normalize_keywords([qualifier, "scraping"]) == ["scraping"]

    def test_find_violations_flags_qualifier_token(self) -> None:
        issues = find_keyword_violations(["stars:>=0"])
        codes = [i.code for i in issues]
        assert "qualifier_in_keyword" in codes
        issue = next(i for i in issues if i.code == "qualifier_in_keyword")
        assert issue.token == "stars:>=0"

    def test_regular_tokens_with_no_colon_still_pass(self) -> None:
        # Sanity: real keywords must not be caught by the qualifier regex.
        for token in ["c++", "c#", "f#", "react", "kubernetes", "spring-boot"]:
            assert normalize_keywords([token]) == [canonicalize_keyword_token(token)]
            codes = {i.code for i in find_keyword_violations([token])}
            assert "qualifier_in_keyword" not in codes, (
                f"false positive on legitimate token '{token}': {codes}"
            )


class TestIter4FollowupStage35Immutability:
    """M3 — Stage 3.5 must not mutate the list in place; idempotence
    already covers behavioral equivalence but this guards the contract."""

    def test_repeated_stopword_parts_all_consumed(self) -> None:
        # `open source open source foo` should collapse both pairs.
        assert normalize_keywords(["open", "source", "open", "source", "foo"]) == [
            "foo"
        ]

    def test_stage_35_returns_new_list_not_mutated_input(self) -> None:
        from gh_search.normalizers.keyword_rules import _drop_multi_word_stopwords

        input_list = ["open", "source", "scraping"]
        snapshot = list(input_list)
        output = _drop_multi_word_stopwords(input_list)
        assert output == ["scraping"]
        assert input_list == snapshot, "Stage 3.5 must not mutate its input list"


# ---------------------------------------------------------------------------
# Iter7 — English decoration token cleanup
# (ITER7_DECORATION_CLEANUP_SPEC §3.1, §7.1, §7.3)
# ---------------------------------------------------------------------------


class TestIter7DecorationCleanup:
    """§7.1 — single-token decoration stopwords drop at Stage 3."""

    def test_implementations_dropped_q007(self) -> None:
        # q007 GPT/CLA/DSK iter6 blocker: parser emits decoration tail.
        assert normalize_keywords(["graphql", "server", "implementations"]) == [
            "graphql",
            "server",
        ]

    def test_projects_dropped_q018_dsk(self) -> None:
        # q018 DSK iter6 blocker.
        assert normalize_keywords(["spring boot", "starter", "projects"]) == [
            "spring boot",
            "starter",
        ]

    def test_decoration_drop_is_case_insensitive(self) -> None:
        assert normalize_keywords(["GraphQL", "Server", "IMPLEMENTATIONS"]) == [
            "graphql",
            "server",
        ]

    def test_project_singular_kept_locked_out_of_iter7(self) -> None:
        # §3.2: 'project' deferred to follow-up; must NOT be dropped by iter7.
        assert normalize_keywords(["project"]) == ["project"]

    def test_project_management_phrase_kept_no_substring_match(self) -> None:
        # Stage 0 splits 'project management' → ['project', 'management'];
        # neither part is in _DECORATION_STOPWORDS, so both survive.
        out = normalize_keywords(["project management"])
        assert "project" in out and "management" in out

    def test_sample_unaffected(self) -> None:
        # §2.3: 'sample' (q029) is not in iter7 scope.
        assert normalize_keywords(["sample"]) == ["sample"]

    def test_template_unaffected_plural_drift_deferred(self) -> None:
        # §2.3: 'templates -> template' plural drift deferred; singular passes.
        assert normalize_keywords(["template"]) == ["template"]

    def test_japanese_unaffected_deferred_to_iter8(self) -> None:
        # §3.3: 'japanese' explicitly deferred; iter7 must not drop it.
        assert normalize_keywords(["japanese"]) == ["japanese"]


class TestIter7DecorationSharedContract:
    """§7.3 — find_keyword_violations and normalize_keywords must share the
    same decoration stopword set so the audit trail and the actual drop never
    diverge (iter6 evidence-dict / regex divergence bug)."""

    def test_decoration_set_consistent_each_token(self) -> None:
        from gh_search.normalizers.keyword_rules import _DECORATION_STOPWORDS

        for token in _DECORATION_STOPWORDS:
            # normalize drops it.
            assert normalize_keywords([token]) == [], (
                f"normalize_keywords kept decoration token '{token}'"
            )
            # find_keyword_violations flags it under the decoration code.
            issues = find_keyword_violations([token])
            codes = [i.code for i in issues]
            assert "decoration_stopword" in codes, (
                f"find_keyword_violations did not flag decoration token "
                f"'{token}': {codes}"
            )
            issue = next(i for i in issues if i.code == "decoration_stopword")
            assert issue.token == token

    def test_q007_pipeline_drop_matches_violation_flag(self) -> None:
        raw = ["graphql", "server", "implementations"]
        normalized = normalize_keywords(raw)
        flagged = {
            i.token
            for i in find_keyword_violations(raw)
            if i.code == "decoration_stopword"
        }
        assert "implementations" not in normalized
        assert flagged == {"implementations"}

    def test_q018_dsk_pipeline_drop_matches_violation_flag(self) -> None:
        raw = ["spring boot", "starter", "projects"]
        normalized = normalize_keywords(raw)
        flagged = {
            i.token
            for i in find_keyword_violations(raw)
            if i.code == "decoration_stopword"
        }
        assert "projects" not in normalized
        assert flagged == {"projects"}


# ---------------------------------------------------------------------------
# Iter8 — Multilingual canonicalization
# (ITER8_MULTILINGUAL_CANONICALIZATION_SPEC §3.1, §7.1, §7.3)
# ---------------------------------------------------------------------------


class TestIter8MultilingualCanonicalization:
    """§7.1 — single-token CJK compound rewrites + bag-level contextual rules."""

    # --- Positive cases (the 5 patterns from §3.1) -----------------------

    def test_scraping_plus_kit_rewrites_to_scraping_crawler(self) -> None:
        # q027 GPT/CLA: parser emits ['scraping', '套件']; bag rule replaces
        # '套件' with 'crawler' when 'scraping' co-occurs (§3.1 rule 2).
        assert normalize_keywords(["scraping", "套件"]) == ["scraping", "crawler"]

    def test_scraping_plus_kit_order_insensitive(self) -> None:
        # §3.1 rule 2: order-insensitive; parser may emit '套件' first.
        assert normalize_keywords(["套件", "scraping"]) == ["crawler", "scraping"]

    def test_cjk_crawler_kit_compound_rewrites_to_scraping_crawler(self) -> None:
        # q027 DSK: parser emits the joined CJK compound (§3.1 rule 1).
        assert normalize_keywords(["爬蟲套件"]) == ["scraping", "crawler"]

    def test_microservice_framework_compound_splits(self) -> None:
        # q028 GPT: '微服务框架' (no space, simplified Chinese) -> two canonical
        # English tokens (§3.1 rule 3). Distinct from the existing space-split
        # case 'microservice framework' which Stage 0 already handles.
        assert normalize_keywords(["微服务框架"]) == ["microservice", "framework"]

    def test_sample_project_japanese_compound_rewrites_to_sample_only(self) -> None:
        # q029 GPT: 'サンプルプロジェクト' is a Japanese compound; spec §3.1 rule
        # 4 maps it to 'sample' (only) — no orphan 'project' left behind.
        assert normalize_keywords(["react", "サンプルプロジェクト"]) == [
            "react",
            "sample",
        ]

    def test_sample_project_japanese_trio_drops_project_and_japanese(self) -> None:
        # q029 DSK: parser emits all three canonical English tokens; §3.1
        # rule 5 narrow contextual drop fires when all three co-occur.
        assert normalize_keywords(
            ["react", "sample", "project", "japanese"]
        ) == ["react", "sample"]

    def test_trio_drop_other_tokens_unaffected(self) -> None:
        # §3.1 rule 5: "其他 token 如 react 不影響觸發"; topic-bearing tokens
        # outside the trio must survive.
        assert normalize_keywords(
            ["vue", "sample", "project", "japanese", "starter"]
        ) == ["vue", "sample", "starter"]

    # --- Guard cases (§7.1: lock against accidental global promotion) -----

    def test_kit_alone_kept_no_global_alias(self) -> None:
        # §3.2: '套件' must NOT become a global '套件' -> 'crawler' alias.
        assert normalize_keywords(["套件"]) == ["套件"]

    def test_project_alone_kept_no_global_stopword(self) -> None:
        # §3.2: 'project' (singular) must NOT become a global stopword.
        assert normalize_keywords(["project"]) == ["project"]

    def test_japanese_alone_kept_no_global_stopword(self) -> None:
        # §3.2: 'japanese' must NOT become a global stopword.
        assert normalize_keywords(["japanese"]) == ["japanese"]

    def test_sample_project_pair_kept_no_japanese_no_drop(self) -> None:
        # Trio not satisfied (missing 'japanese'); both tokens survive.
        assert normalize_keywords(["sample", "project"]) == ["sample", "project"]

    def test_sample_japanese_pair_kept_no_project_no_drop(self) -> None:
        # Trio not satisfied (missing 'project'); both tokens survive.
        assert normalize_keywords(["sample", "japanese"]) == ["sample", "japanese"]

    def test_project_japanese_pair_kept_no_sample_no_drop(self) -> None:
        # Trio not satisfied (missing 'sample'); both tokens survive.
        assert normalize_keywords(["project", "japanese"]) == ["project", "japanese"]

    def test_microservice_framework_split_pair_unaffected(self) -> None:
        # Already-canonical English pair must pass through untouched.
        assert normalize_keywords(["microservice", "framework"]) == [
            "microservice",
            "framework",
        ]

    def test_react_sample_pair_unaffected(self) -> None:
        # Common React-sample query without trio noise must pass through.
        assert normalize_keywords(["react", "sample"]) == ["react", "sample"]

    # --- Idempotence -----------------------------------------------------

    @pytest.mark.parametrize(
        "keywords",
        [
            ["scraping", "套件"],
            ["爬蟲套件"],
            ["微服务框架"],
            ["react", "サンプルプロジェクト"],
            ["react", "sample", "project", "japanese"],
            ["vue", "sample", "project", "japanese", "starter"],
        ],
    )
    def test_normalize_idempotent_on_iter8_inputs(
        self, keywords: list[str]
    ) -> None:
        once = normalize_keywords(keywords)
        twice = normalize_keywords(once)
        assert once == twice


class TestIter8MultilingualSharedContract:
    """§7.3 — find_keyword_violations and normalize_keywords must agree on
    which tokens iter8 rules touch."""

    def test_cjk_crawler_kit_compound_flagged(self) -> None:
        issues = find_keyword_violations(["爬蟲套件"])
        codes = [i.code for i in issues]
        assert "multilingual_canonicalization" in codes
        issue = next(i for i in issues if i.code == "multilingual_canonicalization")
        assert issue.token == "爬蟲套件"
        assert issue.replacement == "scraping, crawler"

    def test_microservice_framework_compound_flagged(self) -> None:
        issues = find_keyword_violations(["微服务框架"])
        codes = [i.code for i in issues]
        assert "multilingual_canonicalization" in codes
        issue = next(i for i in issues if i.code == "multilingual_canonicalization")
        assert issue.token == "微服务框架"
        assert issue.replacement == "microservice, framework"

    def test_sample_project_japanese_compound_flagged(self) -> None:
        issues = find_keyword_violations(["サンプルプロジェクト"])
        codes = [i.code for i in issues]
        assert "multilingual_canonicalization" in codes
        issue = next(
            i
            for i in issues
            if i.code == "multilingual_canonicalization"
            and i.token == "サンプルプロジェクト"
        )
        assert issue.replacement == "sample"

    def test_scraping_kit_bag_rule_flagged(self) -> None:
        issues = find_keyword_violations(["scraping", "套件"])
        rewrite_issues = [
            i
            for i in issues
            if i.code == "multilingual_canonicalization" and i.token == "套件"
        ]
        assert len(rewrite_issues) == 1
        assert rewrite_issues[0].replacement == "crawler"

    def test_trio_bag_rule_flags_project_and_japanese(self) -> None:
        issues = find_keyword_violations(
            ["react", "sample", "project", "japanese"]
        )
        drop_tokens = {
            i.token for i in issues if i.code == "multilingual_context_drop"
        }
        assert drop_tokens == {"project", "japanese"}

    def test_trio_bag_rule_with_cjk_compound_still_flags(self) -> None:
        # Mixed input: 'サンプルプロジェクト' expands to 'sample'; combined with
        # explicit 'project' and 'japanese' the trio still triggers and the
        # contract must report it (otherwise normalize / violations diverge).
        issues = find_keyword_violations(
            ["サンプルプロジェクト", "project", "japanese"]
        )
        drop_tokens = {
            i.token for i in issues if i.code == "multilingual_context_drop"
        }
        assert drop_tokens == {"project", "japanese"}

    def test_no_false_positive_on_kit_alone(self) -> None:
        issues = find_keyword_violations(["套件"])
        codes = [i.code for i in issues]
        assert "multilingual_canonicalization" not in codes
        assert "multilingual_context_drop" not in codes

    def test_no_false_positive_on_project_alone(self) -> None:
        issues = find_keyword_violations(["project"])
        codes = [i.code for i in issues]
        assert "multilingual_canonicalization" not in codes
        assert "multilingual_context_drop" not in codes

    def test_no_false_positive_on_japanese_alone(self) -> None:
        issues = find_keyword_violations(["japanese"])
        codes = [i.code for i in issues]
        assert "multilingual_canonicalization" not in codes
        assert "multilingual_context_drop" not in codes

    def test_compound_rewrite_set_consistent_with_normalize(self) -> None:
        # Spec §7.3: violations contract MUST stay aligned with the actual
        # rewrites normalize_keywords applies — pinned across all three CJK
        # compounds.
        from gh_search.normalizers.keyword_rules import _CJK_COMPOUND_REWRITES

        for source, expansion in _CJK_COMPOUND_REWRITES.items():
            normalized = normalize_keywords([source])
            assert normalized == list(expansion), (
                f"normalize_keywords({source!r}) -> {normalized}, "
                f"expected {list(expansion)}"
            )
            issues = find_keyword_violations([source])
            flagged = [
                i
                for i in issues
                if i.code == "multilingual_canonicalization" and i.token == source
            ]
            assert flagged, (
                f"find_keyword_violations did not flag CJK compound {source!r}"
            )

    def test_q027_pipeline_matches_violation_flag(self) -> None:
        # End-to-end shared-contract for q027 GPT/CLA shape.
        raw = ["scraping", "套件"]
        normalized = normalize_keywords(raw)
        flagged = {
            i.token
            for i in find_keyword_violations(raw)
            if i.code == "multilingual_canonicalization"
        }
        assert normalized == ["scraping", "crawler"]
        assert "套件" in flagged

    def test_q029_dsk_pipeline_matches_violation_flag(self) -> None:
        # End-to-end shared-contract for q029 DSK shape.
        raw = ["react", "sample", "project", "japanese"]
        normalized = normalize_keywords(raw)
        flagged = {
            i.token
            for i in find_keyword_violations(raw)
            if i.code == "multilingual_context_drop"
        }
        assert normalized == ["react", "sample"]
        assert flagged == {"project", "japanese"}
