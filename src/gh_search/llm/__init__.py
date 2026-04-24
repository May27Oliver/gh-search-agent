"""Infrastructure: LLM adapters (PHASE2_PLAN.md §3.0).

`LLMJsonCall` is the single callable signature every LLM-backed tool depends
on. It returns an `LLMResponse` carrying both the raw provider string and the
parsed JSON payload. Phase 2 enriches the response with provider / model /
usage / latency metadata so matrix aggregators and logs can report provenance
without every tool knowing which provider answered.

The call signature `(system_prompt, user_message, response_schema) -> LLMResponse`
stays unchanged; every Phase 2 provider knob (temperature, timeout, appendix,
endpoint) is bound at factory time by `make_llm(...)` in `llm/factory.py`.
"""
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class LLMResponse:
    raw_text: str
    parsed: dict
    provider_name: str | None = None
    model_name: str | None = None
    finish_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    latency_ms: int | None = None
    provider_response_id: str | None = None
    transport_error: str | None = None


LLMJsonCall = Callable[[str, str, dict], LLMResponse]

__all__ = ["LLMJsonCall", "LLMResponse"]
