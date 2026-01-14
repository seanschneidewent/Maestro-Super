"""Query agent for navigating construction plan graph with Grok 4.1 Fast via OpenRouter."""

import json
import logging
from typing import Any, AsyncIterator

import openai
from sqlalchemy.orm import Session

from app.config import get_settings

logger = logging.getLogger(__name__)


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
            "description": "Set titles for this chat and the overall conversation. Call this ONCE before your final answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chat_title": {
                        "type": "string",
                        "description": "2-4 word noun phrase for THIS query (e.g., 'Electrical Panels', 'Kitchen Equipment')",
                    },
                    "conversation_title": {
                        "type": "string",
                        "description": "2-6 word phrase summarizing the ENTIRE conversation so far",
                    }
                },
                "required": ["chat_title", "conversation_title"],
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

STRATEGY - SEARCH RESULTS ARE PRE-FETCHED:

Search results for both pages and pointers have ALREADY been fetched and are provided below.
DO NOT call search_pages or search_pointers - the results are already here.

YOUR JOB:
1. Review the pre-fetched results below
2. Decide which pages/pointers to display
3. Call select_pages and/or select_pointers with the relevant IDs
4. Call set_display_title
5. Write a brief response

WHEN TO USE ADDITIONAL TOOLS (escape hatch):
- If the pre-fetched results are empty or unhelpful, you MAY call search_pages/search_pointers with different terms
- If you need detailed pointer info, you MAY call get_pointer or get_page_context
- But for most queries, the pre-fetched results are sufficient - just select and respond

EFFICIENCY IS CRITICAL:
- Most queries should complete in ONE tool call batch: select_pages + set_display_title
- Superintendents are on job sites. Every second counts.

DISPLAYING RESULTS - SHOW ALL RELEVANT PAGES:
- Your goal is to show the user ALL pages relevant to their question, not just pages with pointers.
- Use select_pointers for pages where you found specific relevant pointers to highlight
- Use select_pages for pages that are relevant but don't have specific pointers to highlight
- You CAN call BOTH tools in the same query! For example: if 2 pages have relevant pointers and 3 more pages are relevant but have no pointers, call select_pointers for the 2 AND select_pages for the 3.
- IMPORTANT: Pages without pointers can still be highly relevant. Don't skip them just because there's nothing to highlight.
- PAGE ORDERING: Order pages numerically by sheet number (e.g., E-2.1, E-2.2, E-2.3). If the user requests a specific order, follow their preference instead.
- Always call at least one of these tools before your final answer so the user can see the relevant plans.

BEFORE YOUR FINAL ANSWER:
- Call set_display_title with:
  - chat_title: 2-4 word noun phrase for THIS question (e.g., "Electrical Panels", "Kitchen Equipment")
  - conversation_title: 2-6 word phrase summarizing ALL topics discussed in this conversation
    - First query: same as chat_title
    - Follow-ups: combine themes (e.g., "Kitchen & Electrical Plans", "Panel Details and Locations")

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
- The user sees your tool calls, so don't narrate what just happened

CONVERSATION CONTEXT:
If there are previous messages in this conversation, use that context to:
- Understand pronouns and references (e.g., "those panels", "the second one", "what about floor 2?")
- Avoid repeating searches you've already done unless the user asks for fresh results
- Build on previous findings rather than starting from scratch
- Remember what pages/pointers you've already shown"""


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
        # Use `is not None` to allow empty lists [] as valid results
        return result if result is not None else {"error": "Not found"}
    except Exception as e:
        logger.exception(f"Tool execution error for {tool_name}: {e}")
        return {"error": str(e)}


async def run_agent_query(
    db: Session,
    project_id: str,
    query: str,
    history_messages: list[dict[str, Any]] | None = None,
    viewing_context: dict[str, Any] | None = None,
) -> AsyncIterator[dict]:
    """
    Execute agent query with streaming events using Grok 4.1 Fast via OpenRouter.

    Yields events:
    - {"type": "text", "content": "..."} - Model's reasoning
    - {"type": "tool_call", "tool": "...", "input": {...}} - Tool being called
    - {"type": "tool_result", "tool": "...", "result": {...}} - Tool result
    - {"type": "done", "trace": [...], "usage": {...}, "displayTitle": "..."} - Final event

    Args:
        db: Database session
        project_id: Project UUID (injected into tools that need it)
        query: User's question
        history_messages: Optional list of previous messages in conversation
        viewing_context: Optional dict with page_id, page_name, discipline_name if user is viewing a page
    """
    from app.services.tools import search_pages, search_pointers, list_project_pages

    settings = get_settings()
    if not settings.openrouter_api_key:
        yield {"type": "error", "message": "OpenRouter API key not configured"}
        return

    # Use OpenAI client with OpenRouter base URL
    client = openai.AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    # PRE-FETCH: Run searches + project structure before LLM call to eliminate roundtrips
    # This runs in parallel using asyncio
    import asyncio

    # Yield pre-fetch status
    yield {"type": "tool_call", "tool": "list_project_pages", "input": {}}
    yield {"type": "tool_call", "tool": "search_pages", "input": {"query": query}}
    yield {"type": "tool_call", "tool": "search_pointers", "input": {"query": query}}

    # Run all three in parallel
    project_structure, page_results, pointer_results = await asyncio.gather(
        list_project_pages(db, project_id=project_id),
        search_pages(db, query=query, project_id=project_id, limit=10),
        search_pointers(db, query=query, project_id=project_id, limit=10),
    )

    # Convert project structure to dict for JSON serialization
    project_structure_dict = project_structure.model_dump() if project_structure else None

    # Yield pre-fetch results
    yield {"type": "tool_result", "tool": "list_project_pages", "result": project_structure_dict}
    yield {"type": "tool_result", "tool": "search_pages", "result": page_results}
    yield {"type": "tool_result", "tool": "search_pointers", "result": pointer_results}

    # Build pre-fetch context to inject into prompt
    prefetch_context = f"""

PRE-FETCHED DATA (already executed - do NOT call these tools again):

PROJECT STRUCTURE (all disciplines and pages):
{json.dumps(project_structure_dict, indent=2)}

SEARCH RESULTS for "{query}":

Pages matching query:
{json.dumps(page_results, indent=2)}

Pointers matching query:
{json.dumps(pointer_results, indent=2)}

Use these results directly. Call select_pages/select_pointers with the relevant IDs from above.
If the search results are empty but you can identify relevant pages from the PROJECT STRUCTURE, use those page_ids."""

    system_content = AGENT_SYSTEM_PROMPT + prefetch_context

    # Add viewing context if user is currently viewing a specific page
    if viewing_context:
        page_name = viewing_context.get("page_name", "unknown page")
        discipline = viewing_context.get("discipline_name")
        if discipline:
            system_content += f"""

CURRENT VIEW: The user is currently viewing page {page_name} from {discipline}. This may or may not be relevant to their question - only reference it if it naturally relates to what they're asking."""
        else:
            system_content += f"""

CURRENT VIEW: The user is currently viewing page {page_name}. This may or may not be relevant to their question - only reference it if it naturally relates to what they're asking."""

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_content},
    ]

    # Add history messages if this is a multi-turn conversation
    if history_messages:
        messages.extend(history_messages)
        logger.info(f"Added {len(history_messages)} history messages to conversation")

    # Add current user query
    messages.append({"role": "user", "content": query})

    # Initialize trace with pre-fetch calls
    trace: list[dict] = [
        {"type": "tool_call", "tool": "list_project_pages", "input": {}},
        {"type": "tool_result", "tool": "list_project_pages", "result": project_structure_dict},
        {"type": "tool_call", "tool": "search_pages", "input": {"query": query}},
        {"type": "tool_result", "tool": "search_pages", "result": page_results},
        {"type": "tool_call", "tool": "search_pointers", "input": {"query": query}},
        {"type": "tool_result", "tool": "search_pointers", "result": pointer_results},
    ]
    total_input_tokens = 0
    total_output_tokens = 0
    display_title: str | None = None
    conversation_title: str | None = None

    try:
        while True:
            stream = await client.chat.completions.create(
                model="x-ai/grok-4.1-fast",
                max_tokens=4096,
                tools=TOOL_DEFINITIONS,
                messages=messages,
                stream=True,
                temperature=0,  # More consistent results
            )

            # Collect streaming response
            current_text = ""
            tool_calls_data: dict[int, dict] = {}  # index -> {id, name, arguments}

            async for chunk in stream:
                choice = chunk.choices[0] if chunk.choices else None
                if not choice:
                    continue

                delta = choice.delta

                # Stream text content
                if delta.content:
                    yield {"type": "text", "content": delta.content}
                    current_text += delta.content

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

            # Add accumulated text to trace
            if current_text:
                trace.append({"type": "reasoning", "content": current_text})

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
                    chat_title = tool_input.get("chat_title", "")
                    conv_title = tool_input.get("conversation_title", "")
                    # Clean up titles - strip leading colons, quotes, and whitespace
                    if chat_title:
                        chat_title = chat_title.strip().lstrip(':').strip().strip('"').strip("'").strip()
                    if conv_title:
                        conv_title = conv_title.strip().lstrip(':').strip().strip('"').strip("'").strip()
                    display_title = chat_title[:100] if chat_title else None
                    conversation_title = conv_title[:200] if conv_title else display_title
                    result = {"success": True, "chat_title": display_title, "conversation_title": conversation_title}
                    logger.info(f"Titles set - chat: {display_title}, conversation: {conversation_title}")
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
            if current_text:
                assistant_message["content"] = current_text
            if assistant_tool_calls:
                assistant_message["tool_calls"] = assistant_tool_calls
            messages.append(assistant_message)

            # Add tool results
            messages.extend(tool_results)

        # Final response with trace, usage, and titles
        yield {
            "type": "done",
            "trace": trace,
            "usage": {
                "inputTokens": total_input_tokens,
                "outputTokens": total_output_tokens,
            },
            "displayTitle": display_title,
            "conversationTitle": conversation_title,
        }

    except openai.APIError as e:
        logger.exception(f"OpenRouter API error: {e}")
        yield {"type": "error", "message": f"API error: {str(e)}"}
    except Exception as e:
        logger.exception(f"Agent error: {e}")
        yield {"type": "error", "message": str(e)}
