"""OpenAI realization of LLMJsonCall (PHASE2_PLAN.md §3.0).

The returned closure carries `model_name` / `provider_name` as function
attributes so tools that need per-model prompt composition can introspect
without the call-site signature changing. Decoding stays pinned at
`temperature=0` (EVAL_EXECUTION_SPEC §6, PHASE2_PLAN §1.1).
"""
from __future__ import annotations

import json
import time

from openai import OpenAI

from gh_search.llm import LLMJsonCall, LLMResponse

PROVIDER_NAME = "openai"


def make_openai_llm(
    api_key: str,
    model: str = "gpt-4.1-mini",
    *,
    temperature: float = 0,
    timeout_seconds: float | None = None,
) -> LLMJsonCall:
    client = OpenAI(api_key=api_key)

    def call(system_prompt: str, user_message: str, response_schema: dict) -> LLMResponse:
        started = time.perf_counter()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "gh_search_response",
                    "schema": response_schema,
                    "strict": True,
                },
            },
            temperature=temperature,
            **({"timeout": timeout_seconds} if timeout_seconds is not None else {}),
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        raw_text = response.choices[0].message.content or "{}"
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        usage_obj = getattr(response, "usage", None)
        usage = _usage_dict(usage_obj)
        response_id = getattr(response, "id", None)

        return LLMResponse(
            raw_text=raw_text,
            parsed=json.loads(raw_text),
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


def _usage_dict(usage_obj) -> dict:
    if usage_obj is None:
        return {}
    out: dict = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        val = getattr(usage_obj, key, None)
        if val is not None:
            out[key] = val
    return out
