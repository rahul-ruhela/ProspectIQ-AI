"""Per-vendor adapters behind the :class:`~app.llm.client.LLMClient` facade.

Each provider turns the platform's two primitives - a text completion and a
schema-forced structured call - into vendor-specific request shapes, and
normalises the response back into a plain ``(text, data, usage)`` triple. The
facade stays vendor-agnostic so agents, report synthesis and cost accounting
never learn which vendor answered.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

try:  # SDKs are optional at import time so tooling works without them installed
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None  # type: ignore[assignment]

try:
    import openai
except ImportError:  # pragma: no cover
    openai = None  # type: ignore[assignment]


ANTHROPIC = "anthropic"
OPENAI = "openai"
GOOGLE = "google"

# Model-id prefixes that identify a vendor. Checked longest-first so a more
# specific prefix always wins over a shorter one.
_PREFIXES: tuple[tuple[str, str], ...] = (
    ("claude-", ANTHROPIC),
    ("gpt-", OPENAI),
    ("chatgpt-", OPENAI),
    ("o1", OPENAI),
    ("o3", OPENAI),
    ("o4", OPENAI),
    ("gemini-", GOOGLE),
    ("models/gemini-", GOOGLE),
)


class LLMQuotaExhausted(RuntimeError):
    """The vendor refused the call because a quota - typically a free tier - ran out.

    Raised instead of a generic error so the facade can report it distinctly and
    callers fall back to their deterministic paths. It is never a signal to retry
    the same work on a billed vendor.
    """


def provider_for(model: str) -> str:
    """Infer the vendor that serves ``model``. Defaults to Anthropic."""
    name = (model or "").lower()
    for prefix, slug in sorted(_PREFIXES, key=lambda p: -len(p[0])):
        if name.startswith(prefix):
            return slug
    return ANTHROPIC


@dataclass(slots=True)
class ProviderResponse:
    """Vendor-neutral shape returned by every provider."""

    text: str = ""
    data: dict[str, Any] | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str | None = None


class Provider:
    """Contract every vendor adapter implements."""

    slug: str = ""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client: Any = None

    @property
    def available(self) -> bool:
        raise NotImplementedError

    def complete(
        self, *, model: str, system: str, prompt: str, max_tokens: int
    ) -> ProviderResponse:
        raise NotImplementedError

    def structured(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        tool_name: str,
        tool_description: str,
        max_tokens: int,
    ) -> ProviderResponse:
        raise NotImplementedError


class AnthropicProvider(Provider):
    slug = ANTHROPIC

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key)
        if self.available:
            self._client = anthropic.Anthropic(api_key=api_key)

    @property
    def available(self) -> bool:
        return bool(self._api_key and anthropic is not None)

    def complete(
        self, *, model: str, system: str, prompt: str, max_tokens: int
    ) -> ProviderResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        kwargs.update(self._reasoning_kwargs(model))
        response = self._client.messages.create(**kwargs)
        text = "".join(b.text for b in response.content if b.type == "text")
        return self._to_response(response, text=text)

    def structured(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        tool_name: str,
        tool_description: str,
        max_tokens: int,
    ) -> ProviderResponse:
        tool = {
            "name": tool_name,
            "description": tool_description,
            "input_schema": schema,
            "strict": True,
        }
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
            "tools": [tool],
            "tool_choice": {"type": "tool", "name": tool_name},
        }
        kwargs.update(self._reasoning_kwargs(model, forced_tool=True))
        response = self._client.messages.create(**kwargs)

        data: dict[str, Any] | None = None
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                # Tool inputs may carry provider-specific JSON escaping; never string-match.
                data = json.loads(json.dumps(block.input))
                break
        return self._to_response(response, text="", data=data)

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
    def _to_response(
        response: Any, text: str, data: dict[str, Any] | None = None
    ) -> ProviderResponse:
        usage = getattr(response, "usage", None)
        return ProviderResponse(
            text=text,
            data=data,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            stop_reason=getattr(response, "stop_reason", None),
        )


class OpenAIProvider(Provider):
    slug = OPENAI

    def __init__(self, api_key: str) -> None:
        super().__init__(api_key)
        if self.available:
            self._client = openai.OpenAI(api_key=api_key)

    @property
    def available(self) -> bool:
        return bool(self._api_key and openai is not None)

    def complete(
        self, *, model: str, system: str, prompt: str, max_tokens: int
    ) -> ProviderResponse:
        response = self._client.chat.completions.create(
            model=model,
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        choice = response.choices[0]
        return self._to_response(response, text=choice.message.content or "")

    def structured(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        tool_name: str,
        tool_description: str,
        max_tokens: int,
    ) -> ProviderResponse:
        # Deliberately not OpenAI "strict" mode: the platform's schemas allow
        # optional properties, which strict mode rejects outright.
        tool = {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_description,
                "parameters": schema,
            },
        }
        response = self._client.chat.completions.create(
            model=model,
            max_completion_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": tool_name}},
        )
        choice = response.choices[0]

        data: dict[str, Any] | None = None
        for call in getattr(choice.message, "tool_calls", None) or []:
            if call.function.name == tool_name:
                try:
                    parsed = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError as exc:
                    logger.warning("openai_tool_json_invalid", model=model, error=str(exc))
                    break
                data = parsed if isinstance(parsed, dict) else None
                break
        return self._to_response(response, text="", data=data)

    @staticmethod
    def _to_response(
        response: Any, text: str, data: dict[str, Any] | None = None
    ) -> ProviderResponse:
        usage = getattr(response, "usage", None)
        finish = getattr(response.choices[0], "finish_reason", None)
        return ProviderResponse(
            text=text,
            data=data,
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            # Normalise onto the vocabulary the rest of the platform already uses.
            stop_reason="refusal" if finish == "content_filter" else finish,
        )


# JSON Schema keywords the Gemini function-declaration parser rejects outright.
# The platform's schemas are written for Anthropic/OpenAI, so they are filtered
# rather than rewritten: dropping a keyword only widens what the model may return,
# and every caller validates the result anyway.
_SCHEMA_UNSUPPORTED = frozenset({
    "$schema", "$id", "$ref", "$defs", "definitions", "additionalProperties",
    "strict", "default", "examples", "title", "const", "patternProperties",
    "unevaluatedProperties", "if", "then", "else", "not", "allOf", "oneOf",
})


def _gemini_schema(schema: Any) -> Any:
    """Recursively strip keywords Gemini's schema parser will not accept."""
    if isinstance(schema, dict):
        return {
            key: _gemini_schema(value)
            for key, value in schema.items()
            if key not in _SCHEMA_UNSUPPORTED
        }
    if isinstance(schema, list):
        return [_gemini_schema(item) for item in schema]
    return schema


class GeminiProvider(Provider):
    """Google Gemini over the Generative Language REST API.

    Deliberately spoken to over plain HTTP rather than the ``google-genai`` SDK:
    httpx is already a hard dependency, the endpoint is stable, and one fewer
    optional import means the free-tier path works on a bare install.

    A 429 becomes :class:`LLMQuotaExhausted` so an exhausted free tier is
    distinguishable from a transport failure and never silently escalates cost.
    """

    slug = GOOGLE

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    # LLM turns outlast the platform's normal HTTP budget, so this timeout is its own.
    TIMEOUT_SECONDS = 120.0

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def complete(
        self, *, model: str, system: str, prompt: str, max_tokens: int
    ) -> ProviderResponse:
        payload = self._post(model, self._body(model, system, prompt, max_tokens))
        return self._to_response(payload, tool_name=None)

    def structured(
        self,
        *,
        model: str,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        tool_name: str,
        tool_description: str,
        max_tokens: int,
    ) -> ProviderResponse:
        body = self._body(model, system, prompt, max_tokens)
        body["tools"] = [
            {
                "functionDeclarations": [
                    {
                        "name": tool_name,
                        "description": tool_description,
                        "parameters": _gemini_schema(schema),
                    }
                ]
            }
        ]
        # mode ANY with a single allowed name is Gemini's equivalent of a forced tool.
        body["toolConfig"] = {
            "functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": [tool_name]}
        }
        payload = self._post(model, body)
        return self._to_response(payload, tool_name=tool_name)

    @staticmethod
    def _body(model: str, system: str, prompt: str, max_tokens: int) -> dict[str, Any]:
        generation: dict[str, Any] = {"maxOutputTokens": max_tokens, "temperature": 0.0}
        # Thinking is billed against the same free-tier token budget and adds nothing
        # to extraction work, so it is switched off on the tiers that allow a zero
        # budget. Pro models reject one, so they keep their default.
        if "flash" in model:
            generation["thinkingConfig"] = {"thinkingBudget": 0}
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation,
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        return body

    def _post(self, model: str, body: dict[str, Any]) -> dict[str, Any]:
        name = model.split("/")[-1]
        with httpx.Client(timeout=self.TIMEOUT_SECONDS) as client:
            response = client.post(
                f"{self.BASE_URL}/{name}:generateContent",
                json=body,
                # Every AI Studio key format - classic "AIza..." and the newer
                # "AQ." keys alike - authenticates through this header. Sending one
                # as a bearer token instead yields API_KEY_SERVICE_BLOCKED.
                headers={
                    "x-goog-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
            )
        if response.status_code == 429:
            # Two very different causes share this status: a rate/quota ceiling that
            # resets on its own, and a depleted prepaid balance that never will.
            depleted = "prepayment credits are depleted" in response.text
            raise LLMQuotaExhausted(
                f"gemini {'prepaid balance is empty' if depleted else 'quota exhausted'} "
                f"for {name}: {response.text[:200]}"
            )
        if response.status_code in (401, 403):
            # Overwhelmingly a setup problem rather than a transient one, so the
            # message names the fix instead of only echoing Google's wording.
            raise RuntimeError(
                f"gemini_auth_{response.status_code}: the key was rejected. Check that the "
                "Generative Language API is enabled for the key's Google Cloud project and "
                "that the key carries no API restriction excluding it. "
                f"Response: {response.text[:250]}"
            )
        if response.status_code == 404 and "no longer available" in response.text:
            # Google retires model ids for new projects while still listing them,
            # so this reads as a 404 rather than a deprecation warning.
            raise RuntimeError(
                f"gemini_model_retired: {name} is no longer served to new projects. "
                "Pick a current model id - GET /v1beta/models lists what this key can "
                f"actually call. Response: {response.text[:200]}"
            )
        if response.status_code >= 400:
            raise RuntimeError(f"gemini_http_{response.status_code}: {response.text[:300]}")
        return response.json()

    @staticmethod
    def _to_response(payload: dict[str, Any], tool_name: str | None) -> ProviderResponse:
        usage = payload.get("usageMetadata") or {}
        # Thinking tokens bill as output; count them so budgets stay honest.
        output = int(usage.get("candidatesTokenCount", 0) or 0) + int(
            usage.get("thoughtsTokenCount", 0) or 0
        )
        prompt_tokens = int(usage.get("promptTokenCount", 0) or 0)

        blocked = (payload.get("promptFeedback") or {}).get("blockReason")
        candidates = payload.get("candidates") or []
        if blocked or not candidates:
            return ProviderResponse(
                input_tokens=prompt_tokens,
                output_tokens=output,
                stop_reason="refusal" if blocked else "empty",
            )

        candidate = candidates[0]
        finish = candidate.get("finishReason")
        text_parts: list[str] = []
        data: dict[str, Any] | None = None
        for part in (candidate.get("content") or {}).get("parts") or []:
            if "text" in part:
                text_parts.append(part["text"])
            call = part.get("functionCall")
            if call and (tool_name is None or call.get("name") == tool_name):
                args = call.get("args")
                data = args if isinstance(args, dict) else None

        refused = finish in {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}
        return ProviderResponse(
            text="".join(text_parts),
            data=data,
            input_tokens=prompt_tokens,
            output_tokens=output,
            # Normalise onto the vocabulary the rest of the platform already uses.
            stop_reason="refusal" if refused else finish,
        )


PROVIDER_CLASSES: dict[str, type[Provider]] = {
    ANTHROPIC: AnthropicProvider,
    OPENAI: OpenAIProvider,
    GOOGLE: GeminiProvider,
}
