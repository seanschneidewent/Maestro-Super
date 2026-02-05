"""Learning agent for Maestro V3."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict
from typing import Any, AsyncIterator
from uuid import uuid4

from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.services.v3.learning_tool_executor import execute_learning_tool
from app.services.v3.providers import chat_completion
from app.types.learning import InteractionPackage
from app.types.session import LiveSession

logger = logging.getLogger(__name__)


LEARNING_TOOLS: list[dict[str, Any]] = [
    # Experience filesystem
    {
        "name": "read_file",
        "description": "Read an Experience file.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Create or overwrite an Experience file. "
            "When creating a new extended file, also update routing_rules.md."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Surgical edit to an existing Experience file.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "list_files",
        "description": "List all Experience files for this project.",
        "parameters": {"type": "object", "properties": {}},
    },
    # Knowledge read
    {
        "name": "read_pointer",
        "description": "Read a Pointer's full description.",
        "parameters": {
            "type": "object",
            "properties": {"pointer_id": {"type": "string"}},
            "required": ["pointer_id"],
        },
    },
    {
        "name": "read_page",
        "description": "Read page-level data (sheet reflection, cross references).",
        "parameters": {
            "type": "object",
            "properties": {"page_id": {"type": "string"}},
            "required": ["page_id"],
        },
    },
    {
        "name": "search_knowledge",
        "description": "Semantic search across Pointers.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    # Knowledge write
    {
        "name": "edit_pointer",
        "description": "Edit a Pointer's description or cross_references.",
        "parameters": {
            "type": "object",
            "properties": {
                "pointer_id": {"type": "string"},
                "field": {"type": "string", "enum": ["description", "cross_references"]},
                "new_content": {"type": "string"},
            },
            "required": ["pointer_id", "field", "new_content"],
        },
    },
    {
        "name": "edit_page",
        "description": "Edit page-level data.",
        "parameters": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string"},
                "field": {"type": "string", "enum": ["sheet_reflection", "cross_references"]},
                "new_content": {"type": "string"},
            },
            "required": ["page_id", "field", "new_content"],
        },
    },
    {
        "name": "update_cross_references",
        "description": "Update a Pointer's cross_references list.",
        "parameters": {
            "type": "object",
            "properties": {
                "pointer_id": {"type": "string"},
                "references": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["pointer_id", "references"],
        },
    },
    # Re-ground
    {
        "name": "trigger_reground",
        "description": (
            "Spawn Brain Mode to re-analyze a page region. "
            "Use ONLY for vision errors (wrong bbox, missed region), not text corrections."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string"},
                "instruction": {"type": "string"},
            },
            "required": ["page_id", "instruction"],
        },
    },
]


def _build_learning_system_prompt() -> str:
    return "\n\n".join(
        [
            "You are the Learning agent for Maestro. You observe every interaction between Maestro and the superintendent.",
            "Your job: evaluate the interaction, identify what can be learned, and write it to Experience or fix Knowledge.",
            "You do not answer the user directly. You only act through tools and concise summaries.",
            "",
            "Priorities:",
            "- Corrections: If the user corrects Maestro, update Knowledge (Pointer descriptions) or log to corrections.md.",
            "- Routing patterns: If you see consistent routing needs, update routing_rules.md.",
            "- Preferences: Log user preferences to preferences.md.",
            "- Schedule info: Add to schedule.md.",
            "- Gaps: If Maestro was uncertain or missing info, log to gaps.md.",
            "",
            "Choose the right action level:",
            "- Wrong text in a Pointer -> edit_pointer (description) or update_cross_references.",
            "- Wrong vision / missed region -> trigger_reground (rare).",
            "- Retrieval behavior issue -> update Experience (routing_rules.md).",
            "",
            "When creating a new extended Experience file, ALWAYS update routing_rules.md so Maestro can find it.",
            "Be surgical and concise. Avoid verbose commentary.",
        ]
    ).strip()


def _format_interaction(interaction: InteractionPackage) -> str:
    if isinstance(interaction, dict):
        payload = interaction
    else:
        payload = asdict(interaction)
    return "Interaction package:\n" + json.dumps(payload, indent=2)


def _thinking_event(
    panel: str,
    content: str,
    turn_number: int,
) -> dict[str, Any]:
    return {
        "type": "thinking",
        "panel": panel,
        "content": content,
        "turn_number": turn_number,
    }


def _tool_summary(tool_name: str, tool_args: dict[str, Any], result: Any) -> str:
    if tool_name in {"write_file", "edit_file"}:
        return f"{tool_name}: {tool_args.get('path')}"
    if tool_name == "edit_pointer":
        return f"edit_pointer: {tool_args.get('pointer_id')} ({tool_args.get('field')})"
    if tool_name == "edit_page":
        return f"edit_page: {tool_args.get('page_id')} ({tool_args.get('field')})"
    if tool_name == "update_cross_references":
        return f"update_cross_references: {tool_args.get('pointer_id')}"
    if tool_name == "trigger_reground":
        new_ids = []
        if isinstance(result, dict):
            new_ids = result.get("new_pointer_ids") or []
        suffix = f" -> {len(new_ids)} new pointers" if new_ids else ""
        return f"trigger_reground: {tool_args.get('page_id')}{suffix}"
    return f"{tool_name}"


async def run_learning_turn(
    session: LiveSession,
    interaction: InteractionPackage,
    db: DBSession,
) -> AsyncIterator[dict[str, Any]]:
    turn_number = 0
    if isinstance(interaction, dict):
        try:
            turn_number = int(interaction.get("turn_number") or 0)
        except Exception:
            turn_number = 0
    else:
        turn_number = interaction.turn_number

    session.learning_messages.append(
        {"role": "user", "content": _format_interaction(interaction)}
    )
    session.dirty = True

    system_prompt = _build_learning_system_prompt()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *session.learning_messages,
    ]

    settings = get_settings()
    model = settings.learning_model

    while True:
        iteration_text = ""
        tool_calls: list[dict[str, Any]] = []

        async for chunk in chat_completion(messages, LEARNING_TOOLS, model=model, stream=True):
            event_type = chunk.get("type")
            if event_type == "token":
                iteration_text += chunk.get("content") or ""
            elif event_type == "thinking":
                content = chunk.get("content") or ""
                if content:
                    yield _thinking_event("learning", content, turn_number)
            elif event_type == "tool_call":
                tool_calls.append(
                    {
                        "id": chunk.get("id") or str(uuid4()),
                        "name": chunk.get("name"),
                        "arguments": chunk.get("arguments") or {},
                    }
                )
            elif event_type == "done":
                break

        if tool_calls:
            assistant_message = {
                "role": "assistant",
                "content": iteration_text,
                "tool_calls": tool_calls,
            }
            messages.append(assistant_message)

            for call in tool_calls:
                result = await execute_learning_tool(
                    call["name"],
                    call["arguments"],
                    session,
                    db,
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "name": call["name"],
                        "content": result,
                    }
                )

                panel = None
                if call["name"] in {"write_file", "edit_file"}:
                    panel = "learning"
                elif call["name"] in {"edit_pointer", "edit_page", "update_cross_references", "trigger_reground"}:
                    panel = "knowledge_update"

                if panel:
                    summary = _tool_summary(call["name"], call["arguments"], result)
                    yield _thinking_event(panel, summary, turn_number)

                session.dirty = True

            continue

        if iteration_text:
            yield _thinking_event("learning", iteration_text, turn_number)

        session.learning_messages.append(
            {"role": "assistant", "content": iteration_text}
        )
        session.dirty = True
        session.last_active = time.time()

        yield {"type": "learning_done", "turn_number": turn_number}
        break


async def run_learning_worker(
    session: LiveSession,
    db_factory,
) -> None:
    """Background task per session. Pulls from learning_queue and processes interactions."""
    while True:
        try:
            interaction = await session.learning_queue.get()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Learning queue error for session %s: %s", session.session_id, exc)
            await asyncio.sleep(0.5)
            continue

        db = db_factory()
        try:
            async for event in run_learning_turn(session, interaction, db):
                try:
                    session.event_bus.put_nowait(event)
                except Exception:
                    logger.debug("Event bus full or unavailable for session %s", session.session_id)
            session.dirty = True
        except asyncio.CancelledError:
            db.close()
            break
        except Exception as exc:
            logger.exception("Learning worker error for session %s: %s", session.session_id, exc)
        finally:
            db.close()
