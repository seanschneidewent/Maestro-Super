"""Query agent for navigating construction plan graph with Kimi K2 via OpenRouter."""

import json
import logging
import re
from typing import Any, AsyncIterator

import openai
from sqlalchemy.orm import Session

from app.config import get_settings

logger = logging.getLogger(__name__)

# Pattern to filter out Kimi K2's native tool call tokens that sometimes leak through as text
KIMI_TOKEN_PATTERN = re.compile(
    r'<\|tool_call[s]?_[^>]+\|>|'  # <|tool_call_begin|>, <|tool_calls_section_begin|>, etc.
    r'<\|tool_call_argument_begin\|>|'
    r'functions\.[a-z_]+:\d+',  # functions.select_pages:2
    re.IGNORECASE
)


def filter_kimi_tokens(text: str) -> str:
    """Remove Kimi K2's native tool call tokens from text content."""
    if not text:
        return text
    # Remove the token patterns
    filtered = KIMI_TOKEN_PATTERN.sub('', text)
    # Clean up any resulting JSON fragments that got orphaned
    # (e.g., the argument JSON after removing the wrapper tokens)
    if filtered.strip().startswith('{') and '"page_ids"' in filtered:
        return ''  # This is a leaked tool call argument, drop it entirely
    return filtered


# Tool definitions in OpenAI format
# Note: project_id is injected by execute_tool(), not exposed to the model
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_pointers",
            "description": "Search for relevant pointers (detailed annotations on pages) by keyword/semantic query. Returns pointers with their page info. Use this to find specific details, callouts, or annotations.",
            "parameters": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "search_pages",
            "description": "Search for pages/sheets by name or content. Use this to find specific sheets (e.g., 'E-2.1', 'panel schedule') or pages containing certain content. Returns page names with context snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (matches page name or context)"},
                    "discipline": {
                        "type": "string",
                        "description": "Optional discipline filter (e.g., 'Electrical', 'Mechanical')",
                    },
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pointer",
            "description": "Get full details of a specific pointer including its description, text content, and references to other pages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pointer_id": {"type": "string", "description": "Pointer UUID"}
                },
                "required": ["pointer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page_context",
            "description": "Get summary of a page and all pointers on it. Use to understand what's on a specific page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "Page UUID"}
                },
                "required": ["page_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_discipline_overview",
            "description": "Get high-level view of a discipline including all pages and cross-references to other disciplines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "discipline_id": {"type": "string", "description": "Discipline UUID"}
                },
                "required": ["discipline_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_project_pages",
            "description": "List all pages in the project organized by discipline. Use to understand project structure.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_references_to_page",
            "description": "Find all pointers that reference a specific page (reverse lookup). Use to discover what points TO a page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string", "description": "Page UUID"}
                },
                "required": ["page_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_pages",
            "description": "Display specific pages in the plan viewer for the user to see. Use this when the user asks to see specific pages or when you want to show them relevant plan sheets. Pages will be displayed without any pointer highlighting.",
            "parameters": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "select_pointers",
            "description": "Highlight specific pointers on the plan viewer to show the user which areas of the plans are relevant to their query. This also displays the pages containing those pointers. Use when you want to highlight specific details on the plans.",
            "parameters": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "set_display_title",
            "description": "Set a short title summarizing what the user asked about. Call this ONCE before your final answer. The title should be a 2-4 word noun phrase describing the topic (e.g., 'Electrical Panels', 'Kitchen Equipment', 'Fire Sprinkler Layout').",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "A 2-4 word noun phrase summarizing the query topic",
                    }
                },
                "required": ["title"],
            },
        },
    },
]

AGENT_SYSTEM_PROMPT = """You are a construction plan analysis agent. You help superintendents find information across construction documents by navigating a graph of pages and details (pointers).

You have access to these tools:
- search_pointers: Find relevant pointers (annotations/details) by keyword/semantic search
- search_pages: Find pages/sheets by name or content (e.g., "E-2.1", "panel schedule")
- get_pointer: Get full details of a specific pointer including references to other pages
- get_page_context: Get summary of a page and all pointers on it
- get_discipline_overview: Get high-level view of a discipline (architectural, structural, etc.)
- list_project_pages: See all pages in the project
- get_references_to_page: Find what points TO a specific page (reverse lookup)
- select_pages: Display specific pages in the plan viewer for the user to see
- select_pointers: Highlight specific pointers on pages to show the user relevant areas
- set_display_title: Set a short title for this query (REQUIRED before final answer)

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
- PAGE ORDERING: Always order pages numerically by sheet number (e.g., E-2.1, E-2.2, E-2.3). If the user requests a specific order (e.g., "show me the detail first" or "start with the overview"), follow their preference instead.

BEFORE YOUR FINAL ANSWER:
- Call set_display_title with a 2-4 word noun phrase summarizing the topic
- Examples: "Electrical Panel Location", "Kitchen Equipment", "Grease Trap Details", "Fire Sprinkler Layout"
- This title describes WHAT the user asked about, not what you found

RESPONSE STYLE:
You're a helpful secondary superintendent - knowledgeable, casual, and to the point. Talk like a colleague, not a robot.

DO:
- Sound natural: "Got your kitchen equipment plans - K-201 is the overview, the other two are enlarged sections."
- Add useful context: "Panel schedule's on E-3.2, but you'll want E-3.1 too for the one-line diagram."
- Be brief: 1-2 sentences max. Superintendents are busy.

DON'T:
- Announce what you did: "I have displayed the pages" ❌
- Sound robotic: "The requested documents are now shown" ❌
- List things formally: "These are: K-212, K-201, K-211" ❌
- Repeat what the user asked for: "You asked about equipment floor plans and I found equipment floor plans" ❌

THINKING OUT LOUD (during tool calls only):
- Verbalize your reasoning BEFORE each tool call: "Let me check the kitchen sheets...", "Found a few options, looking at the first one..."
- Brief status updates help the user follow along

FINAL ANSWER (after all tools are done):
- Jump straight into your response - NO preamble, NO reasoning, NO "let me now..."
- Your final answer should start with the actual information, not with what you're about to do
- WRONG: "Good, I found the pages. Now let me give you a brief answer. K-201 is your overview..."
- RIGHT: "K-201 is your overview, with K-211 and K-212 showing the enlarged sections."
- The user sees your tool calls, so don't narrate what just happened"""


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
        if tool_name in ("search_pointers", "search_pages"):
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
    Execute agent query with streaming events using Kimi K2 via OpenRouter.

    Yields events:
    - {"type": "text", "content": "..."} - Model's reasoning
    - {"type": "tool_call", "tool": "...", "input": {...}} - Tool being called
    - {"type": "tool_result", "tool": "...", "result": {...}} - Tool result
    - {"type": "done", "trace": [...], "usage": {...}, "displayTitle": "..."} - Final event

    Args:
        db: Database session
        project_id: Project UUID (injected into tools that need it)
        query: User's question
    """
    settings = get_settings()
    if not settings.openrouter_api_key:
        yield {"type": "error", "message": "OpenRouter API key not configured"}
        return

    # Use OpenAI client with OpenRouter base URL
    client = openai.AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]
    trace: list[dict] = []
    total_input_tokens = 0
    total_output_tokens = 0
    display_title: str | None = None

    try:
        while True:
            # Stream response from Kimi K2 Thinking (with native reasoning)
            stream = await client.chat.completions.create(
                model="moonshotai/kimi-k2-thinking",
                max_tokens=4096,
                tools=TOOL_DEFINITIONS,
                messages=messages,
                stream=True,
            )

            # Collect streaming response
            current_text = ""
            current_reasoning = ""
            tool_calls_data: dict[int, dict] = {}  # index -> {id, name, arguments}

            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                if not choice:
                    continue

                delta = choice.delta

                # Stream native reasoning from Kimi K2 Thinking
                if hasattr(delta, 'model_extra') and delta.model_extra:
                    reasoning = delta.model_extra.get('reasoning')
                    if reasoning:
                        # Filter out any leaked tool call tokens
                        filtered_reasoning = filter_kimi_tokens(reasoning)
                        if filtered_reasoning:
                            yield {"type": "text", "content": filtered_reasoning}
                            current_reasoning += filtered_reasoning

                # Stream text content (final answer)
                if delta.content:
                    # Filter out any leaked tool call tokens
                    filtered_content = filter_kimi_tokens(delta.content)
                    if filtered_content:
                        yield {"type": "text", "content": filtered_content}
                        current_text += filtered_content

                # Accumulate tool calls (they come in chunks)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_data:
                            tool_calls_data[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name if tc.function and tc.function.name else "",
                                "arguments": "",
                            }
                        if tc.id:
                            tool_calls_data[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_data[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_data[idx]["arguments"] += tc.function.arguments

                # Track usage from final chunk
                if chunk.usage:
                    total_input_tokens += chunk.usage.prompt_tokens or 0
                    total_output_tokens += chunk.usage.completion_tokens or 0

            # Add accumulated reasoning and text to trace
            if current_reasoning:
                trace.append({"type": "reasoning", "content": current_reasoning})
            if current_text:
                trace.append({"type": "response", "content": current_text})

            # If no tool calls, we're done
            if not tool_calls_data:
                break

            # Process tool calls
            tool_calls_list = []
            for idx in sorted(tool_calls_data.keys()):
                tc_data = tool_calls_data[idx]
                tool_name = tc_data["name"]
                try:
                    tool_input = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                except json.JSONDecodeError:
                    tool_input = {}

                tool_calls_list.append({
                    "id": tc_data["id"],
                    "name": tool_name,
                    "input": tool_input,
                })

                yield {"type": "tool_call", "tool": tool_name, "input": tool_input}
                trace.append({"type": "tool_call", "tool": tool_name, "input": tool_input})

            # Execute tools and build results
            tool_results = []
            assistant_tool_calls = []

            for tc in tool_calls_list:
                tool_name = tc["name"]
                tool_input = tc["input"]
                tool_id = tc["id"]

                # Handle set_display_title specially - no DB access needed
                if tool_name == "set_display_title":
                    title = tool_input.get("title", "")
                    # Clean up the title - strip leading colons, quotes, and whitespace
                    # (Kimi K2 sometimes outputs `: "Title"` instead of just `Title`)
                    if title:
                        title = title.strip().lstrip(':').strip().strip('"').strip("'").strip()
                    display_title = title[:100] if title else None
                    result = {"success": True, "title": display_title}
                    logger.info(f"Display title set to: {display_title}")
                else:
                    result = await execute_tool(db, project_id, tool_name, tool_input)

                result_json = json.dumps(result)

                yield {"type": "tool_result", "tool": tool_name, "result": result}
                trace.append({"type": "tool_result", "tool": tool_name, "result": result})

                # Build assistant tool_calls for message history
                assistant_tool_calls.append({
                    "id": tool_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_input),
                    },
                })

                # Build tool result message
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": result_json,
                })

            # Add assistant message with tool calls
            assistant_message: dict[str, Any] = {"role": "assistant"}
            # Combine reasoning and content for message history
            combined_content = current_reasoning + current_text
            if combined_content:
                assistant_message["content"] = combined_content
            if assistant_tool_calls:
                assistant_message["tool_calls"] = assistant_tool_calls
            messages.append(assistant_message)

            # Add tool results
            messages.extend(tool_results)

        # Final response with trace, usage, and display title
        yield {
            "type": "done",
            "trace": trace,
            "usage": {
                "inputTokens": total_input_tokens,
                "outputTokens": total_output_tokens,
            },
            "displayTitle": display_title,
        }

    except openai.APIError as e:
        logger.exception(f"OpenRouter API error: {e}")
        yield {"type": "error", "message": f"API error: {str(e)}"}
    except Exception as e:
        logger.exception(f"Agent error: {e}")
        yield {"type": "error", "message": str(e)}
