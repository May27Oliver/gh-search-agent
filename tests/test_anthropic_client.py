"""Anthropic adapter realizes LLMJsonCall via forced tool_use (PHASE2_PLAN §3.0).

Uses an injected `http_post` so we exercise the full request/response shape
without mocking the SDK or making network calls.
"""
from __future__ import annotations

import json

from gh_search.llm.anthropic_client import make_anthropic_llm


def _fake_success_payload(schema_match: dict) -> dict:
    return {
        "id": "msg_01abc",
        "model": "claude-sonnet-4",
        "stop_reason": "tool_use",
        "content": [
            {
                "type": "tool_use",
                "name": "emit_gh_search_response",
                "input": schema_match,
            }
        ],
        "usage": {"input_tokens": 123, "output_tokens": 45},
    }


def test_anthropic_adapter_returns_parsed_tool_input():
    calls = {}

    def http_post(url, headers, body, timeout):
        calls["url"] = url
        calls["headers"] = headers
        calls["body"] = json.loads(body)
        return _fake_success_payload({"keywords": ["orm"], "language": "Go"})

    llm = make_anthropic_llm(
        api_key="ak-test",
        model="claude-sonnet-4",
        http_post=http_post,
    )
    out = llm("SYS", "USER", {"type": "object", "properties": {"keywords": {"type": "array"}}})

    assert out.parsed == {"keywords": ["orm"], "language": "Go"}
    assert out.provider_name == "anthropic"
    assert out.model_name == "claude-sonnet-4"
    assert out.finish_reason == "tool_use"
    assert out.provider_response_id == "msg_01abc"
    assert out.usage == {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168}
    # raw_text is a serialization of the parsed tool input so raw_model_output
    # in session logs stays faithful.
    assert json.loads(out.raw_text) == out.parsed


def test_anthropic_adapter_sends_correct_request_shape():
    captured = {}

    def http_post(url, headers, body, timeout):
        captured["headers"] = headers
        captured["body"] = json.loads(body)
        return _fake_success_payload({})

    llm = make_anthropic_llm(
        api_key="ak-test",
        model="claude-sonnet-4",
        temperature=0,
        http_post=http_post,
    )
    llm("SYS_PROMPT", "USER_MSG", {"type": "object"})

    assert captured["headers"]["x-api-key"] == "ak-test"
    assert captured["headers"]["anthropic-version"]
    body = captured["body"]
    # PHASE2_PLAN §1.1: canonical name stays kebab-case in logs/matrix, but
    # Anthropic's API only accepts snapshot IDs — the adapter translates at
    # the wire boundary. Canonical `claude-sonnet-4` → snapshot id.
    assert body["model"] == "claude-sonnet-4-20250514"
    assert body["system"] == "SYS_PROMPT"
    assert body["temperature"] == 0
    assert body["messages"] == [{"role": "user", "content": "USER_MSG"}]
    assert body["tool_choice"] == {"type": "tool", "name": "emit_gh_search_response"}
    assert body["tools"][0]["name"] == "emit_gh_search_response"
    assert body["tools"][0]["input_schema"] == {"type": "object"}


def test_anthropic_adapter_translates_canonical_to_snapshot_id_on_wire():
    """Canonical `claude-sonnet-4` (PHASE2_PLAN §1.1) must reach Anthropic
    as the concrete snapshot id the API accepts, while `.model_name` and
    the response's `model_name` stay canonical for logs / matrix rows."""
    captured = {}

    def http_post(url, headers, body, timeout):
        captured["body"] = json.loads(body)
        return _fake_success_payload({})

    llm = make_anthropic_llm(api_key="ak-test", model="claude-sonnet-4", http_post=http_post)
    out = llm("S", "U", {"type": "object"})

    assert captured["body"]["model"] == "claude-sonnet-4-20250514"
    assert llm.model_name == "claude-sonnet-4"
    assert out.model_name == "claude-sonnet-4"


def test_anthropic_adapter_passes_unknown_model_through_unchanged():
    """A model name not in the snapshot map (e.g. a brand-new snapshot id
    the user hand-passes) must be forwarded as-is rather than silently
    dropped — this keeps us from blocking on a map update when Anthropic
    ships a new snapshot."""
    captured = {}

    def http_post(url, headers, body, timeout):
        captured["body"] = json.loads(body)
        return _fake_success_payload({})

    llm = make_anthropic_llm(
        api_key="ak-test", model="claude-sonnet-4-99991231", http_post=http_post
    )
    llm("S", "U", {"type": "object"})
    assert captured["body"]["model"] == "claude-sonnet-4-99991231"


def test_anthropic_adapter_exposes_model_name_for_tool_composition():
    """The closure must carry `.model_name` so tools can look up the
    per-model appendix at call time (PHASE2_PLAN §3.0)."""

    def http_post(url, headers, body, timeout):
        return _fake_success_payload({})

    llm = make_anthropic_llm(
        api_key="ak-test",
        model="claude-sonnet-4",
        http_post=http_post,
    )
    assert llm.model_name == "claude-sonnet-4"
    assert llm.provider_name == "anthropic"


def test_anthropic_adapter_passes_system_prompt_through_unchanged():
    captured = {}

    def http_post(url, headers, body, timeout):
        captured["body"] = json.loads(body)
        return _fake_success_payload({})

    llm = make_anthropic_llm(api_key="ak-test", http_post=http_post)
    llm("CORE_PROMPT_FROM_FILE", "U", {"type": "object"})

    # Adapters no longer compose appendix themselves — composition happens
    # at the tool layer. The adapter must forward `system_prompt` verbatim.
    assert captured["body"]["system"] == "CORE_PROMPT_FROM_FILE"


def test_anthropic_adapter_handles_missing_tool_use_block():
    """Provider drift: if a future version returns only text, we should still
    return a response (possibly empty-parsed) rather than crash. Upstream
    validation remains responsible for catching bad parses."""

    def http_post(url, headers, body, timeout):
        return {
            "id": "msg_text",
            "model": "claude-sonnet-4",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": '{"keywords": ["abc"]}'}],
            "usage": {"input_tokens": 5, "output_tokens": 2},
        }

    llm = make_anthropic_llm(api_key="ak", http_post=http_post)
    out = llm("SYS", "USER", {"type": "object"})
    assert out.parsed == {"keywords": ["abc"]}
    assert out.provider_name == "anthropic"
