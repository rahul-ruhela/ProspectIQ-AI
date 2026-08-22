"""Multi-provider LLM facade with tiered model selection, strict JSON output and cost accounting.

Every call returns an :class:`LLMResult` carrying token counts and a USD cost so the
platform can enforce per-campaign budgets. The vendor is inferred from the configured
model id, so switching a tier between Claude and GPT is a configuration change only.
When no key is configured for the selected model's vendor the wrapper reports itself
unavailable and callers fall back to their deterministic paths - the platform never
invents data just because the LLM is missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.quota import get_ledger
from app.llm.providers import (
    ANTHROPIC,
    GOOGLE,
    OPENAI,
    PROVIDER_CLASSES,
    LLMQuotaExhausted,
    Provider,
    provider_for,
)

logger = get_logger(__name__)


# USD per million tokens. Kept in sync with the admin `ai_models` table, which is
# seeded from this map and is authoritative once an operator edits it.
# The Gemini rows are the paid-tier list prices: they apply only if billing is
# enabled on the Google project AND LLM_FREE_TIER_ONLY is turned off.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
}

# Gemini's flash and flash-lite tiers are the ones Google serves on the no-card AI
# Studio free tier. Matching the family rather than pinning exact ids is deliberate:
# Google retires ids for new projects fast (2.5 -> 3.x within a year), and an
# explicit list would silently block every current model as it rotated.
_FREE_TIER_PREFIX = "gemini-"
_FREE_TIER_MARKERS = ("flash",)

# Never free at any generation, so they stay blocked under the guard.
_NEVER_FREE_MARKERS = ("pro", "ultra", "computer-use")


def is_free_tier(model: str) -> bool:
    """True when ``model`` can be served without a billing account.

    Only Gemini qualifies: Anthropic and OpenAI bill from the first token, so a
    key for either is unusable while LLM_FREE_TIER_ONLY is set.
    """
    name = (model or "").split("/")[-1].lower()
    if not name.startswith(_FREE_TIER_PREFIX):
        return False
    if any(marker in name for marker in _NEVER_FREE_MARKERS):
        return False
    return any(marker in name for marker in _FREE_TIER_MARKERS)


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
    # Under the free-tier guard nothing is billable, so the honest cost is zero -
    # reporting list prices there would burn campaign budgets that were never spent.
    if settings.LLM_FREE_TIER_ONLY and is_free_tier(model):
        return 0.0
    rates = MODEL_PRICING.get(model)
    if rates is None:
        # Silently pricing an unlisted model at zero would let a paid run report a
        # $0 spend and slip past every campaign budget check.
        logger.warning("llm_pricing_unknown", model=model)
        return 0.0
    in_rate, out_rate = rates
    return (input_tokens / 1_000_000) * in_rate + (output_tokens / 1_000_000) * out_rate


class LLMClient:
    """Thin, cost-aware facade over whichever vendors are configured."""

    def __init__(self, api_keys: dict[str, str] | None = None) -> None:
        self._api_keys = api_keys or {
            ANTHROPIC: settings.ANTHROPIC_API_KEY,
            OPENAI: settings.OPENAI_API_KEY,
            GOOGLE: settings.GEMINI_API_KEY,
        }
        self._providers: dict[str, Provider] = {}
        for slug, cls in PROVIDER_CLASSES.items():
            provider = cls(self._api_keys.get(slug, ""))
            if provider.available:
                self._providers[slug] = provider

    @property
    def available(self) -> bool:
        """True when both tiers still have at least one model able to answer today."""
        if not settings.LLM_ENABLED:
            return False
        return all(bool(self.usable_chain(t)) for t in (CHEAP, SMART))

    def available_for(self, model: str) -> bool:
        """True when the vendor serving ``model`` has a usable client.

        The free-tier guard is enforced here rather than at the call site so every
        path into the facade - agents, report synthesis, health checks - sees the
        same answer.
        """
        if not settings.LLM_ENABLED:
            return False
        if settings.LLM_FREE_TIER_ONLY and not is_free_tier(model):
            return False
        return provider_for(model) in self._providers

    def unavailable_reason(self, model: str) -> str | None:
        """Why ``model`` cannot be called, or None when it can."""
        if not settings.LLM_ENABLED:
            return "LLM_ENABLED is false."
        if settings.LLM_FREE_TIER_ONLY and not is_free_tier(model):
            return (
                f"{model} has no free tier and LLM_FREE_TIER_ONLY is on. "
                "Use a gemini-* free-tier model, or set LLM_FREE_TIER_ONLY=false "
                "to allow paid calls."
            )
        if provider_for(model) not in self._providers:
            return f"No API key configured for the {provider_for(model)} provider."
        return None

    @property
    def configured_providers(self) -> list[str]:
        return sorted(self._providers)

    def model_for(self, tier: str) -> str:
        """The preferred model for a tier - the head of its chain."""
        chain = self.chain_for(tier)
        return chain[0] if chain else ""

    def chain_for(self, tier: str) -> list[str]:
        """Every model that may serve ``tier``, best first."""
        chain = settings.smart_model_chain if tier == SMART else settings.cheap_model_chain
        # A model the guard forbids must never appear, or failover would walk
        # straight onto a billed vendor.
        return [m for m in chain if not settings.LLM_FREE_TIER_ONLY or is_free_tier(m)]

    def usable_chain(self, tier: str) -> list[str]:
        """Chain members that are configured and have not run out today."""
        ledger = get_ledger()
        return [
            m
            for m in self.chain_for(tier)
            if provider_for(m) in self._providers and not ledger.is_exhausted(m)
        ]

    def quota_snapshot(self) -> dict[str, Any]:
        """Per-model daily usage, for the status endpoint and the UI."""
        ledger = get_ledger()
        models: list[str] = []
        for tier in (CHEAP, SMART):
            for model in self.chain_for(tier):
                if model not in models:
                    models.append(model)
        return {"models": ledger.snapshot(models)}

    @staticmethod
    def _trim(prompt: str) -> str:
        """Cap prompt size. The tail of crawled text is boilerplate, so it goes first."""
        limit = settings.LLM_MAX_PROMPT_CHARS
        if limit <= 0 or len(prompt) <= limit:
            return prompt
        logger.info("llm_prompt_truncated", original_chars=len(prompt), limit=limit)
        return prompt[:limit] + "\n\n[truncated to fit the token budget]"

    def complete(
        self,
        *,
        system: str,
        prompt: str,
        tier: str = CHEAP,
        max_tokens: int | None = None,
    ) -> LLMResult:
        """Plain text completion, failing over across the tier's model chain."""
        prompt = self._trim(prompt)
        return self._attempt(
            tier,
            lambda provider, model: provider.complete(
                model=model,
                system=system,
                prompt=prompt,
                max_tokens=max_tokens or settings.LLM_MAX_OUTPUT_TOKENS,
            ),
        )

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
        prompt = self._trim(prompt)
        result = self._attempt(
            tier,
            lambda provider, model: provider.structured(
                model=model,
                system=system,
                prompt=prompt,
                schema=schema,
                tool_name=tool_name,
                tool_description=tool_description,
                max_tokens=max_tokens or settings.LLM_MAX_OUTPUT_TOKENS,
            ),
        )
        if result.ok and result.data is None:
            result.ok = False
            result.error = result.error or "no_tool_output"
        return result

    def _attempt(self, tier: str, call: Any) -> LLMResult:
        """Run ``call`` against each model in the tier chain until one answers.

        Only quota exhaustion advances to the next model: it is the one failure that
        another model can genuinely fix. A transport or auth error would recur
        identically down the chain, so it is returned immediately rather than
        multiplied by the chain length.
        """
        ledger = get_ledger()
        chain = self.chain_for(tier)
        if not chain:
            return LLMResult(ok=False, error="llm_unavailable")

        last: LLMResult | None = None
        for model in chain:
            provider = self._providers.get(provider_for(model))
            if provider is None:
                continue
            if ledger.is_exhausted(model):
                continue

            try:
                response = call(provider, model)
            except LLMQuotaExhausted as exc:
                # Remembered for the rest of the UTC day so the next of the job's
                # many calls skips this model instead of re-probing it.
                ledger.mark_exhausted(model, str(exc))
                last = LLMResult(ok=False, model=model, error="quota_exhausted")
                continue
            except Exception as exc:
                logger.warning(
                    "llm_call_failed", provider=provider.slug, model=model, error=str(exc)
                )
                return LLMResult(ok=False, model=model, error=str(exc))

            ledger.record_call(model)
            return self._to_result(response, model)

        if last is not None:
            logger.warning("llm_chain_exhausted", tier=tier, chain=chain)
            return last
        return LLMResult(ok=False, model=chain[0], error="llm_unavailable")

    @staticmethod
    def _to_result(response: Any, model: str) -> LLMResult:
        refused = response.stop_reason == "refusal"
        return LLMResult(
            text=response.text,
            data=response.data,
            model=model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cost_usd=estimate_cost(model, response.input_tokens, response.output_tokens),
            ok=not refused,
            stop_reason=response.stop_reason,
            error="refusal" if refused else None,
        )


_default_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
