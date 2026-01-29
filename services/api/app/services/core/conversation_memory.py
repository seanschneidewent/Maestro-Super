"""Conversation memory utilities for reconstructing conversation history."""

import logging
from typing import Any

from sqlalchemy.orm import Session as DbSession

from app.models.query import Query

logger = logging.getLogger(__name__)


def trace_to_messages(
    query_text: str,
    trace: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert a stored trace to minimal history messages.

    For conversation context, we only need:
    - What the user asked
    - What the assistant said (final response text)

    Tool calls and results are NOT included because:
    - Fresh pre-fetch data is injected every query
    - The LLM doesn't need to know HOW previous answers were found
    - This keeps history tokens minimal (~100 per turn instead of ~10k)
    """
    messages: list[dict[str, Any]] = []

    # User message
    messages.append({"role": "user", "content": query_text})

    if not trace:
        return messages

    # Extract just the assistant's text responses (reasoning), skip tool stuff
    # The final reasoning block is typically the actual answer
    assistant_texts = []
    for step in trace:
        if step.get("type") in ("response", "reasoning"):
            content = step.get("content", "").strip()
            if content:
                assistant_texts.append(content)

    # Combine all assistant text into one message
    if assistant_texts:
        # Usually the last text block is the actual answer
        # Include all for context but could optimize to just last
        combined = "\n".join(assistant_texts)
        messages.append({"role": "assistant", "content": combined})

    return messages


def fetch_conversation_history(
    db: DbSession,
    conversation_id: str,
    exclude_query_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch and reconstruct conversation history for a conversation.

    Args:
        db: Database session
        conversation_id: Conversation UUID
        exclude_query_id: Query ID to exclude (usually current query)

    Returns:
        List of OpenAI-format messages for all previous queries in conversation
    """
    query = (
        db.query(Query)
        .filter(Query.conversation_id == conversation_id)
        .filter(Query.hidden == False)  # noqa: E712
        .order_by(Query.sequence_order.asc())
    )

    if exclude_query_id:
        query = query.filter(Query.id != exclude_query_id)

    previous_queries = query.all()

    all_messages: list[dict[str, Any]] = []

    for prev_query in previous_queries:
        if prev_query.trace:
            messages = trace_to_messages(
                query_text=prev_query.query_text,
                trace=prev_query.trace,
            )
            all_messages.extend(messages)

    logger.info(
        f"Loaded {len(all_messages)} history messages from {len(previous_queries)} "
        f"previous queries in conversation {conversation_id}"
    )

    return all_messages
