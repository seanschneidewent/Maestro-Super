"""Debug trace writer for local development.

Writes a summarized query trace to services/api/debug/last-query.json
after each query completes. Rotates last 5 traces.

Only called when DEV_USER_ID is set (local dev mode).
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEBUG_DIR = Path(__file__).resolve().parent.parent.parent / "debug"
MAX_TRACE_FILES = 5


def _truncate_middle(text: str, max_chars: int = 1000) -> str:
    """Keep first half and last half if text exceeds max_chars."""
    if not text or len(text) <= max_chars:
        return text or ""
    half = max_chars // 2
    return (
        text[:half]
        + f"\n... [{len(text) - max_chars} chars truncated] ...\n"
        + text[-half:]
    )


def _strip_base64(obj: Any) -> Any:
    """Recursively strip base64 image data from dicts/lists."""
    if isinstance(obj, str):
        if obj.startswith("data:image/"):
            return f"<base64 {len(obj)} chars>"
        if len(obj) > 200 and re.match(r"^[A-Za-z0-9+/=\s]+$", obj):
            return f"<base64 {len(obj)} chars>"
        return obj
    if isinstance(obj, dict):
        return {k: _strip_base64(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_base64(item) for item in obj]
    return obj


def _summarize_trace_step(step: dict) -> dict:
    """Summarize a single trace step for debug output."""
    step_type = step.get("type", "unknown")
    summarized: dict[str, Any] = {"type": step_type}

    if step_type == "reasoning":
        summarized["content"] = _truncate_middle(step.get("content", ""))
    elif step_type == "thinking":
        summarized["content"] = _truncate_middle(step.get("content", ""), 1000)
    elif step_type == "tool_call":
        summarized["tool"] = step.get("tool")
        summarized["input"] = _strip_base64(step.get("input", {}))
    elif step_type == "tool_result":
        summarized["tool"] = step.get("tool")
        summarized["result"] = _strip_base64(step.get("result", {}))
    else:
        for k, v in step.items():
            if k == "type":
                continue
            if isinstance(v, str):
                summarized[k] = _truncate_middle(v, 500)
            else:
                summarized[k] = _strip_base64(v)

    return summarized


def write_debug_trace(
    query_text: str,
    mode: str,
    trace: list[dict],
    usage: dict,
    response_text: str,
    display_title: str | None,
    pages_data: list[dict],
    query_id: str,
    project_id: str,
) -> None:
    """Write a compact debug summary to debug/last-query.json.

    Rotates previous files: last-query.json -> last-query-1.json -> ... -> last-query-5.json
    """
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)

        # Rotate existing files
        for i in range(MAX_TRACE_FILES, 1, -1):
            src = DEBUG_DIR / f"last-query-{i - 1}.json"
            dst = DEBUG_DIR / f"last-query-{i}.json"
            if src.exists():
                dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

        # Move current to last-query-1.json
        current = DEBUG_DIR / "last-query.json"
        if current.exists():
            (DEBUG_DIR / "last-query-1.json").write_text(
                current.read_text(encoding="utf-8"), encoding="utf-8"
            )

        # Summarize trace
        summarized_trace = [_summarize_trace_step(s) for s in (trace or [])]

        # Extract annotated image info (count + sizes, no data)
        annotated_images_info = []
        for step in trace or []:
            if step.get("type") == "tool_result":
                result = step.get("result", {})
                if isinstance(result, dict):
                    for img in result.get("annotated_images", []):
                        if isinstance(img, dict):
                            data = img.get("data", "")
                            annotated_images_info.append({
                                "label": img.get("label", "unlabeled"),
                                "bytes": len(data) if isinstance(data, str) else 0,
                            })

        debug_summary = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query_id": query_id,
            "project_id": project_id,
            "query_text": query_text,
            "mode": mode,
            "display_title": display_title,
            "usage": usage,
            "pages_selected": [
                {"page_id": p.get("page_id"), "pointers": p.get("pointers", [])}
                for p in (pages_data or [])
            ],
            "annotated_images": {
                "count": len(annotated_images_info),
                "details": annotated_images_info,
            },
            "response_text": response_text or "",
            "trace_steps": len(trace or []),
            "trace": summarized_trace,
        }

        current.write_text(
            json.dumps(debug_summary, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info(f"Debug trace written to {current}")

    except Exception as e:
        logger.warning(f"Failed to write debug trace: {e}")
