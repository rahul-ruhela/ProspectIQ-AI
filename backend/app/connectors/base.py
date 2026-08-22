"""Discovery connector contract.

A connector turns a search intent into raw, attributed results. Connectors never
invent results: when a provider is unconfigured or fails, the connector reports
``available = False`` with a reason and yields nothing.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""
    source: str = ""
    source_type: str = "search_result"
    rank: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ConnectorStatus:
    slug: str
    name: str
    available: bool
    reason: str


class SearchConnector(ABC):
    slug: str = "base"
    name: str = "Base connector"
    kind: str = "search"
    requires_api_key: bool = False
    cost_per_call_usd: float = 0.0

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether this connector has everything it needs to run."""

    @property
    def unavailable_reason(self) -> str:
        return "" if self.available else "Not configured."

    def status(self) -> ConnectorStatus:
        return ConnectorStatus(
            slug=self.slug,
            name=self.name,
            available=self.available,
            reason="Ready." if self.available else self.unavailable_reason,
        )

    @abstractmethod
    async def search(self, query: str, *, limit: int = 20, country: str | None = None) -> list[SearchResult]:
        """Run one query and return attributed results."""
