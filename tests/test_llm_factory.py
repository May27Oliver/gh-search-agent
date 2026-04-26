"""Factory routing (PHASE2_PLAN §3.0)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gh_search.llm.factory import (
    LLMBinding,
    ProviderConfigError,
    UnknownModelError,
    canonical_model_name,
    make_llm,
    provider_for,
)


def test_canonical_model_name_accepts_only_the_three_canonical_models():
    assert canonical_model_name("GPT-4.1-mini") == "gpt-4.1-mini"
    assert canonical_model_name("CLAUDE-SONNET-4") == "claude-sonnet-4"
    assert canonical_model_name("DeepSeek-R1") == "deepseek-r1"


def test_canonical_model_name_rejects_unknown():
    with pytest.raises(UnknownModelError):
        canonical_model_name("totally-made-up-model-v9")
    with pytest.raises(UnknownModelError):
        canonical_model_name("gpt-4.1")
    with pytest.raises(UnknownModelError):
        canonical_model_name("claude-sonnet-4.5")
    with pytest.raises(UnknownModelError):
        canonical_model_name("deepseek-reasoner")


def test_provider_for_uses_canonical_form():
    assert provider_for("claude-sonnet-4") == "anthropic"
    assert provider_for("CLAUDE-SONNET-4") == "anthropic"
    assert provider_for("deepseek-r1") == "deepseek"


@patch("gh_search.llm.factory.make_openai_llm")
def test_make_llm_routes_openai(mock_make):
    mock_make.return_value = MagicMock(name="openai-closure")
    binding = make_llm("gpt-4.1-mini", openai_api_key="sk-x")
    assert isinstance(binding, LLMBinding)
    assert binding.provider_name == "openai"
    assert binding.model_name == "gpt-4.1-mini"
    mock_make.assert_called_once()
    assert mock_make.call_args.kwargs["model"] == "gpt-4.1-mini"


@patch("gh_search.llm.factory.make_anthropic_llm")
def test_make_llm_routes_anthropic(mock_make):
    mock_make.return_value = MagicMock(name="anthropic-closure")
    binding = make_llm("claude-sonnet-4", anthropic_api_key="ant-key")
    assert binding.provider_name == "anthropic"
    assert binding.model_name == "claude-sonnet-4"  # canonical form
    assert mock_make.call_args.kwargs["model"] == "claude-sonnet-4"


@patch("gh_search.llm.factory.make_deepseek_llm")
def test_make_llm_routes_deepseek(mock_make):
    mock_make.return_value = MagicMock(name="deepseek-closure")
    binding = make_llm(
        "DeepSeek-R1",
        deepseek_api_key="ds-key",
        deepseek_endpoint="https://api.deepseek.com",
    )
    assert binding.provider_name == "deepseek"
    # Endpoint is an adapter-internal concern; the factory forwards it to
    # `make_deepseek_llm` but doesn't leak it onto the binding.
    assert mock_make.call_args.kwargs["endpoint_url"] == "https://api.deepseek.com"


def test_make_llm_requires_openai_key():
    with pytest.raises(ProviderConfigError):
        make_llm("gpt-4.1-mini")  # no key


def test_make_llm_requires_anthropic_key():
    with pytest.raises(ProviderConfigError):
        make_llm("claude-sonnet-4")  # no key


def test_make_llm_requires_deepseek_key():
    with pytest.raises(ProviderConfigError):
        make_llm("deepseek-r1")

