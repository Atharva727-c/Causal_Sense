"""SSE wire-format helpers.

Wire format is 100% compatible with the existing Express backend so the
React frontend works with zero changes:

  data: {"event":"start","userMsgId":"<uuid>"}\\n\\n
  data: {"delta":"<text>"}\\n\\n
  data: {"event":"done","assistantMsgId":"<uuid>","title":"<title>"}\\n\\n
  data: {"event":"error","code":"<str>","message":"<str>"}\\n\\n

Agent-specific events (future frontend integration):
  data: {"event":"agent_step","stepType":"thinking","content":"..."}\\n\\n
  data: {"event":"tool_use","toolName":"...","toolInput":{...},"toolUseId":"..."}\\n\\n
  data: {"event":"tool_result","toolUseId":"...","content":"...","isError":false}\\n\\n
"""
from __future__ import annotations
import json
from typing import Any


def _encode(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def sse_start(user_msg_id: str) -> str:
    return _encode({"event": "start", "userMsgId": user_msg_id})


def sse_delta(text: str) -> str:
    return _encode({"delta": text})


def sse_done(assistant_msg_id: str, title: str = "") -> str:
    return _encode({"event": "done", "assistantMsgId": assistant_msg_id, "title": title})


def sse_error(code: str, message: str) -> str:
    return _encode({"event": "error", "code": code, "message": message})


def sse_agent_step(step_type: str, content: str, metadata: dict | None = None) -> str:
    return _encode({
        "event": "agent_step",
        "stepType": step_type,
        "content": content,
        "metadata": metadata or {},
    })


def sse_tool_use(tool_name: str, tool_input: dict, tool_use_id: str) -> str:
    return _encode({
        "event": "tool_use",
        "toolName": tool_name,
        "toolInput": tool_input,
        "toolUseId": tool_use_id,
    })


def sse_tool_result(tool_use_id: str, content: str, is_error: bool = False) -> str:
    return _encode({
        "event": "tool_result",
        "toolUseId": tool_use_id,
        "content": content,
        "isError": is_error,
    })
