"""Prompt composition (PHASE2_PLAN.md §3.0).

Lays the `prompts/core/{name}-v{N}.md` + `prompts/appendix/{name}-{model}-v{N}.md`
filesystem layout into a tiny loader. Adapters stay pure: they treat
composed text as opaque `system_prompt`, and model-specific appendices are
bound at factory time (PHASE2_PLAN §1.1 — model-specific tuning stays
isolated from the core layer).

Naming:
- `name` identifies the tool / prompt role (e.g. `parse`, `intention`).
- `model` must already be canonicalised (use `canonical_model_name(...)`).
- versions are separate for core and appendix so Iteration 1 tuning can
  bump one without touching the other.

Returns `PromptBundle` with the composed system prompt and the canonical
`prompt_version` label written into run_config / matrix rows.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROMPTS_ROOT = _PROJECT_ROOT / "prompts"


@dataclass(frozen=True)
class PromptBundle:
    core_text: str
    appendix_text: str | None
    prompt_version: str

    @property
    def composed_system(self) -> str:
        """Return the concatenated system prompt (core + appendix).

        When the appendix file exists but is empty-or-comment-only, it
        collapses to just the core text so the model doesn't see trailing
        whitespace (which can meaningfully perturb some models).
        """
        core = self.core_text.strip()
        if not self.appendix_text:
            return core
        return f"{core}\n\n{self.appendix_text.strip()}"


def load_prompt_bundle(
    name: str,
    model: str,
    *,
    core_version: str = "v1",
    appendix_version: str = "v1",
    prompts_root: Path | None = None,
) -> PromptBundle:
    root = Path(prompts_root) if prompts_root is not None else DEFAULT_PROMPTS_ROOT
    core_path = root / "core" / f"{name}-{core_version}.md"
    appendix_path = root / "appendix" / f"{name}-{model}-{appendix_version}.md"

    core_text = _read_text(core_path, required=True)
    appendix_text = _read_text(appendix_path, required=False)

    if appendix_text is not None and not _has_non_comment_content(appendix_text):
        appendix_text = None

    prompt_version = (
        f"core-{core_version} + appendix-{model}-{appendix_version}"
    )
    return PromptBundle(
        core_text=core_text,
        appendix_text=appendix_text,
        prompt_version=prompt_version,
    )


def compose_system_for(name: str, llm, *, default_model: str = "gpt-4.1-mini") -> str:
    """Read the prompt bundle for (tool `name`, model bound to `llm`).

    Tools call this at invocation time so the model actually *sees* the
    content of `prompts/core/*.md` and the per-model appendix. When an
    `llm` closure wasn't decorated with `.model_name` (e.g. a hand-built
    test stub) we fall back to `default_model` rather than crashing — the
    real runtime adapters all set the attribute.
    """
    model = getattr(llm, "model_name", None) or default_model
    bundle = load_prompt_bundle(name, model)
    return bundle.composed_system


def _read_text(path: Path, *, required: bool) -> str | None:
    if not path.is_file():
        if required:
            raise FileNotFoundError(f"prompt file missing: {path}")
        return None
    return path.read_text(encoding="utf-8")


_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def _has_non_comment_content(text: str) -> bool:
    stripped = _HTML_COMMENT.sub("", text).strip()
    return bool(stripped)


__all__ = [
    "DEFAULT_PROMPTS_ROOT",
    "PromptBundle",
    "compose_system_for",
    "load_prompt_bundle",
]
