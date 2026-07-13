"""Agent registry — the single source of truth for available agents.

To add a new agent:
  1. Create ``app/services/agents/your_agent.py`` subclassing ``BaseAgent``.
  2. Import it here and add it to ``_REGISTRY``.
"""
from __future__ import annotations
from typing import Type

from app.services.agents.base import BaseAgent
from app.services.agents.eda import EDAAgent
from app.services.agents.market_research import MarketResearchAgent

_REGISTRY: dict[str, Type[BaseAgent]] = {
    "eda": EDAAgent,
    "market_research": MarketResearchAgent,
}


def get_agent(name: str) -> BaseAgent:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise KeyError(
            f"Unknown agent: {name!r}. Available: {sorted(_REGISTRY)}"
        )
    return cls()


def list_agents() -> list[dict]:
    return [
        {"name": cls.name, "description": cls.description, "mode": cls.mode}
        for cls in _REGISTRY.values()
    ]
