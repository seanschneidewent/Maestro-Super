"""Query agent for navigating construction plan graph with Claude."""

import json
import logging
from typing import Any, AsyncIterator

import anthropic
from sqlalchemy.orm import Session

from app.config import get_settings

logger = logging.getLogger(__name__)

# Tool definitions in Anthropic format
# Note: project_id is injected by execute_tool(), not exposed to Claude
TOOL_DEFINITIONS = [
    {
        "name": "search_pointers",
        "description": "Search for relevant pointers by keyword/semantic query. Use this to find starting points for investigation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "discipline": {
                    "type": "string",
                    "description": "Optional discipline filter (e.g., 'Electrical', 'Mechanical')",
                },
                "limit": {"type": "integer", "description": "Max results (default 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_pointer",
        "description": "Get full details of a specific pointer including its description, text content, and references to other pages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pointer_id": {"type": "string", "description": "Pointer UUID"}
            },
            "required": ["pointer_id"],
        },
    },
    {
        "name": "get_page_context",
        "description": "Get summary of a page and all pointers on it. Use to understand what's on a specific page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page UUID"}
            },
            "required": ["page_id"],
        },
    },
    {
        "name": "get_discipline_overview",
        "description": "Get high-level view of a discipline including all pages and cross-references to other disciplines.",
        "input_schema": {
            "type": "object",
            "properties": {
                "discipline_id": {"type": "string", "description": "Discipline UUID"}
            },
            "required": ["discipline_id"],
        },
    },
    {
        "name": "list_project_pages",
        "description": "List all pages in the project organized by discipline. Use to understand project structure.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_references_to_page",
        "description": "Find all pointers that reference a specific page (reverse lookup). Use to discover what points TO a page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string", "description": "Page UUID"}
            },
            "required": ["page_id"],
        },
    },
    {
        "name": "select_pages",
        "description": "Display specific pages in the plan viewer for the user to see. Use this when the user asks to see specific pages or when you want to show them relevant plan sheets. Pages will be displayed without any pointer highlighting.",
        "input_schema": {
            "type": "object",
            "properties": {
                "page_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of page UUIDs to display",
                }
            },
            "required": ["page_ids"],
        },
    },
    {
        "name": "select_pointers",
        "description": "Highlight specific pointers on the plan viewer to show the user which areas of the plans are relevant to their query. This also displays the pages containing those pointers. Use when you want to highlight specific details on the plans.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pointer_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of pointer UUIDs to highlight",
                }
            },
            "required": ["pointer_ids"],
        },
    },
]

AGENT_SYSTEM_PROMPT = """You are a construction plan analysis agent. You help superintendents find information across construction documents by navigating a graph of pages and details (pointers).

You have access to these tools:
- search_pointers: Find relevant starting points by keyword/semantic search
- get_pointer: Get full details of a specific pointer including references to other pages
- get_page_context: Get summary of a page and all pointers on it
- get_discipline_overview: Get high-level view of a discipline (architectural, structural, etc.)
- list_project_pages: See all pages in the project
- get_references_to_page: Find what points TO a specific page (reverse lookup)
- select_pages: Display specific pages in the plan viewer for the user to see
- select_pointers: Highlight specific pointers on pages to show the user relevant areas

STRATEGY:
1. Start by searching for relevant pointers or identifying which discipline likely contains the answer
2. Examine promising pointers in detail
3. When you find references to other pages, evaluate if they're relevant to the original query
4. Follow relevant references - keep traversing until you have enough information
5. If a reference exists but isn't relevant to the query, note it but don't follow it
6. Use select_pages to show relevant pages, or select_pointers to highlight specific details
7. Stop when you can comprehensively answer the question

DISPLAYING RESULTS:
- Use select_pages when you want to show the user specific plan sheets without highlighting
- Use select_pointers when you want to highlight specific details/areas on the plans
- Always call one of these before your final answer so the user can see the relevant plans

RESPONSE STYLE:
- Keep final answers to 2 sentences maximum
- Be direct and concise - superintendents are busy
- Don't list what a page "typically contains" - just confirm you found it

REASONING:
- Think through each step briefly
- Note when you have enough information to answer"""


async def execute_tool(
    db: Session,
    project_id: str,
    tool_name: str,
    tool_input: dict,
) -> dict:
    """Execute a tool and return JSON-serializable result."""
    from app.services.tools import TOOL_REGISTRY

    tool_fn = TOOL_REGISTRY.get(tool_name)
    if not tool_fn:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        # Inject project_id for tools that need it
        if tool_name == "search_pointers":
            result = await tool_fn(db, project_id=project_id, **tool_input)
        elif tool_name == "list_project_pages":
            result = await tool_fn(db, project_id=project_id)
        elif tool_name in ("select_pages", "select_pointers"):
            result = await tool_fn(db, **tool_input)
        else:
            result = await tool_fn(db, **tool_input)

        # Convert Pydantic model to dict
        if hasattr(result, "model_dump"):
            return result.model_dump(by_alias=True, mode="json")
        # search_pointers returns list[dict], not a Pydantic model
        return result if result else {"error": "Not found"}
    except Exception as e:
        logger.exception(f"Tool execution error for {tool_name}: {e}")
        return {"error": str(e)}


async def run_agent_query(
    db: Session,
    project_id: str,
    query: str,
) -> AsyncIterator[dict]:
    """
    Execute agent query with streaming events.

    Yields events:
    - {"type": "text", "content": "..."} - Claude's reasoning
    - {"type": "tool_call", "tool": "...", "input": {...}} - Tool being called
    - {"type": "tool_result", "tool": "...", "result": {...}} - Tool result
    - {"type": "done", "trace": [...], "usage": {...}} - Final event

    Args:
        db: Database session
        project_id: Project UUID (injected into tools that need it)
        query: User's question
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        yield {"type": "error", "message": "Anthropic API key not configured"}
        return

    # Use AsyncAnthropic for proper async streaming
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    messages: list[dict[str, Any]] = [{"role": "user", "content": query}]
    trace: list[dict] = []
    total_input_tokens = 0
    total_output_tokens = 0

    try:
        while True:
            # Stream response from Claude (async context manager)
            async with client.messages.stream(
                model="claude-sonnet-4-5-20250929",
                max_tokens=4096,
                system=AGENT_SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            ) as stream:
                # Stream text chunks as they arrive
                current_text = ""
                async for text in stream.text_stream:
                    yield {"type": "text", "content": text}
                    current_text += text

                # Get final message for tool uses and usage stats
                response = await stream.get_final_message()

            # Track token usage
            total_input_tokens += response.usage.input_tokens
            total_output_tokens += response.usage.output_tokens

            # Add accumulated text to trace
            if current_text:
                trace.append({"type": "reasoning", "content": current_text})

            # Process tool use blocks
            tool_uses = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_uses.append(block)
                    tool_name = block.name
                    tool_input = block.input

                    yield {"type": "tool_call", "tool": tool_name, "input": tool_input}
                    trace.append(
                        {"type": "tool_call", "tool": tool_name, "input": tool_input}
                    )

            # If no tool uses, we're done
            if not tool_uses:
                break

            # Execute tools and build tool results
            tool_results = []
            for block in tool_uses:
                result = await execute_tool(db, project_id, block.name, block.input)

                # Tool result content must be a JSON string
                result_json = json.dumps(result)

                yield {"type": "tool_result", "tool": block.name, "result": result}
                trace.append(
                    {"type": "tool_result", "tool": block.name, "result": result}
                )

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_json,  # String, not object
                    }
                )

            # Add assistant message and tool results for next iteration
            # Need to serialize content blocks for messages
            messages.append(
                {
                    "role": "assistant",
                    "content": [
                        block.model_dump() if hasattr(block, "model_dump") else block
                        for block in response.content
                    ],
                }
            )
            messages.append({"role": "user", "content": tool_results})

        # Final response with trace and usage
        yield {
            "type": "done",
            "trace": trace,
            "usage": {
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
            },
        }

    except anthropic.APIError as e:
        logger.exception(f"Anthropic API error: {e}")
        yield {"type": "error", "message": f"API error: {str(e)}"}
    except Exception as e:
        logger.exception(f"Agent error: {e}")
        yield {"type": "error", "message": str(e)}
