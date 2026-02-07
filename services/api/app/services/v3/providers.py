"""Model provider abstraction for Maestro V3."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import anthropic
from google import genai
from google.genai import types

from app.config import get_settings

logger = logging.getLogger(__name__)


async def chat_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    model: str,
    stream: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    """Route chat completion to the correct provider and normalize stream events."""
    model = (model or "").strip()
    if model.startswith("claude-"):
        async for event in _anthropic_chat_completion(messages, tools or [], model, stream=stream):
            yield event
        return
    if model.startswith("gemini-"):
        async for event in _gemini_chat_completion(messages, tools or [], model, stream=stream):
            yield event
        return
    if model.startswith("gpt-"):
        raise NotImplementedError("OpenAI provider not yet implemented for Maestro V3")
    if model.startswith("grok-"):
        raise NotImplementedError("xAI provider not yet implemented for Maestro V3")
    raise ValueError(f"Unsupported model prefix: {model}")


# ---------------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------------

def _anthropic_client() -> anthropic.AsyncAnthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise ValueError("Anthropic API key must be configured")
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


def _split_system_message(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system_prompt = ""
    remaining: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") == "system":
            system_prompt = str(msg.get("content") or "")
        else:
            remaining.append(msg)
    return system_prompt, remaining


def _anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tool in tools:
        out.append(
            {
                "name": tool.get("name"),
                "description": tool.get("description"),
                "input_schema": tool.get("parameters") or {},
            }
        )
    return out


def _anthropic_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        if role == "user":
            converted.append({"role": "user", "content": msg.get("content", "")})
        elif role == "assistant":
            blocks: list[dict[str, Any]] = []
            content = msg.get("content")
            if content:
                blocks.append({"type": "text", "text": str(content)})
            tool_calls = msg.get("tool_calls") or []
            for call in tool_calls:
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call.get("id") or str(uuid4()),
                        "name": call.get("name"),
                        "input": call.get("arguments") or {},
                    }
                )
            if blocks:
                converted.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id") or msg.get("id") or str(uuid4())
            tool_name = msg.get("name") or "tool"
            content = msg.get("content")
            if isinstance(content, (dict, list)):
                content_text = json.dumps(content)
            else:
                content_text = str(content or "")
            converted.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_call_id,
                            "content": content_text,
                        }
                    ],
                }
            )
        else:
            # Ignore unknown roles
            continue
    return converted


async def _anthropic_chat_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str,
    stream: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    client = _anthropic_client()
    system_prompt, remaining = _split_system_message(messages)
    payload_messages = _anthropic_messages(remaining)

    response = await client.messages.create(
        model=model,
        max_tokens=2048,
        system=system_prompt or None,
        messages=payload_messages,
        tools=_anthropic_tools(tools) if tools else None,
        temperature=0.2,
    )

    text_chunks: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in response.content or []:
        block_type = getattr(block, "type", None) or block.get("type") if isinstance(block, dict) else None
        if block_type == "text":
            text = getattr(block, "text", None) or (block.get("text") if isinstance(block, dict) else "")
            if text:
                text_chunks.append(str(text))
        elif block_type == "tool_use":
            tool_calls.append(
                {
                    "id": getattr(block, "id", None) or (block.get("id") if isinstance(block, dict) else str(uuid4())),
                    "name": getattr(block, "name", None) or (block.get("name") if isinstance(block, dict) else ""),
                    "arguments": getattr(block, "input", None) or (block.get("input") if isinstance(block, dict) else {}),
                }
            )

    for call in tool_calls:
        yield {
            "type": "tool_call",
            "id": call["id"],
            "name": call["name"],
            "arguments": call["arguments"],
            "thought_signature": call.get("thought_signature"),
        }

    if text_chunks:
        full_text = "".join(text_chunks)
        if stream:
            for chunk in _chunk_text(full_text):
                yield {"type": "token", "content": chunk}
        else:
            yield {"type": "token", "content": full_text}

    yield {"type": "done"}


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

def _gemini_client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ValueError("Gemini API key must be configured")
    return genai.Client(api_key=settings.gemini_api_key)


def _gemini_tools(tools: list[dict[str, Any]]) -> list[types.Tool]:
    if not tools:
        return []
    declarations: list[types.FunctionDeclaration] = []
    for tool in tools:
        declarations.append(
            types.FunctionDeclaration(
                name=tool.get("name"),
                description=tool.get("description"),
                parametersJsonSchema=tool.get("parameters") or {},
            )
        )
    return [types.Tool(functionDeclarations=declarations)]


def _gemini_messages(messages: list[dict[str, Any]]) -> tuple[str, list[types.Content]]:
    system_prompt = ""
    contents: list[types.Content] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            system_prompt = str(msg.get("content") or "")
            continue
        if role == "user":
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=str(msg.get("content") or ""))],
                )
            )
        elif role == "assistant":
            parts: list[types.Part] = []
            content = msg.get("content")
            if content:
                parts.append(types.Part.from_text(text=str(content)))
            tool_calls = msg.get("tool_calls") or []
            for call in tool_calls:
                function_call = types.FunctionCall(
                    id=str(call.get("id")) if call.get("id") else None,
                    name=str(call.get("name") or ""),
                    args=call.get("arguments") or {},
                )
                thought_signature = call.get("thought_signature")
                if isinstance(thought_signature, str):
                    thought_signature = thought_signature.encode("utf-8")
                if not isinstance(thought_signature, (bytes, bytearray)):
                    thought_signature = None
                parts.append(
                    types.Part(
                        function_call=function_call,
                        thought_signature=bytes(thought_signature) if thought_signature else None,
                    )
                )
            if parts:
                contents.append(types.Content(role="model", parts=parts))
        elif role == "tool":
            tool_name = msg.get("name") or "tool"
            content = msg.get("content")
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    parsed = {"content": content}
            elif isinstance(content, (dict, list)):
                parsed = content
            else:
                parsed = {"content": str(content or "")}
            response_payload = parsed if isinstance(parsed, dict) else {"results": parsed}
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            name=str(tool_name),
                            response=response_payload,
                        )
                    ],
                )
            )
    return system_prompt, contents


async def _gemini_chat_completion(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str,
    stream: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    client = _gemini_client()
    system_prompt, contents = _gemini_messages(messages)

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt or None,
            tools=_gemini_tools(tools) if tools else None,
            temperature=0.2,
        ),
    )

    text_chunks: list[str] = []
    tool_calls: list[dict[str, Any]] = []

    candidates = getattr(response, "candidates", None) or []
    if candidates:
        content = getattr(candidates[0], "content", None)
        if content:
            for part in getattr(content, "parts", []) or []:
                if part.function_call:
                    tool_calls.append(
                        {
                            "id": part.function_call.id or str(uuid4()),
                            "name": part.function_call.name,
                            "arguments": part.function_call.args or {},
                            "thought_signature": part.thought_signature,
                        }
                    )
                if part.text:
                    text_chunks.append(part.text)
                if getattr(part, "thought", False):
                    if part.text:
                        yield {"type": "thinking", "content": part.text}

    for call in tool_calls:
        yield {
            "type": "tool_call",
            "id": call["id"],
            "name": call["name"],
            "arguments": call["arguments"],
            "thought_signature": call.get("thought_signature"),
        }

    if text_chunks:
        full_text = "".join(text_chunks)
        if stream:
            for chunk in _chunk_text(full_text):
                yield {"type": "token", "content": chunk}
        else:
            yield {"type": "token", "content": full_text}

    yield {"type": "done"}


def _chunk_text(text: str, size: int = 24) -> list[str]:
    if not text:
        return []
    return [text[i : i + size] for i in range(0, len(text), size)]
