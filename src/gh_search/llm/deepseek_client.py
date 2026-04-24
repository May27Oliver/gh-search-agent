"""DeepSeek realization of LLMJsonCall (PHASE2_PLAN.md §3.0).

DeepSeek's official API is OpenAI-compatible. We therefore reuse the
official `openai` SDK with `base_url` pointed at the configured endpoint.
The canonical project model name is `deepseek-r1`, while the official API
model id is currently `deepseek-reasoner`; the adapter translates at the
wire boundary so logs / matrix rows stay canonical.
"""
from __future__ import annotations

import json
import time

from openai import BadRequestError, OpenAI

from gh_search.llm import LLMJsonCall, LLMResponse

PROVIDER_NAME = "deepseek"
DEFAULT_ENDPOINT_URL = "https://api.deepseek.com"

_API_MODEL_ID: dict[str, str] = {
    "deepseek-r1": "deepseek-reasoner",
}


def _to_api_model_id(canonical: str) -> str:
    return _API_MODEL_ID.get(canonical, canonical)


def make_deepseek_llm(
    api_key: str,
    endpoint_url: str | None = None,
    model: str = "deepseek-r1",
    *,
    temperature: float = 0,
    timeout_seconds: float | None = 60.0,
    json_schema_support: bool = True,
) -> LLMJsonCall:
    client = OpenAI(
        api_key=api_key,
        base_url=(endpoint_url or DEFAULT_ENDPOINT_URL),
    )
    api_model_id = _to_api_model_id(model)

    def call(system_prompt: str, user_message: str, response_schema: dict) -> LLMResponse:
        started = time.perf_counter()
        response = _create_with_fallback(
            client=client,
            system_prompt=system_prompt,
            user_message=user_message,
            response_schema=response_schema,
            model=api_model_id,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            json_schema_support=json_schema_support,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)

        raw_text = response.choices[0].message.content or "{}"
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            parsed = {}

        finish_reason = getattr(response.choices[0], "finish_reason", None)
        usage = _usage_dict(getattr(response, "usage", None))
        response_id = getattr(response, "id", None)

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


def _inline_schema_if_needed(system_prompt: str, schema: dict, json_schema_support: bool) -> str:
    if json_schema_support:
        return system_prompt
    return (
        f"{system_prompt}\n\n"
        "You MUST respond with a single JSON object matching this JSON Schema. "
        "Do not add prose, markdown fences, or commentary.\n"
        f"Schema:\n{json.dumps(schema, ensure_ascii=False)}"
    )


def _pick_response_format(schema: dict, json_schema_support: bool) -> dict:
    if json_schema_support:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "gh_search_response",
                "schema": schema,
                "strict": True,
            },
        }
    return {"type": "json_object"}


def _build_request_kwargs(
    *,
    system_prompt: str,
    user_message: str,
    response_schema: dict,
    model: str,
    temperature: float,
    timeout_seconds: float | None,
    json_schema_support: bool,
) -> dict:
    kwargs: dict = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": _inline_schema_if_needed(system_prompt, response_schema, json_schema_support),
            },
            {"role": "user", "content": user_message},
        ],
        "response_format": _pick_response_format(response_schema, json_schema_support),
        "temperature": temperature,
    }
    if timeout_seconds is not None:
        kwargs["timeout"] = timeout_seconds
    return kwargs


def _create_with_fallback(
    *,
    client,
    system_prompt: str,
    user_message: str,
    response_schema: dict,
    model: str,
    temperature: float,
    timeout_seconds: float | None,
    json_schema_support: bool,
):
    try:
        return client.chat.completions.create(
            **_build_request_kwargs(
                system_prompt=system_prompt,
                user_message=user_message,
                response_schema=response_schema,
                model=model,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
                json_schema_support=json_schema_support,
            )
        )
    except BadRequestError as exc:
        if not json_schema_support or not _should_fallback_to_json_object(exc):
            raise
        return client.chat.completions.create(
            **_build_request_kwargs(
                system_prompt=system_prompt,
                user_message=user_message,
                response_schema=response_schema,
                model=model,
                temperature=temperature,
                timeout_seconds=timeout_seconds,
                json_schema_support=False,
            )
        )


def _should_fallback_to_json_object(exc: BadRequestError) -> bool:
    text = str(exc).lower()
    return (
        "response_format" in text
        and "unavailable" in text
        and "json_schema" in text
    ) or (
        "response_format" in text
        and "unavailable now" in text
    )


def _usage_dict(usage_obj) -> dict:
    if usage_obj is None:
        return {}
    out: dict = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        val = getattr(usage_obj, key, None)
        if val is not None:
            out[key] = val
    return out
