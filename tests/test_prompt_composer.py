"""Prompt composer loads core + optional appendix (PHASE2_PLAN §3.0)."""
from __future__ import annotations

from pathlib import Path

import pytest

from gh_search.llm.prompts import load_prompt_bundle


def _seed(prompts_root: Path, *, core: str, appendix: str | None = None,
          name: str = "parse", model: str = "test-model") -> None:
    core_dir = prompts_root / "core"
    app_dir = prompts_root / "appendix"
    core_dir.mkdir(parents=True, exist_ok=True)
    app_dir.mkdir(parents=True, exist_ok=True)
    (core_dir / f"{name}-v1.md").write_text(core, encoding="utf-8")
    if appendix is not None:
        (app_dir / f"{name}-{model}-v1.md").write_text(appendix, encoding="utf-8")


def test_load_prompt_bundle_core_only(tmp_path: Path):
    _seed(tmp_path, core="CORE")
    b = load_prompt_bundle("parse", "test-model", prompts_root=tmp_path)
    assert b.core_text == "CORE"
    assert b.appendix_text is None
    assert b.prompt_version == "core-v1 + appendix-test-model-v1"


def test_load_prompt_bundle_with_appendix(tmp_path: Path):
    _seed(tmp_path, core="CORE_RULES", appendix="MORE")
    b = load_prompt_bundle("parse", "test-model", prompts_root=tmp_path)
    assert b.appendix_text == "MORE"


def test_load_prompt_bundle_ignores_empty_comment_appendix(tmp_path: Path):
    _seed(
        tmp_path,
        core="CORE",
        appendix="<!-- intentionally empty baseline -->\n",
    )
    b = load_prompt_bundle("parse", "test-model", prompts_root=tmp_path)
    # A placeholder appendix file with only HTML comments should read as "no
    # appendix" so the composed prompt doesn't grow trailing whitespace.
    assert b.appendix_text is None


def test_load_prompt_bundle_missing_core_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_prompt_bundle("parse", "test-model", prompts_root=tmp_path)


def test_real_prompts_directory_contains_phase2_baseline():
    # Self-check: the repo itself carries a populated core + appendix
    # scaffolding for the Phase 2 baseline models (PHASE2_PLAN §1.1).
    for model in ("gpt-4.1-mini", "claude-sonnet-4", "deepseek-r1"):
        b = load_prompt_bundle("parse", model)
        assert b.core_text.strip()  # non-empty
        assert b.prompt_version == f"core-v1 + appendix-{model}-v1"
