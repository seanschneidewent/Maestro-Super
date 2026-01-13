"""Conversation memory utilities for reconstructing conversation history."""

import hashlib
import json
import logging
from typing import Any

from sqlalchemy.orm import Session as DbSession

from app.models.query import Query

logger = logging.getLogger(__name__)


def generate_tool_call_id(query_id: str, tool_index: int) -> str:
    """
    Generate a deterministic tool call ID from query_id and index.

    OpenAI format requires unique IDs like "call_abc123".
    We generate these deterministically so the same trace always
    produces the same IDs.
    """
    seed = f"{query_id}:{tool_index}"
    hash_suffix = hashlib.md5(seed.encode()).hexdigest()[:12]
    return f"call_{hash_suffix}"


def trace_to_messages(
    query_text: str,
    trace: list[dict[str, Any]],
    query_id: str,
) -> list[dict[str, Any]]:
    """
    Convert a stored trace back to OpenAI message format.

    Args:
        query_text: The user's original query
        trace: The stored trace from Query.trace
        query_id: Query UUID for generating deterministic tool call IDs

    Returns:
        List of OpenAI-format messages representing this query's conversation

    Trace format (stored):
        {"type": "response", "content": "..."}
        {"type": "tool_call", "tool": "...", "input": {...}}
        {"type": "tool_result", "tool": "...", "result": {...}}

    OpenAI format (output):
        {"role": "user", "content": "..."}
        {"role": "assistant", "content": "...", "tool_calls": [...]}
        {"role": "tool", "tool_call_id": "...", "content": "..."}
    """
    messages: list[dict[str, Any]] = []

    # Start with user message
    messages.append({"role": "user", "content": query_text})

    if not trace:
        return messages

    # Process trace steps
    # Group consecutive response + tool_call + tool_result into assistant turns
    i = 0
    tool_call_counter = 0

    while i < len(trace):
        step = trace[i]
        step_type = step.get("type")

        if step_type == "response" or step_type == "reasoning":
            # Start of an assistant turn - collect content and any following tool calls
            # Handle both "response" (old traces) and "reasoning" (new traces) for backwards compatibility
            assistant_content = step.get("content", "")
            tool_calls: list[dict[str, Any]] = []
            tool_results: list[dict[str, Any]] = []

            i += 1

            # Collect all tool_call/tool_result pairs that follow
            while i < len(trace):
                next_step = trace[i]
                next_type = next_step.get("type")

                if next_type == "tool_call":
                    tool_name = next_step.get("tool", "")
                    tool_input = next_step.get("input", {})
                    tool_id = generate_tool_call_id(query_id, tool_call_counter)
                    tool_call_counter += 1

                    tool_calls.append({
                        "id": tool_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(tool_input),
                        },
                    })
                    i += 1

                elif next_type == "tool_result":
                    tool_result = next_step.get("result", {})

                    # Match to most recent unmatched tool call
                    if len(tool_results) < len(tool_calls):
                        matched_tool_id = tool_calls[len(tool_results)]["id"]
                        tool_results.append({
                            "role": "tool",
                            "tool_call_id": matched_tool_id,
                            "content": json.dumps(tool_result),
                        })
                    i += 1

                elif next_type == "response":
                    # New assistant turn starts
                    break
                else:
                    i += 1

            # Build assistant message
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            if assistant_content:
                assistant_msg["content"] = assistant_content
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls

            messages.append(assistant_msg)

            # Add tool results
            messages.extend(tool_results)

        elif step_type == "tool_call":
            # Tool call without preceding response (edge case)
            tool_name = step.get("tool", "")
            tool_input = step.get("input", {})
            tool_id = generate_tool_call_id(query_id, tool_call_counter)
            tool_call_counter += 1

            assistant_msg = {
                "role": "assistant",
                "tool_calls": [{
                    "id": tool_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_input),
                    },
                }],
            }
            messages.append(assistant_msg)

            # Look for matching tool_result
            i += 1
            if i < len(trace) and trace[i].get("type") == "tool_result":
                tool_result = trace[i].get("result", {})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": json.dumps(tool_result),
                })
                i += 1

        else:
            i += 1

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
                query_id=str(prev_query.id),
            )
            all_messages.extend(messages)

    logger.info(
        f"Loaded {len(all_messages)} history messages from {len(previous_queries)} "
        f"previous queries in conversation {conversation_id}"
    )

    return all_messages
