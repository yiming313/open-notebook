"""Per-source chat graph.

Physically unified with :mod:`open_notebook.graphs.chat`: both graphs
render the **same** ``prompts/chat/system.jinja`` template, call
``provision_langchain_model("chat", max_tokens=8192)``, and stuff the
full text of the user-selected content into the prompt without
truncation.

History note: the previous implementation built context through
``ContextBuilder`` and ran the result through ``_format_source_context``,
which hard-clamped ``source.full_text`` at 5000 characters and never
included notes — so answers about long sources were systematically
worse than answers from the notebook-level Chat. We now call
``source.get_context("long")`` (full text, no clamp) and skip the custom
formatter entirely.

The graph is invoked exactly like Notebook Chat:
SQLite checkpointing per ``thread_id`` (== chat session id), single
``call_model`` node, no RAG.
"""

import asyncio
import sqlite3
from typing import Annotated, Dict, List, Optional

from ai_prompter import Prompter
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from open_notebook.ai.provision import provision_langchain_model
from open_notebook.config import LANGGRAPH_CHECKPOINT_FILE
from open_notebook.domain.notebook import Source
from open_notebook.exceptions import OpenNotebookError
from open_notebook.utils import clean_thinking_content
from open_notebook.utils.error_classifier import classify_error
from open_notebook.utils.text_utils import extract_text_content


class SourceChatState(TypedDict):
    messages: Annotated[list, add_messages]
    source_id: str
    context: Optional[str]
    model_override: Optional[str]
    # Surface IDs the model can cite, so the UI can highlight which
    # source/insights/notes contributed to this turn. Notes are always
    # empty for the per-source view; insights pick up the source's
    # attached insights.
    context_indicators: Optional[Dict[str, List[str]]]


def _run_async_in_sync(coro_factory):
    """Run an async callable from a sync LangGraph node.

    Same dance used in :mod:`chat` — LangGraph nodes are sync but our
    domain layer is async."""

    def run_in_new_loop():
        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            return new_loop.run_until_complete(coro_factory())
        finally:
            new_loop.close()
            asyncio.set_event_loop(None)

    try:
        asyncio.get_running_loop()
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_in_new_loop)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro_factory())


def call_model_with_source_context(
    state: SourceChatState, config: RunnableConfig
) -> dict:
    """Render the same chat system prompt notebook chat uses, with the
    selected source's full text as the only context entry."""
    try:
        return _inner(state, config)
    except OpenNotebookError:
        raise
    except Exception as e:
        error_class, user_message = classify_error(e)
        raise error_class(user_message) from e


def _inner(state: SourceChatState, config: RunnableConfig) -> dict:
    source_id = state.get("source_id")
    if not source_id:
        raise ValueError("source_id is required in state")

    # Fetch source + build the long-form context (full text, no truncation).
    async def _load() -> dict:
        source = await Source.get(source_id)
        if not source:
            raise ValueError(f"Source {source_id} not found")
        return await source.get_context(context_size="long")

    source_context: dict = _run_async_in_sync(_load)

    insight_ids = [
        ins.get("id") for ins in source_context.get("insights", []) if ins.get("id")
    ]
    context_indicators = {
        "sources": [source_context.get("id")] if source_context.get("id") else [],
        "insights": insight_ids,
        "notes": [],
    }

    # Stringify for the chat template. We embed the dict literally —
    # the model just needs to see the title/ID/full_text/insights as
    # text, the exact serialisation format doesn't matter as long as
    # the IDs are visible for citations.
    import json as _json

    context_str = _json.dumps(
        {"sources": [source_context], "notes": []},
        ensure_ascii=False,
        default=str,
    )

    # SAME template as Notebook Chat (prompts/chat/system.jinja). The
    # template renders an optional ``notebook`` block (we leave it None)
    # and the ``context`` block we just built.
    system_prompt = Prompter(prompt_template="chat/system").render(
        data={"notebook": None, "context": context_str, "context_config": None}
    )
    payload = [SystemMessage(content=system_prompt)] + state.get("messages", [])

    model_id = config.get("configurable", {}).get("model_id") or state.get(
        "model_override"
    )

    async def _provision():
        return await provision_langchain_model(
            str(payload), model_id, "chat", max_tokens=8192
        )

    model = _run_async_in_sync(_provision)

    ai_message = model.invoke(payload)
    content = extract_text_content(ai_message.content)
    cleaned_content = clean_thinking_content(content)
    cleaned_message = ai_message.model_copy(update={"content": cleaned_content})

    return {
        "messages": cleaned_message,
        "context": context_str,
        "context_indicators": context_indicators,
    }


# Create SQLite checkpointer (same file as chat — thread_id partitions
# the two feature areas, so there is no collision).
conn = sqlite3.connect(
    LANGGRAPH_CHECKPOINT_FILE,
    check_same_thread=False,
)
memory = SqliteSaver(conn)

# Create the StateGraph
source_chat_state = StateGraph(SourceChatState)
source_chat_state.add_node("source_chat_agent", call_model_with_source_context)
source_chat_state.add_edge(START, "source_chat_agent")
source_chat_state.add_edge("source_chat_agent", END)
source_chat_graph = source_chat_state.compile(checkpointer=memory)
