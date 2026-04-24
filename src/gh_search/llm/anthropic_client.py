"""Anthropic realization of LLMJsonCall (PHASE2_PLAN.md §3.0).

Anthropic's Messages API does not natively expose JSON-schema structured
output like OpenAI's `response_format=json_schema`. The canonical workaround
is a single `tool_use` tool whose `input_schema` IS the target schema; the
model is then required to emit that tool call. We parse the tool-call `input`
as the structured JSON response, which guarantees schema conformance without
relying on prose-level instructions.

We hit the REST endpoint with `urllib` instead of adding the `anthropic` SDK
as a dependency. Swapping in the official SDK later is a one-file change.

The returned closure carries `model_name` / `provider_name` attrs so tools
can compose per-model prompts via `llm.model_name`.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from gh_search.llm import LLMJsonCall, LLMResponse

PROVIDER_NAME = "anthropic"

_DEFAULT_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_TOOL_NAME = "emit_gh_search_response"

# Anthropic only accepts concrete snapshot IDs on `/v1/messages`, not family
# aliases. PHASE2_PLAN §1.1 fixes our canonical names as lowercase kebab-case
# family labels (`claude-sonnet-4`), so the adapter translates at the wire
# boundary. Logs / matrix stay on the canonical name; the API gets the
# snapshot. Unknown canonicals fall through unchanged so a future snapshot can
# be passed through without a code change. Only canonicals that `factory.py`
# actually routes here belong in this map.
_API_MODEL_ID: dict[str, str] = {
    "claude-sonnet-4": "claude-sonnet-4-20250514",
}


def _to_api_model_id(canonical: str) -> str:
    return _API_MODEL_ID.get(canonical, canonical)


def make_anthropic_llm(
    api_key: str,
    model: str = "claude-sonnet-4",
    *,
    temperature: float = 0,
    timeout_seconds: float | None = 60.0,
    max_tokens: int = 1024,
    endpoint_url: str = _DEFAULT_URL,
    http_post=None,
) -> LLMJsonCall:
    """Return an `LLMJsonCall` backed by Anthropic Messages API.

    `http_post` is injectable for tests: it takes `(url, headers, body_bytes,
    timeout)` and returns a dict body. Defaults to urllib.
    """
    poster = http_post or _urllib_post

    api_model_id = _to_api_model_id(model)

    def call(system_prompt: str, user_message: str, response_schema: dict) -> LLMResponse:
        body = {
            "model": api_model_id,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
            "tools": [
                {
                    "name": _TOOL_NAME,
                    "description": (
                        "Emit the parsed GitHub search response as structured JSON. "
                        "You MUST call this tool exactly once."
                    ),
                    "input_schema": response_schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": _TOOL_NAME},
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }

        started = time.perf_counter()
        payload = poster(endpoint_url, headers, json.dumps(body).encode("utf-8"), timeout_seconds)
        latency_ms = int((time.perf_counter() - started) * 1000)

        parsed, raw_text = _extract_tool_input(payload)
        usage = _usage_dict(payload.get("usage"))
        response_id = payload.get("id")
        finish_reason = payload.get("stop_reason")

        return LLMResponse(
            raw_text=raw_text,
            parsed=parsed,
            provider_name=PROVIDER_NAME,
            model_name=model,
            finish_reason=finish_reason,
            usage=usage,
            latency_ms=latency_ms,
            provider_response_id=response_id,
        )

    call.model_name = model  # type: ignore[attr-defined]
    call.provider_name = PROVIDER_NAME  # type: ignore[attr-defined]
    return call


def _extract_tool_input(payload: dict) -> tuple[dict, str]:
    """Pull the tool_use block that carries the structured response.

    Anthropic returns `content` as a list of blocks. With our forced
    `tool_choice`, exactly one block should have `type=tool_use` and
    `input` as the parsed JSON. `raw_text` mirrors `input` serialized so
    `raw_model_output` logs stay meaningful (LOGGING.md §6).
    """
    content = payload.get("content") or []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == _TOOL_NAME:
            parsed = block.get("input") or {}
            return parsed, json.dumps(parsed, ensure_ascii=False)
    # Fallback: concatenate any text blocks, attempt json parse.
    text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    raw_text = "".join(text_parts)
    try:
        return json.loads(raw_text or "{}"), raw_text
    except json.JSONDecodeError:
        return {}, raw_text


def _usage_dict(usage_obj) -> dict:
    if not isinstance(usage_obj, dict):
        return {}
    out: dict = {}
    # Anthropic names differ from OpenAI; normalize to OpenAI-ish keys so
    # matrix aggregator doesn't branch on provider.
    mapping = {
        "input_tokens": "prompt_tokens",
        "output_tokens": "completion_tokens",
    }
    for src, dst in mapping.items():
        if src in usage_obj:
            out[dst] = usage_obj[src]
    if "prompt_tokens" in out and "completion_tokens" in out:
        out["total_tokens"] = out["prompt_tokens"] + out["completion_tokens"]
    return out


def _urllib_post(url: str, headers: dict, body: bytes, timeout: float | None) -> dict:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed hosts
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8")
        except Exception:
            detail = str(exc)
        raise RuntimeError(f"anthropic http {exc.code}: {detail}") from exc
