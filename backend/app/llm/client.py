"""Anthropic client wrapper with tiered model selection, strict JSON output and cost accounting.

Every call returns an :class:`LLMResult` carrying token counts and a USD cost so the
platform can enforce per-campaign budgets. When no API key is configured the wrapper
reports itself unavailable and callers fall back to their deterministic paths — the
platform never invents data just because the LLM is missing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

try:  # the SDK is a hard requirement, but importing must not break tooling
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore[assignment]


# USD per million tokens. Kept in sync with the admin `ai_models` table, which is
# seeded from this map and is authoritative once an operator edits it.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

CHEAP = "cheap"
SMART = "smart"


@dataclass(slots=True)
class LLMResult:
    text: str = ""
    data: dict[str, Any] | None = None
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    ok: bool = False
    error: str | None = None
    stop_reason: str | None = None


@dataclass(slots=True)
class LLMUsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    by_model: dict[str, float] = field(default_factory=dict)

    def add(self, result: LLMResult) -> None:
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        self.cost_usd += result.cost_usd
        self.calls += 1
        self.by_model[result.model] = self.by_model.get(result.model, 0.0) + result.cost_usd


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_rate, out_rate = MODEL_PRICING.get(model, (0.0, 0.0))
    return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate


class LLMClient:
    """Thin, cost-aware facade over the Anthropic Messages API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or settings.ANTHROPIC_API_KEY
        self._client = None
        if self.available and anthropic is not None:
            self._client = anthropic.Anthropic(api_key=self._api_key)

    @property
    def available(self) -> bool:
        return bool(settings.LLM_ENABLED and self._api_key and anthropic is not None)

    def model_for(self, tier: str) -> str:
        return settings.LLM_SMART_MODEL if tier == SMART else settings.LLM_CHEAP_MODEL

    def complete(
        self,
        *,
        system: str,
        prompt: str,
        tier: str = CHEAP,
        max_tokens: int | None = None,
    ) -> LLMResult:
        """Plain text completion."""
        if not self.available:
            return LLMResult(ok=False, error="llm_unavailable")

        model = self.model_for(tier)
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens or settings.LLM_MAX_OUTPUT_TOKENS,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            }
            kwargs.update(self._reasoning_kwargs(model))
            response = self._client.messages.create(**kwargs)  # type: ignore[union-attr]
        except Exception as exc:  # network, auth, rate limits - all non-fatal here
            logger.warning("llm_call_failed", model=model, error=str(exc))
            return LLMResult(ok=False, model=model, error=str(exc))

        text = "".join(b.text for b in response.content if b.type == "text")
        return self._to_result(response, model, text=text)

    def structured(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        tool_name: str = "record_result",
        tool_description: str = "Record the structured result.",
        tier: str = CHEAP,
        max_tokens: int | None = None,
    ) -> LLMResult:
        """Force the model to answer through a strict JSON tool schema."""
        if not self.available:
            return LLMResult(ok=False, error="llm_unavailable")

        model = self.model_for(tier)
        tool = {
            "name": tool_name,
            "description": tool_description,
            "input_schema": schema,
            "strict": True,
        }
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens or settings.LLM_MAX_OUTPUT_TOKENS,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
                "tools": [tool],
                "tool_choice": {"type": "tool", "name": tool_name},
            }
            kwargs.update(self._reasoning_kwargs(model, forced_tool=True))
            response = self._client.messages.create(**kwargs)  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("llm_structured_failed", model=model, error=str(exc))
            return LLMResult(ok=False, model=model, error=str(exc))

        data: dict[str, Any] | None = None
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                # Tool inputs may carry provider-specific JSON escaping; never string-match.
                data = json.loads(json.dumps(block.input))
                break

        result = self._to_result(response, model, text="")
        result.data = data
        result.ok = result.ok and data is not None
        if data is None and result.error is None:
            result.error = "no_tool_output"
        return result

    @staticmethod
    def _reasoning_kwargs(model: str, forced_tool: bool = False) -> dict[str, Any]:
        """Thinking configuration differs per model generation."""
        if model.startswith("claude-opus-5") or model.startswith("claude-sonnet-5"):
            if forced_tool:
                # A forced tool choice already guarantees a structured answer;
                # medium effort keeps enrichment affordable.
                return {"thinking": {"type": "disabled"}, "output_config": {"effort": "medium"}}
            return {"thinking": {"type": "adaptive"}, "output_config": {"effort": "medium"}}
        # Haiku 4.5 and older generations take no thinking configuration here.
        return {}

    @staticmethod
    def _to_result(response: Any, model: str, text: str) -> LLMResult:
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        stop_reason = getattr(response, "stop_reason", None)
        return LLMResult(
            text=text,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=estimate_cost(model, input_tokens, output_tokens),
            ok=stop_reason != "refusal",
            stop_reason=stop_reason,
            error="refusal" if stop_reason == "refusal" else None,
        )


_default_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
