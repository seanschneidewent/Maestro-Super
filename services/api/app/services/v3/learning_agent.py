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
from app.services.v3.benchmark import update_benchmark_learning
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


BENCHMARK_EVALUATION_INSTRUCTIONS = """
## Benchmark Evaluation (Phase 7)

After evaluating each interaction, provide a structured assessment in your final summary.

Format your final response as:
```
ASSESSMENT: [2-3 sentence evaluation of this interaction]

SCORES: {
  "dimension_name": score (0-1),
  ...
}

ACTIONS: [list of actions taken: Experience writes, Knowledge edits, or "none"]
```

Scoring dimensions should EMERGE from what you observe - don't use a fixed rubric.
Common dimensions (use what applies):
- retrieval_relevance: Did Maestro find the right Pointers?
- response_accuracy: Was the answer correct?
- gap_identification: Did Maestro flag what it didn't know?
- confidence_calibration: Was Maestro's confidence appropriate?
- workspace_assembly_quality: Did Maestro build a useful workspace? (if applicable)
- experience_application: Did routing rules help? (if applicable)

Let the interaction tell you what matters. Don't force dimensions that don't apply.
"""


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
            BENCHMARK_EVALUATION_INSTRUCTIONS,
        ]
    ).strip()


def _format_interaction(interaction: InteractionPackage) -> str:
    if isinstance(interaction, dict):
        payload = interaction
    else:
        payload = asdict(interaction)
    return "Interaction package:\n" + json.dumps(payload, indent=2)


def _parse_learning_assessment(response_text: str) -> tuple[dict, dict, list]:
    """
    Parse Learning's structured assessment from its response.

    Returns:
        (assessment_dict, scores_dict, actions_list)
    """
    import re

    assessment = {}
    scores = {}
    actions: list[str] = []

    # Parse ASSESSMENT section
    assessment_match = re.search(
        r"ASSESSMENT:\s*(.+?)(?=\nSCORES:|$)",
        response_text,
        re.DOTALL | re.IGNORECASE,
    )
    if assessment_match:
        assessment["summary"] = assessment_match.group(1).strip()

    # Parse SCORES section - look for JSON object
    scores_match = re.search(
        r"SCORES:\s*\{([^}]+)\}",
        response_text,
        re.DOTALL | re.IGNORECASE,
    )
    if scores_match:
        try:
            scores_text = "{" + scores_match.group(1) + "}"
            # Clean up the JSON - handle trailing commas and comments
            scores_text = re.sub(r",\s*}", "}", scores_text)
            scores_text = re.sub(r"//[^\n]*", "", scores_text)
            parsed = json.loads(scores_text)
            if isinstance(parsed, dict):
                # Ensure all values are floats in 0-1 range
                for key, value in parsed.items():
                    try:
                        score = float(value)
                        if 0 <= score <= 1:
                            scores[key] = score
                    except (ValueError, TypeError):
                        pass
        except json.JSONDecodeError:
            # Try line-by-line parsing
            for line in scores_match.group(1).splitlines():
                line = line.strip().strip(",")
                if ":" in line:
                    parts = line.split(":", 1)
                    key = parts[0].strip().strip('"').strip("'")
                    try:
                        value = float(parts[1].strip().strip(","))
                        if 0 <= value <= 1:
                            scores[key] = value
                    except (ValueError, TypeError):
                        pass

    # Parse ACTIONS section
    actions_match = re.search(
        r"ACTIONS:\s*(.+?)(?=\n[A-Z]+:|$)",
        response_text,
        re.DOTALL | re.IGNORECASE,
    )
    if actions_match:
        actions_text = actions_match.group(1).strip()
        # Handle list format or comma-separated
        if actions_text.startswith("["):
            actions_text = actions_text.strip("[]")
        for item in re.split(r"[,\n]", actions_text):
            item = item.strip().strip("-").strip("*").strip()
            if item and item.lower() != "none":
                actions.append(item)

    return assessment, scores, actions


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


def _append_panel_text(current: str, incoming: str) -> str:
    if not incoming:
        return current
    return f"{current}\n{incoming}" if current else incoming


def _append_panel_to_turn(
    session: LiveSession,
    turn_number: int,
    panel: str,
    content: str,
) -> None:
    if not content:
        return
    for message in reversed(session.maestro_messages):
        if message.get("role") != "assistant":
            continue
        if message.get("turn_number") != turn_number:
            continue
        panels = message.setdefault(
            "panels",
            {"workspace_assembly": "", "learning": "", "knowledge_update": ""},
        )
        current = panels.get(panel, "")
        panels[panel] = _append_panel_text(current, content)
        session.dirty = True
        return


async def run_learning_turn(
    session: LiveSession,
    interaction: InteractionPackage,
    db: DBSession,
) -> AsyncIterator[dict[str, Any]]:
    turn_number = 0
    benchmark_id = None

    if isinstance(interaction, dict):
        try:
            turn_number = int(interaction.get("turn_number") or 0)
        except Exception:
            turn_number = 0
        benchmark_id = interaction.get("benchmark_id")
    else:
        turn_number = interaction.turn_number
        benchmark_id = interaction.benchmark_id

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

    # Phase 7: Track tool usage for benchmark updates
    experience_updates: list[dict[str, Any]] = []
    knowledge_edits: list[dict[str, Any]] = []
    full_response_text = ""

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
                    _append_panel_to_turn(session, turn_number, "learning", content)
                    yield _thinking_event("learning", content, turn_number)
            elif event_type == "tool_call":
                tool_calls.append(
                    {
                        "id": chunk.get("id") or str(uuid4()),
                        "name": chunk.get("name"),
                        "arguments": chunk.get("arguments") or {},
                        "thought_signature": chunk.get("thought_signature"),
                    }
                )
            elif event_type == "done":
                break

        full_response_text += iteration_text

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
                    # Track Experience updates
                    experience_updates.append({
                        "tool": call["name"],
                        "path": call["arguments"].get("path"),
                    })
                elif call["name"] in {"edit_pointer", "edit_page", "update_cross_references", "trigger_reground"}:
                    panel = "knowledge_update"
                    # Track Knowledge edits
                    knowledge_edits.append({
                        "tool": call["name"],
                        "target": call["arguments"].get("pointer_id") or call["arguments"].get("page_id"),
                        "field": call["arguments"].get("field"),
                    })

                if panel:
                    summary = _tool_summary(call["name"], call["arguments"], result)
                    _append_panel_to_turn(session, turn_number, panel, summary)
                    yield _thinking_event(panel, summary, turn_number)

                session.dirty = True

            continue

        if iteration_text:
            _append_panel_to_turn(session, turn_number, "learning", iteration_text)
            yield _thinking_event("learning", iteration_text, turn_number)

        session.learning_messages.append(
            {"role": "assistant", "content": iteration_text}
        )

        # Phase 7: Parse assessment and update benchmark
        if benchmark_id and settings.benchmark_enabled:
            assessment, scores, _ = _parse_learning_assessment(full_response_text)
            if assessment or scores:
                update_benchmark_learning(
                    benchmark_id=benchmark_id,
                    assessment=assessment,
                    scores=scores,
                    experience_updates=experience_updates if experience_updates else None,
                    knowledge_edits=knowledge_edits if knowledge_edits else None,
                    db=db,
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
