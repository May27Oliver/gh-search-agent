"""Provider adapter factory (PHASE2_PLAN.md §3.0).

One function — `make_llm(...)` — is the only place CLI / runner / tests go
to construct an `LLMJsonCall`. The factory owns:

- canonical-name normalization (lowercase kebab-case; PHASE2_PLAN §1.1)
- alias resolution (`claude-sonnet-4-5` → `claude-sonnet-4`, etc.)
- model → provider routing
- per-provider config injection (API keys, endpoint, timeout)
- optional per-model prompt appendix binding

Every caller stays provider-agnostic — they pass a canonical model name and
get back an `LLMJsonCall`. Downstream code never imports a provider-specific
adapter module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gh_search.llm import LLMJsonCall
from gh_search.llm.anthropic_client import make_anthropic_llm
from gh_search.llm.deepseek_client import make_deepseek_llm
from gh_search.llm.openai_client import make_openai_llm

ProviderName = Literal["openai", "anthropic", "deepseek"]

# Canonical names are lowercase kebab-case (PHASE2_PLAN §1.1). CLI / env values
# can use any recognised alias; runtime always resolves back to canonical.
MODEL_ALIASES: dict[str, str] = {
    # OpenAI
    "gpt-4.1-mini": "gpt-4.1-mini",
    "gpt4.1-mini": "gpt-4.1-mini",
    "gpt-4.1": "gpt-4.1",
    # Anthropic
    "claude-sonnet-4": "claude-sonnet-4",
    "claude-sonnet-4.5": "claude-sonnet-4",
    "claude-sonnet-4-5": "claude-sonnet-4",
    "claude-3-5-sonnet": "claude-sonnet-4",
    "sonnet-4": "claude-sonnet-4",
    # DeepSeek
    "deepseek-r1": "deepseek-r1",
    "deepseek r1": "deepseek-r1",
    "deepseek-reasoner": "deepseek-r1",
}

PROVIDER_BY_MODEL: dict[str, ProviderName] = {
    "gpt-4.1-mini": "openai",
    "gpt-4.1": "openai",
    "claude-sonnet-4": "anthropic",
    "deepseek-r1": "deepseek",
}


class UnknownModelError(ValueError):
    pass


class ProviderConfigError(ValueError):
    pass


@dataclass(frozen=True)
class LLMBinding:
    """Resolved factory output — includes the callable and its metadata.

    The metadata is what runner / CLI persists into run_config.json so the
    matrix aggregator can read `provider_name` / `model_name` without having
    to look at the callable's closure.
    """

    call: LLMJsonCall
    provider_name: ProviderName
    model_name: str


def canonical_model_name(raw: str) -> str:
    key = (raw or "").strip().lower()
    if not key:
        raise UnknownModelError("empty model name")
    if key in MODEL_ALIASES:
        return MODEL_ALIASES[key]
    # Allow direct canonical names we may have added that aren't in aliases.
    if key in PROVIDER_BY_MODEL:
        return key
    raise UnknownModelError(f"unknown model: {raw!r}")


def provider_for(model_name: str) -> ProviderName:
    canonical = canonical_model_name(model_name)
    try:
        return PROVIDER_BY_MODEL[canonical]
    except KeyError as exc:
        raise UnknownModelError(f"no provider mapping for canonical model: {canonical}") from exc


def make_llm(
    model_name: str,
    *,
    openai_api_key: str | None = None,
    anthropic_api_key: str | None = None,
    deepseek_api_key: str | None = None,
    deepseek_endpoint: str | None = None,
    temperature: float = 0,
    timeout_seconds: float | None = None,
    deepseek_json_schema_support: bool = True,
    provider_override: ProviderName | None = None,
) -> LLMBinding:
    """Build an LLMBinding for the given model.

    Prompt composition (core + per-model appendix) happens at the tool layer
    via `gh_search.llm.prompts.load_prompt_bundle` — tools introspect
    `llm.model_name` on the returned call to decide which appendix file to
    read. That keeps the adapter contract independent of prompt layering so
    a given adapter can serve multiple tools with different prompts.
    """
    canonical = canonical_model_name(model_name)
    provider = provider_override or PROVIDER_BY_MODEL.get(canonical)
    if provider is None:
        raise UnknownModelError(f"no provider mapping for model: {canonical}")

    if provider == "openai":
        if not openai_api_key:
            raise ProviderConfigError("OPENAI_API_KEY required for openai provider")
        call = make_openai_llm(
            api_key=openai_api_key,
            model=canonical,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )
        return LLMBinding(call=call, provider_name="openai", model_name=canonical)

    if provider == "anthropic":
        if not anthropic_api_key:
            raise ProviderConfigError("ANTHROPIC_API_KEY required for anthropic provider")
        call = make_anthropic_llm(
            api_key=anthropic_api_key,
            model=canonical,
            temperature=temperature,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else 60.0,
        )
        return LLMBinding(call=call, provider_name="anthropic", model_name=canonical)

    if provider == "deepseek":
        if not deepseek_api_key:
            raise ProviderConfigError("DEEPSEEK_API_KEY required for deepseek provider")
        call = make_deepseek_llm(
            api_key=deepseek_api_key,
            endpoint_url=deepseek_endpoint,
            model=canonical,
            temperature=temperature,
            timeout_seconds=timeout_seconds if timeout_seconds is not None else 60.0,
            json_schema_support=deepseek_json_schema_support,
        )
        return LLMBinding(call=call, provider_name="deepseek", model_name=canonical)

    raise UnknownModelError(f"unsupported provider: {provider}")


__all__ = [
    "LLMBinding",
    "MODEL_ALIASES",
    "PROVIDER_BY_MODEL",
    "ProviderConfigError",
    "ProviderName",
    "UnknownModelError",
    "canonical_model_name",
    "make_llm",
    "provider_for",
]
