"""Tests for the Agentic Vision Brain Mode pipeline."""

from __future__ import annotations

import asyncio
import sys
from io import BytesIO
from types import SimpleNamespace

from PIL import Image

# Optional dependency used by other provider modules during package import.
sys.modules.setdefault("voyageai", SimpleNamespace(Client=lambda *args, **kwargs: None))
sys.modules.setdefault("supabase", SimpleNamespace(create_client=lambda *args, **kwargs: None))
sys.modules.setdefault("pdf2image", SimpleNamespace(convert_from_bytes=lambda *args, **kwargs: []))

from app.services.core.brain_mode_processor import process_page_brain_mode
from app.services.providers.gemini import (
    _extract_json_response,
    analyze_sheet_brain_mode,
    normalize_bbox,
    process_brain_mode_result,
    validate_brain_mode_response,
)


def _make_png(width: int = 1200, height: int = 800) -> bytes:
    image = Image.new("RGB", (width, height), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_extract_json_response_from_markdown_code_block() -> None:
    raw = """```json
{"regions": [], "sheet_info": {}, "index": {}}
```"""
    parsed = _extract_json_response(raw)
    assert parsed["regions"] == []
    assert parsed["sheet_info"] == {}
    assert parsed["index"] == {}


def test_validate_brain_mode_response_requires_keys() -> None:
    assert validate_brain_mode_response({"regions": [], "sheet_info": {}, "index": {}})
    assert not validate_brain_mode_response({"regions": []})


def test_normalize_bbox_converts_to_unit_range() -> None:
    bbox = {"x0": 100, "y0": 250, "x1": 900, "y1": 750}
    normalized = normalize_bbox(bbox, width=2000, height=1000)

    assert normalized == {"x0": 0.1, "y0": 0.25, "x1": 0.9, "y1": 0.75}


def test_process_brain_mode_result_normalizes_fields() -> None:
    raw = {
        "regions": [
            {
                "type": "Detail",
                "bbox": {"x0": 100, "y0": 100, "x1": 500, "y1": 400},
                "detail_number": 5,
                "confidence": "0.9",
            }
        ],
        "sheet_reflection": "summary",
        "page_type": "detail_sheet",
        "cross_references": [{"sheet": "A201"}, "S-101"],
        "sheet_info": {"number": "A101"},
        "index": {"keywords": ["flashing"]},
        "questions_this_sheet_answers": ["What does detail 5 show?", 42],
    }

    processed = process_brain_mode_result(raw, width=2000, height=1000)
    assert processed["regions"][0]["bbox"] == {"x0": 0.1, "y0": 0.1, "x1": 0.5, "y1": 0.4}
    assert processed["regions"][0]["detail_number"] == "5"
    assert processed["cross_references"] == ["A201", "S-101"]
    assert processed["questions_this_sheet_answers"] == ["What does detail 5 show?", "42"]


def test_analyze_sheet_brain_mode_returns_result_and_timing(monkeypatch) -> None:
    class FakePart:
        def __init__(self, text: str | None = None, thought: bool = False) -> None:
            self.text = text
            self.thought = thought

    class FakeResponse:
        def __init__(self) -> None:
            parts = [
                FakePart(text="reasoning", thought=True),
                FakePart(text='```json\n{"regions": [], "sheet_info": {}, "index": {}}\n```'),
            ]
            self.candidates = [SimpleNamespace(content=SimpleNamespace(parts=parts))]
            self.text = ""

    class FakeClient:
        def __init__(self) -> None:
            self.models = SimpleNamespace(generate_content=lambda **kwargs: FakeResponse())

    settings = SimpleNamespace(
        use_agentic_vision=True,
        brain_mode_thinking_level="high",
        brain_mode_model="gemini-test-model",
    )
    monkeypatch.setattr("app.services.providers.gemini.get_settings", lambda: settings)
    monkeypatch.setattr("app.services.providers.gemini._get_gemini_client", lambda: FakeClient())

    result, timing_ms = asyncio.run(
        analyze_sheet_brain_mode(
            image_bytes=_make_png(),
            page_name="A101",
            discipline="architectural",
            custom_prompt="test-prompt",
        )
    )

    assert isinstance(result, dict)
    assert "regions" in result
    assert "sheet_info" in result
    assert "index" in result
    assert isinstance(timing_ms, int)
    assert timing_ms >= 0


def test_process_page_brain_mode_returns_agentic_fields(monkeypatch) -> None:
    async def fake_analyze_sheet_brain_mode(**kwargs):
        return (
            {
                "regions": [],
                "sheet_reflection": "brief",
                "page_type": "detail_sheet",
                "cross_references": ["A201"],
                "sheet_info": {"number": "A101"},
                "index": {"keywords": ["flashing"]},
                "questions_this_sheet_answers": ["Where is flashing called out?"],
            },
            812,
        )

    monkeypatch.setattr(
        "app.services.core.brain_mode_processor.analyze_sheet_brain_mode",
        fake_analyze_sheet_brain_mode,
    )

    result = asyncio.run(
        process_page_brain_mode(
            image_bytes=_make_png(),
            page_name="A101",
            discipline_name="Architectural",
        )
    )

    assert result["sheet_info"] == {"number": "A101"}
    assert result["index"] == {"keywords": ["flashing"]}
    assert result["questions_this_sheet_answers"] == ["Where is flashing called out?"]
    assert result["processing_time_ms"] == 812
