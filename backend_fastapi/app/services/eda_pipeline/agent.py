"""LangGraph ReAct agent for follow-up turns."""
from __future__ import annotations

import logging

from app.config import get_settings
from app.services.eda_pipeline import dial
from app.services.eda_pipeline.prompts import react_system
from app.services.eda_pipeline.tools import make_tools
from app.services.eda_pipeline.vectorstore import HybridVectorStore
from app.services.eda_pipeline.workspace import Workspace

logger = logging.getLogger(__name__)
_s = get_settings()


def _content_to_str(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # some models return content blocks
        parts = []
        for b in content:
            if isinstance(b, dict):
                parts.append(b.get("text", ""))
            else:
                parts.append(str(b))
        return "".join(parts)
    return str(content)


def run_react(ws: Workspace, store: HybridVectorStore, question: str, facts: str) -> str:
    """Answer a follow-up question with the ReAct agent (tools + facts context)."""
    if not dial.available():
        return _mock_answer(store, question)

    from langchain_core.messages import HumanMessage, SystemMessage
    from langgraph.prebuilt import create_react_agent

    model = dial.get_langchain_chat()
    tools = make_tools(ws, store)
    agent = create_react_agent(model, tools)

    result = agent.invoke(
        {"messages": [SystemMessage(react_system(facts)), HumanMessage(question)]},
        config={"recursion_limit": _s.eda_react_max_iterations * 2 + 5},
    )
    return _content_to_str(result["messages"][-1].content)


def _mock_answer(store: HybridVectorStore, question: str) -> str:
    """Offline path: show retrieval works, without calling the LLM."""
    hits = store.search(question, k=_s.eda_vector_top_k)
    lines = ["**[Mock follow-up answer]** DIAL not configured — echoing retrieved context.\n"]
    for i, h in enumerate(hits, 1):
        m = h["metadata"]
        lines.append(f"{i}. (cell_index={m.get('cell_index')}, section={m.get('section')}) {h['text'][:200]}…")
    if not hits:
        lines.append("_(vector store empty)_")
    lines.append(
        "\n<<FOLLOWUPS>>\n1. Placeholder question one?\n2. Placeholder question two?\n"
        "3. Placeholder question three?\n4. Placeholder question four?\n5. Placeholder question five?\n<<END>>"
    )
    return "\n".join(lines)
