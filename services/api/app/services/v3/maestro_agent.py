"""Maestro agent for V3 sessions."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from typing import Any, AsyncIterator
from uuid import uuid4

from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.models.project import Project
from app.services.v3.experience import read_experience_for_query
from app.services.v3.providers import chat_completion
from app.services.v3.tool_executor import execute_maestro_tool
from app.types.learning import InteractionPackage
from app.types.session import LiveSession

HEARTBEAT_TRIGGER_PREFIX = "[HEARTBEAT TRIGGER"

logger = logging.getLogger(__name__)


def _create_panel_state() -> dict[str, str]:
    return {
        "workspace_assembly": "",
        "learning": "",
        "knowledge_update": "",
    }


def _append_panel_text(current: str, incoming: str) -> str:
    if not incoming:
        return current
    return f"{current}\n{incoming}" if current else incoming


def _append_panel(panel_state: dict[str, str], panel: str, content: str) -> None:
    if not content:
        return
    existing = panel_state.get(panel, "")
    panel_state[panel] = _append_panel_text(existing, content)


def _format_tool_event(kind: str, name: str, payload: dict[str, Any] | list[Any]) -> str:
    try:
        formatted = json.dumps(payload, indent=2)
    except TypeError:
        formatted = json.dumps(str(payload))
    return f"**Tool {kind}**: {name}\n{formatted}"


WORKSPACE_TOOLS = [
    {
        "name": "search_knowledge",
        "description": "Search the project's knowledge base of Pointers for relevant details.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_pointer",
        "description": "Read a specific Pointer's rich description and cross-references.",
        "parameters": {
            "type": "object",
            "properties": {"pointer_id": {"type": "string"}},
            "required": ["pointer_id"],
        },
    },
    {
        "name": "read_experience",
        "description": "Read a specific Experience file by path.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "list_experience",
        "description": "List all Experience files for the current project.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "add_pages",
        "description": "Add plan pages to the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "page_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["page_ids"],
        },
    },
    {
        "name": "remove_pages",
        "description": "Remove plan pages from the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "page_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["page_ids"],
        },
    },
    {
        "name": "highlight_pointers",
        "description": "Highlight pointers in the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "pointer_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["pointer_ids"],
        },
    },
    {
        "name": "pin_page",
        "description": "Pin a page to keep it at the top of the workspace.",
        "parameters": {
            "type": "object",
            "properties": {"page_id": {"type": "string"}},
            "required": ["page_id"],
        },
    },
]


TELEGRAM_TOOLS = [
    {
        "name": "search_knowledge",
        "description": "Search the project's knowledge base of Pointers for relevant details.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_pointer",
        "description": "Read a specific Pointer's rich description and cross-references.",
        "parameters": {
            "type": "object",
            "properties": {"pointer_id": {"type": "string"}},
            "required": ["pointer_id"],
        },
    },
    {
        "name": "read_experience",
        "description": "Read a specific Experience file by path.",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "list_experience",
        "description": "List all Experience files for the current project.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "list_workspaces",
        "description": "List active workspaces for the current project.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "workspace_action",
        "description": "Trigger a workspace action (add/remove pages, highlight pointers, pin page).",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "session_id": {"type": "string"},
                "page_ids": {"type": "array", "items": {"type": "string"}},
                "pointer_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["action", "session_id"],
        },
    },
]


HEARTBEAT_INSTRUCTIONS = """This is your scheduled proactive turn. The superintendent did NOT message you.

Your options:
- TELL: Share a proactive insight (upcoming activity × plan detail = actionable info)
- ASK: Ask a calculated scheduling question that fills a gap in your understanding

Requirements:
- Ground everything in Knowledge (use search_knowledge tool) and Experience (read schedule.md)
- Be concise. One insight or one question per heartbeat. Not both.
- If you have nothing valuable to share, say so briefly: "All clear on my end. Let me know if anything changes."
- Never repeat a question you already asked (check your conversation history)
- Your message should read like a text from a knowledgeable colleague, not software."""


def build_maestro_system_prompt(
    session_type: str,
    workspace_state: dict[str, Any] | None,
    experience_context: str,
    project_name: str | None,
    workspace_list: list[dict[str, Any]] | None = None,
    is_heartbeat: bool = False,
) -> str:
    if session_type == "workspace":
        channel_block = (
            "You are chatting in the web workspace. You can assemble plan pages on screen using tools."
        )
    else:
        # Telegram-specific prompt
        channel_block = """You're on Telegram. The superintendent is on the jobsite, phone in pocket.

Communication style for Telegram:
- Keep responses mobile-friendly: short paragraphs, no markdown tables, concise.
- Don't tell them to 'open the workspace' unless they need to see plans. Answer from Knowledge when you can.
- When the super shares schedule info, corrections, or field conditions — acknowledge what they told you.
- You can take actions in workspaces remotely using the workspace_action tool."""

        # Add workspace awareness if available
        if workspace_list:
            workspace_names = [w.get("workspace_name", "Unnamed") for w in workspace_list if w.get("workspace_name")]
            if workspace_names:
                channel_block += f"\n\nActive workspaces: {', '.join(workspace_names)}"

    workspace_line = ""
    if session_type == "workspace" and workspace_state is not None:
        workspace_line = f"Current workspace state: {json.dumps(workspace_state)}"

    experience_block = experience_context or "(No Experience context available.)"

    project_line = f"Project: {project_name}" if project_name else ""

    heartbeat_block = HEARTBEAT_INSTRUCTIONS if is_heartbeat else ""

    parts = [
        "You are Maestro, a construction plan analysis partner for superintendents.",
        "Be honest about uncertainty. If you are unsure, say so and ask a clarifying question.",
        channel_block,
        project_line,
        workspace_line,
        heartbeat_block,
        "Experience context (read-only):",
        experience_block,
        "Use tools to search knowledge, read pointers, and update the workspace when needed.",
    ]

    return "\n\n".join(p for p in parts if p).strip()


def _workspace_state_payload(session: LiveSession) -> dict[str, Any] | None:
    if session.workspace_state is None:
        return None
    return asdict(session.workspace_state)


def _workspace_update_event(
    action: str,
    result: dict[str, Any] | list[dict[str, Any]],
    session: LiveSession,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "workspace_update",
        "action": action,
        "workspace_state": _workspace_state_payload(session),
    }

    if isinstance(result, dict):
        if result.get("page_ids"):
            payload["page_ids"] = result.get("page_ids")
        if result.get("pointer_ids"):
            payload["pointer_ids"] = result.get("pointer_ids")
        if result.get("pages"):
            payload["pages"] = result.get("pages")
        if result.get("pointers"):
            payload["pointers"] = result.get("pointers")
        if result.get("pinned_pages"):
            payload["pinned_pages"] = result.get("pinned_pages")
        if result.get("page_id") and "page_ids" not in payload:
            payload["page_ids"] = [result.get("page_id")]
    return payload


async def run_maestro_turn(
    session: LiveSession,
    user_message: str,
    db: DBSession,
) -> AsyncIterator[dict[str, Any]]:
    # Detect if this is a heartbeat turn
    is_heartbeat = user_message.startswith(HEARTBEAT_TRIGGER_PREFIX)

    turn_number = (
        sum(1 for message in session.maestro_messages if message.get("role") == "user")
        + 1
    )
    session.maestro_messages.append(
        {"role": "user", "content": user_message, "turn_number": turn_number}
    )
    session.last_active = time.time()

    panel_state = _create_panel_state()

    pointers_retrieved: list[dict[str, Any]] = []
    workspace_actions: list[dict[str, Any]] = []
    retrieved_ids: set[str] = set()

    experience_context, paths_read = read_experience_for_query(
        project_id=str(session.project_id),
        user_query=user_message,
        db=db,
    )

    project_name = None
    project = db.query(Project).filter(Project.id == str(session.project_id)).first()
    if project:
        project_name = project.name

    system_prompt = build_maestro_system_prompt(
        session_type=session.session_type,
        workspace_state=_workspace_state_payload(session),
        experience_context=experience_context,
        project_name=project_name,
        is_heartbeat=is_heartbeat,
    )

    tools = WORKSPACE_TOOLS if session.session_type == "workspace" else TELEGRAM_TOOLS

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *session.maestro_messages,
    ]

    settings = get_settings()
    model = settings.maestro_model

    while True:
        iteration_text = ""
        tool_calls: list[dict[str, Any]] = []

        async for chunk in chat_completion(messages, tools, model=model, stream=True):
            event_type = chunk.get("type")
            if event_type == "token":
                content = chunk.get("content") or ""
                iteration_text += content
                yield {"type": "token", "content": content}
            elif event_type == "thinking":
                content = chunk.get("content") or ""
                if content:
                    _append_panel(panel_state, "workspace_assembly", content)
                    yield {
                        "type": "thinking",
                        "panel": "workspace_assembly",
                        "content": content,
                    }
            elif event_type == "tool_call":
                tool_calls.append(
                    {
                        "id": chunk.get("id") or str(uuid4()),
                        "name": chunk.get("name"),
                        "arguments": chunk.get("arguments") or {},
                    }
                )
                _append_panel(
                    panel_state,
                    "workspace_assembly",
                    _format_tool_event(
                        "call",
                        str(chunk.get("name") or ""),
                        chunk.get("arguments") or {},
                    ),
                )
                yield {
                    "type": "tool_call",
                    "tool": chunk.get("name"),
                    "arguments": chunk.get("arguments") or {},
                }
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
                result = await execute_maestro_tool(
                    call["name"],
                    call["arguments"],
                    session,
                    db,
                )
                session.dirty = True
                session.last_active = time.time()

                yield {
                    "type": "tool_result",
                    "tool": call["name"],
                    "result": result,
                }
                _append_panel(
                    panel_state,
                    "workspace_assembly",
                    _format_tool_event("result", call["name"], result),
                )

                if call["name"] == "search_knowledge" and isinstance(result, list):
                    for item in result:
                        if not isinstance(item, dict):
                            continue
                        pointer_id = item.get("pointer_id")
                        if not pointer_id or pointer_id in retrieved_ids:
                            continue
                        pointers_retrieved.append(
                            {
                                "pointer_id": pointer_id,
                                "title": item.get("title"),
                                "description_snippet": item.get("description_snippet")
                                or item.get("relevance_snippet"),
                            }
                        )
                        retrieved_ids.add(pointer_id)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "name": call["name"],
                        "content": result,
                    }
                )

                if call["name"] in {"add_pages", "remove_pages", "highlight_pointers", "pin_page"}:
                    yield _workspace_update_event(call["name"], result, session)
                    action_entry: dict[str, Any] = {"action": call["name"]}
                    if isinstance(result, dict):
                        if result.get("page_ids"):
                            action_entry["page_ids"] = result.get("page_ids")
                        if result.get("pointer_ids"):
                            action_entry["pointer_ids"] = result.get("pointer_ids")
                        if result.get("page_id") and "page_ids" not in action_entry:
                            action_entry["page_ids"] = [result.get("page_id")]
                    workspace_actions.append(action_entry)

                if call["name"] == "workspace_action":
                    action_entry = {
                        "action": (result.get("action") if isinstance(result, dict) else None)
                        or call["arguments"].get("action"),
                    }
                    page_ids = call["arguments"].get("page_ids") or []
                    pointer_ids = call["arguments"].get("pointer_ids") or []
                    if page_ids:
                        action_entry["page_ids"] = page_ids
                    if pointer_ids:
                        action_entry["pointer_ids"] = pointer_ids
                    workspace_actions.append(action_entry)

            continue

        # Final response
        session.maestro_messages.append(
            {
                "role": "assistant",
                "content": iteration_text,
                "turn_number": turn_number,
                "panels": panel_state,
            }
        )
        session.dirty = True
        session.last_active = time.time()

        interaction_package = InteractionPackage(
            user_query=user_message,
            maestro_response=iteration_text,
            pointers_retrieved=pointers_retrieved,
            experience_context_used=paths_read,
            workspace_actions=workspace_actions,
            turn_number=turn_number,
            timestamp=time.time(),
            is_heartbeat=is_heartbeat,
        )
        try:
            session.learning_queue.put_nowait(interaction_package)
        except Exception:
            logger.debug("Learning queue unavailable for session %s", session.session_id)

        yield {"type": "done"}
        break
