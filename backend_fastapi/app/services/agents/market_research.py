"""Market Research Agent."""
from __future__ import annotations
from typing import AsyncIterator

from app.services.agents.base import AgentContext, BaseAgent


class MarketResearchAgent(BaseAgent):
    name = "market_research"
    description = "Market Research — TAM/SAM/SOM, competitive intelligence, 12-scenario analysis"
    mode = "market_research"

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        async for chunk in super().stream(ctx):
            yield chunk
