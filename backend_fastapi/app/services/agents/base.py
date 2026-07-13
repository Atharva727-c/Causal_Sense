"""Agent base classes.

Extension guide for teammates
==============================
1. Subclass ``BaseAgent`` and set ``name``, ``description``, ``mode``.
2. Optionally add ``Tool`` subclasses and list them in ``tools``.
3. Register the new agent in ``registry.py``.

Tool stub
---------
Tools receive a typed ``AgentContext`` and return a plain string result.
The result is fed back to the LLM as a ``tool_result`` block.

Example::

    class MyTool(Tool):
        name = "search_web"
        description = "Search the internet for recent information."
        input_schema = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

        async def execute(self, inputs: dict, ctx: AgentContext) -> str:
            # ── YOUR IMPLEMENTATION HERE ──
            return f"[stub] web search for: {inputs['query']}"

A2A integration
---------------
For agent-to-agent calls, teammates can call ``other_agent.run_once(ctx)``
inside a tool's ``execute`` method or add a dedicated router endpoint that
chains agents together.
"""
from __future__ import annotations
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from anthropic.types import MessageParam

from app.core.events import (
    sse_agent_step, sse_delta, sse_done, sse_error,
    sse_tool_result, sse_tool_use,
)
from app.services.llm import LLMService, get_llm, get_system_prompt

logger = logging.getLogger(__name__)


# ── Tool ABC ──────────────────────────────────────────────────────────────────

class Tool(ABC):
    """Abstract base for every agent-callable tool."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]: ...

    @abstractmethod
    async def execute(self, inputs: dict[str, Any], ctx: "AgentContext") -> str:
        """Execute the tool and return a plain-text result."""
        ...

    def to_anthropic_format(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


# ── Context ───────────────────────────────────────────────────────────────────

@dataclass
class AgentContext:
    """Shared state passed through the agent pipeline."""

    query: str
    chat_history: list[MessageParam] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    # Populated at runtime — teammates may read/write this freely.
    metadata: dict[str, Any] = field(default_factory=dict)


# ── BaseAgent ─────────────────────────────────────────────────────────────────

class BaseAgent(ABC):
    """
    Abstract base for all CausalSense agents.

    ``stream()`` yields SSE-formatted strings compatible with the frontend.
    The default implementation is a single-turn Claude call with optional
    tool-use loop (up to ``max_tool_iterations`` rounds).

    Override ``stream()`` or ``_build_messages()`` for custom behaviour.
    """

    name: str
    description: str
    mode: str | None = None      # maps to a system-prompt variant in llm.py
    tools: list[Tool] = []       # declare tools your agent can call

    def __init__(self, llm: LLMService | None = None) -> None:
        self._llm = llm or get_llm()

    @property
    def system_prompt(self) -> str:
        return get_system_prompt(self.mode)

    # ── Public streaming interface ────────────────────────────────────────────

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        """
        Yields SSE strings.  Drives the Claude conversation + tool loop.
        Override this for multi-step orchestration (planner → executor, RAG, etc.).
        """
        messages = self._build_messages(ctx)
        anthropic_tools = [t.to_anthropic_format() for t in self.tools] or None
        message_id = str(uuid.uuid4())

        yield sse_agent_step("start", f"Running {self.name} agent…")

        accumulated = ""
        in_tok: int | None = None
        out_tok: int | None = None

        async for etype, edata in self._llm.stream(
            messages, system=self.system_prompt, tools=anthropic_tools
        ):
            if etype == "text":
                chunk = edata["text"]
                accumulated += chunk
                yield sse_delta(chunk)
            elif etype == "input_tokens":
                in_tok = edata["count"]
            elif etype == "output_tokens":
                out_tok = edata["count"]
            elif etype == "tool_use":
                yield sse_tool_use(edata["name"], {}, edata["id"])
                # ── Stub: execute tool and feed result back ──────────────────
                result = await self._execute_tool(edata["name"], {}, ctx)
                yield sse_tool_result(edata["id"], result)
                # Append tool exchange to messages and continue streaming.
                messages = self._append_tool_exchange(
                    messages, edata["id"], edata["name"], result
                )

        yield sse_done(message_id)

    async def run_once(self, ctx: AgentContext) -> str:
        """Collect the full response as a single string (for A2A chaining)."""
        import json
        parts: list[str] = []
        async for chunk in self.stream(ctx):
            if chunk.startswith("data:"):
                try:
                    payload = json.loads(chunk[5:].strip())
                    if "delta" in payload:
                        parts.append(payload["delta"])
                except Exception:
                    pass
        return "".join(parts)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _build_messages(self, ctx: AgentContext) -> list[MessageParam]:
        return [*ctx.chat_history, {"role": "user", "content": ctx.query}]

    async def _execute_tool(
        self, name: str, inputs: dict[str, Any], ctx: AgentContext
    ) -> str:
        for tool in self.tools:
            if tool.name == name:
                try:
                    return await tool.execute(inputs, ctx)
                except Exception as exc:
                    logger.exception("Tool %s failed", name)
                    return f"[tool error: {exc}]"
        return f"[tool '{name}' not found]"

    @staticmethod
    def _append_tool_exchange(
        messages: list[MessageParam],
        tool_use_id: str,
        tool_name: str,
        result: str,
    ) -> list[MessageParam]:
        return [
            *messages,
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": tool_use_id, "name": tool_name, "input": {}}],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": result}],
            },
        ]
