"""
Shared parsing utilities for extracting and coercing data.

These utilities are used across brain_mode_processor, query_vision, and gemini modules.
"""

from __future__ import annotations

import json
from typing import Any


def coerce_int(value: Any, default: int = 0) -> int:
    """
    Safely coerce a value to int, rounding floats.

    Args:
        value: Any value to convert
        default: Default value if conversion fails

    Returns:
        Integer value or default
    """
    try:
        return int(round(float(value)))
    except Exception:
        return default


def extract_json_response(text: str) -> dict:
    """
    Best-effort JSON extraction from LLM responses.

    Handles raw JSON, markdown code blocks, and text with embedded JSON.

    Args:
        text: Raw response text from LLM

    Returns:
        Parsed dictionary

    Raises:
        ValueError: If no valid JSON can be extracted
    """
    if not text:
        raise ValueError("Empty response from Gemini")

    # Try direct parsing first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract first JSON object substring
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not extract valid JSON from response")
