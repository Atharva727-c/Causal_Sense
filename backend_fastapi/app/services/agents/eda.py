"""EDA Agent — injects file schema/preview context before calling Claude."""
from __future__ import annotations
from typing import AsyncIterator

from app.services.agents.base import AgentContext, BaseAgent
from app.services.file_processor import build_file_context


class EDAAgent(BaseAgent):
    name = "eda"
    description = "Exploratory Data Analysis — statistical deep-dive on uploaded datasets"
    mode = "eda"

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        ctx.query = self._inject_file_context(ctx)
        async for chunk in super().stream(ctx):
            yield chunk

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _inject_file_context(ctx: AgentContext) -> str:
        parts: list[str] = []
        for f in ctx.files:
            if f.get("schema") or f.get("preview"):
                parts.append(
                    build_file_context(
                        filename=f.get("name", "dataset"),
                        schema=f.get("schema", []),
                        preview=f.get("preview", []),
                        stats=f.get("stats", {}),
                        row_count=f.get("row_count"),
                    )
                )
        if parts:
            return "\n\n".join(parts) + "\n\n---\n\n" + ctx.query
        return ctx.query
