"""Tests for code-execution bbox parsing in Big Maestro."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

# Optional dependencies imported transitively by provider modules.
sys.modules.setdefault("voyageai", SimpleNamespace(Client=lambda *args, **kwargs: None))
sys.modules.setdefault("supabase", SimpleNamespace(create_client=lambda *args, **kwargs: None))
sys.modules.setdefault("pdf2image", SimpleNamespace(convert_from_bytes=lambda *args, **kwargs: []))

from app.services.core.big_maestro import parse_code_bboxes, run_deep_agent_for_page


def test_parse_code_bboxes_real_gemini_example_extracts_18_entries() -> None:
    code = """
dimensions = [
    {"box_2d": [243, 90, 255, 107], "label": "2'-8\\""},
    {"box_2d": [245, 151, 255, 169], "label": "9\\""},
    {"box_2d": [321, 34, 341, 41], "label": "1'-11\\""},
    {"box_2d": [834, 219, 843, 236], "label": "4'-0\\""},
    {"box_2d": [834, 259, 844, 281], "label": "10'-1\\""},
    {"box_2d": [834, 303, 844, 323], "label": "6'-11\\""},
    {"box_2d": [841, 443, 850, 461], "label": "10'-6\\""},
    {"box_2d": [841, 492, 850, 520], "label": "12'-6 1/8\\""},
    {"box_2d": [841, 552, 850, 574], "label": "11'-6 1/8\\""},
    {"box_2d": [914, 222, 922, 239], "label": "7'-0\\""},
    {"box_2d": [914, 273, 922, 288], "label": "7'-0\\""},
    {"box_2d": [914, 360, 922, 377], "label": "12'-1\\""},
    {"box_2d": [914, 439, 922, 467], "label": "17'-11 1/2\\""},
    {"box_2d": [909, 582, 917, 608], "label": "15'-6 1/4\\""},
    {"box_2d": [892, 638, 902, 705], "label": "64'-0\\" TOTAL NEW SPACE"},
    {"box_2d": [114, 210, 126, 232], "label": "4\\" REVEAL"},
    {"box_2d": [360, 568, 396, 574], "label": "7'-6\\" CONDITION"},
    {"box_2d": [363, 606, 371, 629], "label": "1\\" REVEAL"}
]
"""
    parsed = parse_code_bboxes(code)
    assert len(parsed) == 18
    assert parsed[0]["bbox"] == pytest.approx([0.090, 0.243, 0.107, 0.255], abs=1e-9)
    assert parsed[0]["label"] == "2'-8\""


def test_parse_code_bboxes_skips_degenerate_boxes() -> None:
    code = """
entries = [
    {"box_2d": [100, 200, 150, 250], "label": "valid"},
    {"box_2d": [100, 300, 150, 300], "label": "zero_width"},
    {"box_2d": [100, 350, 100, 450], "label": "zero_height"}
]
"""
    parsed = parse_code_bboxes(code)
    assert len(parsed) == 1
    assert parsed[0]["label"] == "valid"
    assert parsed[0]["bbox"] == pytest.approx([0.2, 0.1, 0.25, 0.15], abs=1e-9)


def test_parse_code_bboxes_returns_empty_when_none_found() -> None:
    assert parse_code_bboxes("print('no boxes here')") == []


async def _collect_events(stream) -> list[dict]:
    events: list[dict] = []
    async for event in stream:
        events.append(event)
    return events


def test_run_deep_agent_for_page_emits_code_bboxes_event(monkeypatch) -> None:
    async def fake_explore_with_agentic_vision_v4(**kwargs):
        yield {"type": "code", "content": 'items = [{"box_2d": [243, 90, 255, 107], "label": "WIC-1"}]'}
        yield {"type": "result", "data": {"usage": {"input_tokens": 1, "output_tokens": 1}}}

    monkeypatch.setattr(
        "app.services.providers.gemini.explore_with_agentic_vision_v4",
        fake_explore_with_agentic_vision_v4,
    )

    events = asyncio.run(
        _collect_events(
            run_deep_agent_for_page(
                page={"page_id": "page-1", "page_name": "E-3.2", "image_bytes": b"png"},
                search_mission={"query": "find panel", "pages": [{"page_id": "page-1"}]},
                query="find panel",
                memory_context="",
                history_context="",
                viewing_context="",
            )
        )
    )

    code_bbox_event = next(event for event in events if event.get("type") == "code_bboxes")
    assert code_bbox_event["page_id"] == "page-1"
    assert code_bbox_event["bboxes"][0]["bbox"] == pytest.approx([0.09, 0.243, 0.107, 0.255], abs=1e-9)
    assert code_bbox_event["bboxes"][0]["label"] == "WIC-1"


def test_run_deep_agent_for_page_omits_code_bboxes_when_no_boxes(monkeypatch) -> None:
    async def fake_explore_with_agentic_vision_v4(**kwargs):
        yield {"type": "code", "content": "print('hello world')"}
        yield {"type": "result", "data": {"usage": {}}}

    monkeypatch.setattr(
        "app.services.providers.gemini.explore_with_agentic_vision_v4",
        fake_explore_with_agentic_vision_v4,
    )

    events = asyncio.run(
        _collect_events(
            run_deep_agent_for_page(
                page={"page_id": "page-2", "page_name": "K-201", "image_bytes": b"png"},
                search_mission={"query": "find schedule", "pages": [{"page_id": "page-2"}]},
                query="find schedule",
                memory_context="",
                history_context="",
                viewing_context="",
            )
        )
    )

    assert not any(event.get("type") == "code_bboxes" for event in events)
