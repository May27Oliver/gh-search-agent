"""DeepSeek adapter realizes LLMJsonCall via an OpenAI-compatible endpoint."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
from openai import BadRequestError

from gh_search.llm.deepseek_client import make_deepseek_llm


def _fake_completion(payload: dict, finish_reason: str = "stop"):
    message = MagicMock()
    message.content = json.dumps(payload)
    choice = MagicMock(message=message, finish_reason=finish_reason)
    usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    return MagicMock(choices=[choice], usage=usage, id="deepseek-1")


@patch("gh_search.llm.deepseek_client.OpenAI")
def test_deepseek_adapter_uses_official_endpoint_by_default(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _fake_completion({"keywords": ["x"]})

    llm = make_deepseek_llm(api_key="dskey", model="deepseek-r1")
    out = llm("SYS", "USER", {"type": "object"})

    assert mock_openai_cls.call_args.kwargs["base_url"] == "https://api.deepseek.com"
    assert mock_openai_cls.call_args.kwargs["api_key"] == "dskey"
    assert client.chat.completions.create.call_args.kwargs["model"] == "deepseek-reasoner"
    assert out.parsed == {"keywords": ["x"]}
    assert out.provider_name == "deepseek"
    assert out.model_name == "deepseek-r1"
    assert out.provider_response_id == "deepseek-1"


@patch("gh_search.llm.deepseek_client.OpenAI")
def test_deepseek_adapter_honors_custom_endpoint(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _fake_completion({})

    llm = make_deepseek_llm(
        api_key="k",
        endpoint_url="https://gateway.example.com/v1",
        model="deepseek-r1",
    )
    llm("SYS", "USER", {"type": "object"})
    assert mock_openai_cls.call_args.kwargs["base_url"] == "https://gateway.example.com/v1"


@patch("gh_search.llm.deepseek_client.OpenAI")
def test_deepseek_adapter_falls_back_to_json_object_mode(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    client.chat.completions.create.return_value = _fake_completion({})

    llm = make_deepseek_llm(
        api_key="k",
        json_schema_support=False,
    )
    llm("SYS", "USER", {"type": "object"})

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["response_format"] == {"type": "json_object"}
    assert "Schema:" in kwargs["messages"][0]["content"]


@patch("gh_search.llm.deepseek_client.OpenAI")
def test_deepseek_adapter_retries_when_json_schema_unavailable(mock_openai_cls):
    client = MagicMock()
    mock_openai_cls.return_value = client
    req = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    resp = httpx.Response(400, request=req)
    client.chat.completions.create.side_effect = [
        BadRequestError(
            "This response_format type is unavailable now: json_schema",
            response=resp,
            body={
                "error": {
                    "message": "This response_format type is unavailable now",
                    "type": "invalid_request_error",
                }
            },
        ),
        _fake_completion({"keywords": ["x"]}),
    ]

    llm = make_deepseek_llm(api_key="k", model="deepseek-r1")
    out = llm("SYS", "USER", {"type": "object"})

    assert out.parsed == {"keywords": ["x"]}
    assert client.chat.completions.create.call_count == 2
    first_kwargs = client.chat.completions.create.call_args_list[0].kwargs
    second_kwargs = client.chat.completions.create.call_args_list[1].kwargs
    assert first_kwargs["response_format"]["type"] == "json_schema"
    assert second_kwargs["response_format"] == {"type": "json_object"}
    assert "Schema:" in second_kwargs["messages"][0]["content"]
