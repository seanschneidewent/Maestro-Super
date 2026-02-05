"""
Pass 2 Pointer enrichment agent.

Takes a cropped Pointer image + sheet reflection context and produces
a rich markdown description, structured cross-references, and embedding text.

Uses Gemini with vision + code execution (same pattern as Brain Mode Pass 1).
"""

import logging
import time
from dataclasses import dataclass

from google import genai
from google.genai import types

from app.config import get_settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────

@dataclass
class EnrichmentInput:
    pointer_id: str
    cropped_image_bytes: bytes
    sheet_reflection: str
    page_name: str
    discipline_name: str
    pointer_title: str


@dataclass
class EnrichmentOutput:
    rich_description: str       # Complete markdown extraction
    cross_references: list[str] # ["S-101", "E-201", "Detail 4/A3.01"]
    embedding_text: str         # Text to generate embedding from


# ─────────────────────────────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────────────────────────────

PASS2_ENRICHMENT_PROMPT = """You are analyzing a CROPPED REGION from a construction drawing. This region was identified by a previous analysis pass. Your job is to extract EVERY piece of information visible in this crop.

## CONTEXT
This crop comes from sheet **{page_name}** in the **{discipline_name}** discipline.
The previous analysis identified this region as: **{pointer_title}**

### Sheet-Level Understanding (from Pass 1)
{sheet_reflection}

## YOUR TASK

Read this cropped image EXHAUSTIVELY. Extract everything you can see:

### 1. ALL TEXT
- Every piece of text visible, verbatim where possible
- Every dimension with units (e.g., "4'-6\"", "1200mm", "3/4\"")
- Every specification callout (e.g., "Type X GWB", "R-19 insulation", "#4 rebar @ 12\" O.C.")
- Every note, annotation, or label
- Every item number or tag

### 2. TABLE/SCHEDULE CONTENTS (if applicable)
If this region contains a table or schedule:
- Extract every row and column
- Preserve the structure as a markdown table
- Include all header labels and cell values

### 3. CROSS-REFERENCES
List every reference to other sheets, details, or specs:
- "See Detail 3/A401" → "Detail 3/A401"
- "Refer to sheet S-101" → "S-101"
- Section cut symbols pointing elsewhere
- Tag references to schedules on other sheets
- Specification section references (e.g., "Section 09 21 16")

### 4. VISUAL ELEMENTS
- Describe what the drawing shows (construction assembly, layout, connection, etc.)
- Note materials indicated by hatching or symbols
- Note any leader lines pointing to specific items
- Flag anything partially visible or cut off at the crop boundary

### 5. AMBIGUITIES
Note anything that is:
- Partially visible (cut off at crop boundary)
- Hard to read (small text, overlapping elements)
- Potentially incorrect or unusual

## OUTPUT FORMAT

Return your findings as structured markdown. Use this format:

```
# [Region Title]

## Description
[What this region shows — one clear paragraph]

## Extracted Content
[All text, dimensions, specs, notes — organized logically]

## Table Contents
[If applicable — markdown table]

## Cross-References
- [Reference 1]
- [Reference 2]

## Notes
[Any ambiguities, partial visibility, or other observations]
```

Be EXHAUSTIVE. If you can see it, extract it. Every dimension, every note, every spec callout matters.
Do NOT return JSON. Return clean markdown only."""


# ─────────────────────────────────────────────────────────────────────
# Cross-reference extraction (post-processing)
# ─────────────────────────────────────────────────────────────────────

def _extract_cross_references(markdown: str) -> list[str]:
    """
    Pull structured cross-references from the markdown output.

    Looks for the ## Cross-References section and extracts list items.
    Falls back to regex matching common patterns if section not found.
    """
    import re

    refs: list[str] = []

    # Try to find the Cross-References section
    cr_match = re.search(
        r"## Cross-References\s*\n(.*?)(?=\n## |\Z)",
        markdown,
        re.DOTALL,
    )
    if cr_match:
        section = cr_match.group(1)
        for line in section.strip().split("\n"):
            line = line.strip().lstrip("- ").strip()
            if line and line.lower() not in ("none", "n/a", "none found"):
                refs.append(line)

    # Also scan full text for common reference patterns
    patterns = [
        r"(?:Detail|DET\.?)\s+(\d+/[A-Z]\d+[\.\d]*)",    # Detail 3/A401
        r"(?:Sheet|SHT\.?)\s+([A-Z]-?\d+[\.\d]*)",         # Sheet S-101
        r"(?:See|Refer to)\s+([A-Z]-?\d+[\.\d]*)",          # See E-201
        r"\b([A-Z]\d+\.\d{2})\b",                           # A2.01 style sheet refs
        r"(?:Section)\s+(\d{2}\s+\d{2}\s+\d{2})",           # Section 09 21 16
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, markdown, re.IGNORECASE):
            ref = match.group(1).strip()
            if ref not in refs:
                refs.append(ref)

    return refs


# ─────────────────────────────────────────────────────────────────────
# Main enrichment function
# ─────────────────────────────────────────────────────────────────────

def _get_gemini_client() -> genai.Client:
    """Get Gemini client for Pass 2."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise ValueError("Gemini API key must be configured")
    return genai.Client(api_key=settings.gemini_api_key)


async def enrich_pointer(input: EnrichmentInput) -> EnrichmentOutput:
    """
    Enrich a single Pointer with Gemini vision analysis.

    Sends the cropped image to Gemini along with sheet reflection context.
    Returns rich markdown description, cross-references, and embedding text.

    Uses vision + code execution + high thinking (same as Brain Mode Pass 1).
    """
    import asyncio

    start_time = time.time()
    settings = get_settings()

    prompt = PASS2_ENRICHMENT_PROMPT.format(
        page_name=input.page_name,
        discipline_name=input.discipline_name,
        pointer_title=input.pointer_title,
        sheet_reflection=input.sheet_reflection or "(No sheet reflection available)",
    )

    config_kwargs: dict = {
        "temperature": 0,
        "media_resolution": "media_resolution_high",
        "thinking_config": types.ThinkingConfig(thinking_level="high"),
    }

    # Enable code execution for agentic analysis
    try:
        code_exec_tool = types.Tool(code_execution=types.ToolCodeExecution)
    except Exception:
        code_exec_tool = types.Tool(code_execution=types.ToolCodeExecution())
    config_kwargs["tools"] = [code_exec_tool]

    def _call_gemini() -> str:
        client = _get_gemini_client()
        response = client.models.generate_content(
            model=settings.pass2_model,
            contents=[
                types.Content(
                    parts=[
                        types.Part.from_bytes(
                            data=input.cropped_image_bytes,
                            mime_type="image/png",
                        ),
                        types.Part.from_text(text=prompt),
                    ]
                )
            ],
            config=types.GenerateContentConfig(**config_kwargs),
        )

        # Extract text, skip thinking parts
        response_text = ""
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            content = getattr(candidates[0], "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                if getattr(part, "thought", False):
                    continue
                text = getattr(part, "text", None)
                if text:
                    response_text += text
        if not response_text:
            response_text = getattr(response, "text", "") or ""

        return response_text

    # Run sync Gemini call in thread pool
    rich_description = await asyncio.to_thread(_call_gemini)

    if not rich_description or not rich_description.strip():
        raise ValueError(f"Empty response from Gemini for pointer {input.pointer_id}")

    # Extract structured cross-references from the markdown
    cross_references = _extract_cross_references(rich_description)

    # Build embedding text: title + full description for maximum semantic coverage
    embedding_text = f"{input.pointer_title}\n{rich_description}"

    timing_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "Pass 2 enrichment complete for pointer %s (%s) in %sms — %d cross-refs found",
        input.pointer_id,
        input.pointer_title[:50],
        timing_ms,
        len(cross_references),
    )

    return EnrichmentOutput(
        rich_description=rich_description,
        cross_references=cross_references,
        embedding_text=embedding_text,
    )
