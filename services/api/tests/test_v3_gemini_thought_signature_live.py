"""Live Gemini integration test for thought_signature replay stability."""

from __future__ import annotations

import asyncio
import os

import pytest

from app.config import get_settings
from app.services.v3.providers import _gemini_messages, chat_completion


@pytest.mark.external
@pytest.mark.skipif(
    not (os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key),
    reason="GEMINI_API_KEY is required for external Gemini integration tests",
)
def test_gemini_thought_signature_roundtrip_live() -> None:
    async def _run() -> None:
        settings = get_settings()
        model = (
            settings.maestro_model
            if settings.maestro_model.startswith("gemini-")
            else "gemini-3-flash-preview"
        )

        tools = [
            {
                "name": "echo_tool",
                "description": "Echo the provided text",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            }
        ]

        system_prompt = (
            "You are a test assistant. You must call echo_tool exactly once before answering."
        )
        user_prompt = "Use the tool and then answer with a short confirmation."

        first_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        first_events: list[dict] = []
        async for event in chat_completion(first_messages, tools, model=model, stream=True):
            first_events.append(event)

        tool_call = next((event for event in first_events if event.get("type") == "tool_call"), None)
        if not tool_call:
            pytest.skip("Gemini did not emit a tool call in this run")

        thought_signature = tool_call.get("thought_signature")
        replay_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": tool_call["id"],
                        "name": tool_call["name"],
                        "arguments": tool_call.get("arguments") or {},
                        "thought_signature": thought_signature,
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "name": tool_call["name"],
                "content": {"ok": True, "echo": "tool completed"},
            },
        ]

        _, replay_contents = _gemini_messages(replay_messages)
        replay_model_content = next(
            (content for content in replay_contents if getattr(content, "role", None) == "model"),
            None,
        )
        assert replay_model_content is not None
        replay_part = replay_model_content.parts[0]
        assert replay_part.function_call is not None
        if thought_signature is not None:
            assert replay_part.thought_signature == thought_signature

        second_events: list[dict] = []
        async for event in chat_completion(replay_messages, tools, model=model, stream=True):
            second_events.append(event)

        assert any(event.get("type") == "done" for event in second_events)

    asyncio.run(_run())
