"""Task 3.6 RED: OpenAI adapter realizes LLMJsonCall for gpt-4.1-mini."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from gh_search.llm.openai_client import make_openai_llm


def _fake_completion(payload: dict):
    message = MagicMock()
    message.content = json.dumps(payload)
    choice = MagicMock(message=message)
    return MagicMock(choices=[choice])


@patch("gh_search.llm.openai_client.OpenAI")
def test_adapter_returns_llm_response_with_raw_and_parsed(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    payload = {"intent_status": "supported", "reason": None, "should_terminate": False}
    mock_client.chat.completions.create.return_value = _fake_completion(payload)

    llm = make_openai_llm(api_key="sk-test", model="gpt-4.1-mini")
    out = llm("system prompt", "user query", {"type": "object"})

    assert out.parsed == payload
    assert out.raw_text == json.dumps(payload)


@patch("gh_search.llm.openai_client.OpenAI")
def test_adapter_sends_system_and_user_messages(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _fake_completion({})

    llm = make_openai_llm(api_key="sk-test", model="gpt-4.1-mini")
    llm("SYS", "USER", {"type": "object"})

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4.1-mini"
    assert call_kwargs["messages"][0] == {"role": "system", "content": "SYS"}
    assert call_kwargs["messages"][1] == {"role": "user", "content": "USER"}


@patch("gh_search.llm.openai_client.OpenAI")
def test_adapter_sets_temperature_zero_for_determinism(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _fake_completion({})

    llm = make_openai_llm(api_key="sk-test", model="gpt-4.1-mini")
    llm("SYS", "USER", {"type": "object"})

    assert mock_client.chat.completions.create.call_args.kwargs["temperature"] == 0


@patch("gh_search.llm.openai_client.OpenAI")
def test_adapter_passes_response_schema_as_json_schema(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _fake_completion({})

    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    llm = make_openai_llm(api_key="sk-test", model="gpt-4.1-mini")
    llm("SYS", "USER", schema)

    rf = mock_client.chat.completions.create.call_args.kwargs["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["schema"] == schema
