"""Tests for Smart Fast Mode page selection flow."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

# Optional dependencies used by provider modules during package import.
sys.modules.setdefault("voyageai", SimpleNamespace(Client=lambda *args, **kwargs: None))
sys.modules.setdefault("supabase", SimpleNamespace(create_client=lambda *args, **kwargs: None))
sys.modules.setdefault("pdf2image", SimpleNamespace(convert_from_bytes=lambda *args, **kwargs: []))

from app.services.core import agent as core_agent
from app.routers.queries import (
    extract_deep_mode_trace_payload,
    extract_fast_mode_trace_payload,
    extract_med_mode_trace_payload,
    is_navigation_retry_query,
)
from app.services.providers.gemini import (
    normalize_vision_execution_summary,
    normalize_vision_findings,
    route_fast_query,
    select_pages_smart,
)
from app.services.tools import resolve_highlights
from app.services.utils.sheet_cards import build_sheet_card


def test_select_pages_smart_filters_invalid_and_deduplicates(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.text = """{
  "selected_pages": [
    {"page_id": "page-2", "relevance": "Has panel schedule"},
    {"page_id": "page-2", "relevance": "Duplicate should be removed"},
    {"page_id": "page-404", "relevance": "Not in candidates"},
    {"page_id": "page-1", "relevance": "Contains one-line diagram"}
  ],
  "chat_title": "Panel Schedule",
  "conversation_title": "Electrical Panel Review",
  "response": "E-3.2 has the schedule and E-3.1 has supporting one-line context."
}"""
            self.usage_metadata = SimpleNamespace(
                prompt_token_count=123,
                candidates_token_count=45,
            )

    class FakeClient:
        def __init__(self) -> None:
            self.models = SimpleNamespace(generate_content=lambda **kwargs: FakeResponse())

    monkeypatch.setattr("app.services.providers.gemini._get_gemini_client", lambda: FakeClient())

    result = asyncio.run(
        select_pages_smart(
            project_structure={
                "disciplines": [
                    {
                        "name": "Electrical",
                        "pages": [
                            {"page_id": "page-1", "sheet_number": "E-3.1", "title": "One-Line"},
                            {"page_id": "page-2", "sheet_number": "E-3.2", "title": "Panel Schedule"},
                        ],
                    }
                ],
                "total_pages": 2,
            },
            page_candidates=[
                {"page_id": "page-1", "page_name": "E-3.1", "discipline": "Electrical", "content": "one-line"},
                {"page_id": "page-2", "page_name": "E-3.2", "discipline": "Electrical", "content": "schedule"},
            ],
            query="panel schedule",
        )
    )

    assert result["page_ids"] == ["page-2", "page-1"]
    assert [p["page_id"] for p in result["selected_pages"]] == ["page-2", "page-1"]
    assert result["chat_title"] == "Panel Schedule"
    assert result["conversation_title"] == "Electrical Panel Review"
    assert result["usage"]["input_tokens"] == 123
    assert result["usage"]["output_tokens"] == 45


def test_select_pages_smart_falls_back_to_candidates_when_model_returns_none(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.text = """{
  "selected_pages": [],
  "chat_title": null,
  "conversation_title": null,
  "response": ""
}"""
            self.usage_metadata = SimpleNamespace(
                prompt_token_count=3,
                candidates_token_count=2,
            )

    class FakeClient:
        def __init__(self) -> None:
            self.models = SimpleNamespace(generate_content=lambda **kwargs: FakeResponse())

    monkeypatch.setattr("app.services.providers.gemini._get_gemini_client", lambda: FakeClient())

    result = asyncio.run(
        select_pages_smart(
            project_structure={
                "disciplines": [
                    {
                        "name": "Architectural",
                        "pages": [
                            {"page_id": "page-1", "sheet_number": "A-1.1", "title": "Overview"},
                            {"page_id": "page-2", "sheet_number": "A-1.2", "title": "Details"},
                            {"page_id": "page-3", "sheet_number": "A-1.3", "title": "Notes"},
                            {"page_id": "page-4", "sheet_number": "A-1.4", "title": "Schedule"},
                        ],
                    }
                ],
                "total_pages": 4,
            },
            page_candidates=[
                {"page_id": "page-1", "page_name": "A-1.1", "discipline": "Arch", "content": "overview"},
                {"page_id": "page-2", "page_name": "A-1.2", "discipline": "Arch", "content": "detail"},
                {"page_id": "page-3", "page_name": "A-1.3", "discipline": "Arch", "content": "notes"},
                {"page_id": "page-4", "page_name": "A-1.4", "discipline": "Arch", "content": "schedule"},
            ],
            query="kitchen equipment",
        )
    )

    assert result["page_ids"] == ["page-1", "page-2", "page-3"]
    assert result["chat_title"] == "Query"
    assert result["conversation_title"] == "Query"
    assert result["response"] == "I found the most relevant sheets and pulled them up for review."


def test_route_fast_query_normalizes_response(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.text = """{
  "intent": "PAGE_NAVIGATION",
  "must_terms": ["equipment floor plan", "pages"],
  "preferred_page_types": ["Floor Plan", "plan"],
  "strict": "true",
  "k": "3"
}"""
            self.usage_metadata = SimpleNamespace(
                prompt_token_count=21,
                candidates_token_count=6,
            )

    class FakeClient:
        def __init__(self) -> None:
            self.models = SimpleNamespace(generate_content=lambda **kwargs: FakeResponse())

    monkeypatch.setattr("app.services.providers.gemini._get_gemini_client", lambda: FakeClient())

    result = asyncio.run(route_fast_query(query="equipment floor plan pages"))

    assert result["intent"] == "page_navigation"
    assert result["must_terms"] == ["equipment floor plan"]
    assert result["preferred_page_types"] == ["floor_plan", "plan"]
    assert result["strict"] is True
    assert result["k"] == 3
    assert result["usage"] == {"input_tokens": 21, "output_tokens": 6}


async def _collect_events(stream) -> list[dict]:
    events: list[dict] = []
    async for event in stream:
        events.append(event)
    return events


def test_run_agent_query_fast_uses_smart_selection_response(monkeypatch) -> None:
    async def fake_get_project_structure_summary(db, project_id):
        return {"disciplines": [], "total_pages": 0}

    async def fake_search_pages(db, query, project_id, limit):
        return [
            {"page_id": "page-1", "page_name": "E-3.2", "discipline": "Electrical", "content": "panel schedule"},
            {"page_id": "page-2", "page_name": "E-3.1", "discipline": "Electrical", "content": "one-line"},
        ]

    async def fake_search_pages_and_regions(db, query, project_id):
        return {"page-2": [{"id": "region-1"}]}

    async def fake_select_pages(db, page_ids):
        return {
            "pages": [
                {
                    "page_id": page_id,
                    "page_name": "E-3.2" if page_id == "page-1" else "E-3.1",
                    "file_path": f"/tmp/{page_id}.png",
                    "discipline_id": "disc-1",
                    "discipline_name": "Electrical",
                    "semantic_index": None,
                }
                for page_id in page_ids
            ]
        }

    async def fake_select_pages_smart(project_structure, page_candidates, query, history_context="", viewing_context=""):
        return {
            "selected_pages": [{"page_id": "page-1", "relevance": "Contains panel schedule"}],
            "page_ids": ["page-1"],
            "chat_title": "Panel Schedule",
            "conversation_title": "Electrical Panel Review",
            "response": "E-3.2 has the panel schedule you are looking for.",
            "usage": {"input_tokens": 11, "output_tokens": 7},
        }

    monkeypatch.setattr(core_agent, "get_settings", lambda: SimpleNamespace(fast_ranker_v2=False, fast_selector_rerank=False))
    monkeypatch.setattr("app.services.tools.get_project_structure_summary", fake_get_project_structure_summary)
    monkeypatch.setattr("app.services.tools.search_pages", fake_search_pages)
    monkeypatch.setattr("app.services.tools.select_pages", fake_select_pages)
    monkeypatch.setattr("app.services.utils.search.search_pages_and_regions", fake_search_pages_and_regions)
    monkeypatch.setattr("app.services.providers.gemini.select_pages_smart", fake_select_pages_smart)
    monkeypatch.setattr(core_agent, "_expand_with_cross_reference_pages", lambda db, project_id, page_ids: page_ids)
    monkeypatch.setattr(
        core_agent,
        "_order_page_ids",
        lambda db, page_ids, sort_by_sheet_number=True: (
            page_ids,
            {pid: SimpleNamespace(page_name="E-3.2" if pid == "page-1" else "E-3.1") for pid in page_ids},
        ),
    )

    events = asyncio.run(
        _collect_events(
            core_agent.run_agent_query_fast(
                db=SimpleNamespace(),
                project_id="project-1",
                query="panel schedule",
                history_messages=[{"role": "user", "content": "Need electrical sheet"}],
                viewing_context={"page_name": "E-2.1", "discipline_name": "Electrical"},
            )
        )
    )

    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    assert any(e.get("tool") == "select_pages_smart" for e in tool_calls)

    text_events = [e for e in events if e.get("type") == "text"]
    assert text_events[-1]["content"] == "E-3.2 has the panel schedule you are looking for."

    done_event = next(e for e in events if e.get("type") == "done")
    assert done_event["displayTitle"] == "Panel Schedule"
    assert done_event["conversationTitle"] == "Electrical Panel Review"
    assert done_event["usage"] == {"inputTokens": 11, "outputTokens": 7}


def test_run_agent_query_fast_page_navigation_uses_sheet_list_response(monkeypatch) -> None:
    async def fake_get_project_structure_summary(db, project_id):
        return {
            "disciplines": [
                {
                    "name": "Kitchen",
                    "pages": [
                        {"page_id": "page-1", "sheet_number": "K-101", "title": "Equipment Plan"},
                        {"page_id": "page-2", "sheet_number": "K-201", "title": "Enlarged Kitchen"},
                    ],
                }
            ],
            "total_pages": 2,
        }

    async def fake_search_pages(db, query, project_id, limit):
        return [
            {"page_id": "page-2", "page_name": "K-201", "discipline": "Kitchen", "content": "equipment floor plan"},
            {"page_id": "page-1", "page_name": "K-101", "discipline": "Kitchen", "content": "equipment plan"},
        ]

    async def fake_search_pages_and_regions(db, query, project_id):
        return {}

    async def fake_select_pages(db, page_ids):
        return {
            "pages": [
                {
                    "page_id": page_id,
                    "page_name": "K-101" if page_id == "page-1" else "K-201",
                    "file_path": f"/tmp/{page_id}.png",
                    "discipline_id": "disc-1",
                    "discipline_name": "Kitchen",
                    "semantic_index": None,
                }
                for page_id in page_ids
            ]
        }

    async def fake_select_pages_smart(project_structure, page_candidates, query, history_context="", viewing_context=""):
        return {
            "selected_pages": [{"page_id": "page-1", "relevance": "Equipment sheet"}],
            "page_ids": ["page-1"],
            "chat_title": "Equipment Plans",
            "conversation_title": "Kitchen Equipment Plans",
            "response": "Narrative that should be ignored for page-list queries.",
            "usage": {"input_tokens": 9, "output_tokens": 4},
        }

    monkeypatch.setattr(core_agent, "get_settings", lambda: SimpleNamespace(fast_ranker_v2=False, fast_selector_rerank=False))
    monkeypatch.setattr("app.services.tools.get_project_structure_summary", fake_get_project_structure_summary)
    monkeypatch.setattr("app.services.tools.search_pages", fake_search_pages)
    monkeypatch.setattr("app.services.tools.select_pages", fake_select_pages)
    monkeypatch.setattr("app.services.utils.search.search_pages_and_regions", fake_search_pages_and_regions)
    monkeypatch.setattr("app.services.providers.gemini.select_pages_smart", fake_select_pages_smart)
    monkeypatch.setattr(core_agent, "_expand_with_cross_reference_pages", lambda db, project_id, page_ids: page_ids)
    monkeypatch.setattr(
        core_agent,
        "_order_page_ids",
        lambda db, page_ids, sort_by_sheet_number=True: (
            page_ids,
            {
                "page-1": SimpleNamespace(page_name="K-101"),
                "page-2": SimpleNamespace(page_name="K-201"),
            },
        ),
    )

    events = asyncio.run(
        _collect_events(
            core_agent.run_agent_query_fast(
                db=SimpleNamespace(),
                project_id="project-1",
                query="equipment floor plan pages",
                history_messages=[],
                viewing_context=None,
            )
        )
    )

    text_events = [e for e in events if e.get("type") == "text"]
    assert text_events[-1]["content"].startswith("Showing likely sheets:")
    assert "K-101" in text_events[-1]["content"]


def test_run_agent_query_fast_router_strict_filters_noise(monkeypatch) -> None:
    async def fake_route_fast_query(query, history_context="", viewing_context=""):
        return {
            "intent": "page_navigation",
            "must_terms": ["equipment floor plan"],
            "preferred_page_types": ["floor_plan"],
            "strict": True,
            "k": 2,
            "usage": {"input_tokens": 2, "output_tokens": 1},
        }

    async def fake_get_project_structure_summary(db, project_id):
        return {
            "disciplines": [
                {
                    "name": "Kitchen",
                    "pages": [
                        {"page_id": "page-1", "sheet_number": "K-101", "title": "Equipment Floor Plan"},
                        {"page_id": "page-2", "sheet_number": "K-102", "title": "Equipment Notes"},
                        {"page_id": "page-3", "sheet_number": "A-101", "title": "Roof Plan"},
                    ],
                }
            ],
            "total_pages": 3,
        }

    async def fake_search_pages(db, query, project_id, limit):
        return [
            {
                "page_id": "page-1",
                "page_name": "K-101",
                "discipline": "Kitchen",
                "page_type": "floor_plan",
                "content": "equipment floor plan for kitchen",
                "keywords": ["equipment", "floor plan"],
            },
            {
                "page_id": "page-2",
                "page_name": "K-102",
                "discipline": "Kitchen",
                "page_type": "notes",
                "content": "equipment notes and legends",
                "keywords": ["equipment", "notes"],
            },
            {
                "page_id": "page-3",
                "page_name": "A-101",
                "discipline": "Architectural",
                "page_type": "plan",
                "content": "roof plan overview",
                "keywords": ["roof", "plan"],
            },
        ]

    async def fake_search_pages_and_regions(db, query, project_id):
        return {"page-3": [{"id": "region-1"}]}

    captured = {"candidate_ids": []}

    async def fake_select_pages_smart(project_structure, page_candidates, query, history_context="", viewing_context=""):
        captured["candidate_ids"] = [p.get("page_id") for p in page_candidates]
        return {
            "selected_pages": [{"page_id": "page-3", "relevance": "Noisy match"}],
            "page_ids": ["page-3"],
            "chat_title": "Equipment Plans",
            "conversation_title": "Kitchen Equipment Plans",
            "response": "Routing to likely sheets.",
            "usage": {"input_tokens": 7, "output_tokens": 3},
        }

    async def fake_select_pages(db, page_ids):
        return {
            "pages": [
                {
                    "page_id": page_id,
                    "page_name": {"page-1": "K-101", "page-2": "K-102", "page-3": "A-101"}.get(page_id, ""),
                    "file_path": f"/tmp/{page_id}.png",
                    "discipline_id": "disc-1",
                    "discipline_name": "Kitchen",
                    "semantic_index": None,
                }
                for page_id in page_ids
            ]
        }

    monkeypatch.setattr(core_agent, "get_settings", lambda: SimpleNamespace(fast_ranker_v2=False, fast_selector_rerank=False))
    monkeypatch.setattr("app.services.providers.gemini.route_fast_query", fake_route_fast_query)
    monkeypatch.setattr("app.services.tools.get_project_structure_summary", fake_get_project_structure_summary)
    monkeypatch.setattr("app.services.tools.search_pages", fake_search_pages)
    monkeypatch.setattr("app.services.utils.search.search_pages_and_regions", fake_search_pages_and_regions)
    monkeypatch.setattr("app.services.providers.gemini.select_pages_smart", fake_select_pages_smart)
    monkeypatch.setattr("app.services.tools.select_pages", fake_select_pages)
    monkeypatch.setattr(core_agent, "_expand_with_cross_reference_pages", lambda db, project_id, page_ids: page_ids)
    monkeypatch.setattr(
        core_agent,
        "_order_page_ids",
        lambda db, page_ids, sort_by_sheet_number=True: (
            page_ids,
            {pid: SimpleNamespace(page_name={"page-1": "K-101", "page-2": "K-102", "page-3": "A-101"}[pid]) for pid in page_ids},
        ),
    )

    events = asyncio.run(
        _collect_events(
            core_agent.run_agent_query_fast(
                db=SimpleNamespace(),
                project_id="project-1",
                query="equipment floor plan pages",
                history_messages=[],
                viewing_context=None,
            )
        )
    )

    assert captured["candidate_ids"] == ["page-1"]
    select_pages_call = next(
        e for e in events if e.get("type") == "tool_call" and e.get("tool") == "select_pages"
    )
    assert select_pages_call["input"]["page_ids"] == ["page-1", "page-2"]

    fast_trace_event = next(
        e for e in events if e.get("type") == "tool_result" and e.get("tool") == "fast_mode_trace"
    )
    fast_trace = fast_trace_event["result"]
    assert fast_trace["query_plan"]["intent"] == "page_navigation"
    assert fast_trace["candidate_sets"]["strict_keyword_hits"]["top_ids"] == ["page-1"]
    assert fast_trace["final_selection"]["primary"][0]["page_id"] == "page-1"
    assert fast_trace["token_cost"]["total"] == {"input_tokens": 9, "output_tokens": 4}

    done_event = next(e for e in events if e.get("type") == "done")
    assert done_event["usage"] == {"inputTokens": 9, "outputTokens": 4}


def test_extract_fast_mode_trace_payload_returns_latest() -> None:
    trace = [
        {"type": "tool_result", "tool": "fast_mode_trace", "result": {"query_plan": {"intent": "qa"}}},
        {"type": "tool_result", "tool": "fast_mode_trace", "result": {"query_plan": {"intent": "page_navigation"}}},
    ]
    payload = extract_fast_mode_trace_payload(trace)
    assert payload is not None
    assert payload["query_plan"]["intent"] == "page_navigation"


def test_is_navigation_retry_query_heuristic() -> None:
    assert is_navigation_retry_query("can you pull up those pages again?")
    assert not is_navigation_retry_query("where is the walk-in cooler")


def test_build_sheet_card_extracts_reflection_metadata() -> None:
    card = build_sheet_card(
        sheet_number="K-101",
        page_type="floor_plan",
        discipline_name="Kitchen",
        sheet_reflection=(
            "## K-101 Equipment Floor Plan\n\n"
            "Shows kitchen equipment layout with WIC-1, RTU-2, and panel L1 locations.\n\n"
            "**Key Details:**\n"
            "- Verify hood curb dimensions.\n"
            "- Coordinate with electrical schedule.\n"
        ),
        master_index={"keywords": ["equipment", "kitchen"], "items": ["WIC-1", "RTU-2"]},
        keywords=["floor plan"],
        cross_references=["E-3.2", {"sheet": "M-1.1"}],
    )

    assert card["reflection_title"] == "K-101 Equipment Floor Plan"
    assert "WIC-1" in card["reflection_entities"]
    assert "E-3.2" in card["cross_references"]
    assert "M-1.1" in card["cross_references"]
    assert "equipment" in " ".join(card["reflection_keywords"]).lower()


def test_run_agent_query_fast_v2_skips_selector_and_ranks_deterministically(monkeypatch) -> None:
    async def fake_route_fast_query(query, history_context="", viewing_context=""):
        return {
            "intent": "page_navigation",
            "must_terms": ["equipment floor plan"],
            "preferred_page_types": ["floor_plan"],
            "strict": True,
            "k": 3,
            "usage": {"input_tokens": 5, "output_tokens": 2},
            "model": "fake-router",
        }

    async def fake_get_project_structure_summary(db, project_id):
        return {
            "disciplines": [
                {
                    "name": "Kitchen",
                    "pages": [
                        {"page_id": "page-1", "sheet_number": "K-101", "title": "Equipment Floor Plan"},
                        {"page_id": "page-2", "sheet_number": "K-001", "title": "Cover Sheet"},
                        {"page_id": "page-3", "sheet_number": "K-102", "title": "Equipment Notes"},
                    ],
                }
            ],
            "total_pages": 3,
        }

    async def fake_search_pages(db, query, project_id, limit):
        return [
            {
                "page_id": "page-1",
                "page_name": "K-101",
                "discipline": "Kitchen",
                "page_type": "floor_plan",
                "content": "Equipment floor plan with WIC-1 and RTU-2.",
                "sheet_reflection": "## Equipment Floor Plan\nWIC-1 layout and major equipment tags.",
                "keywords": ["equipment", "floor plan"],
                "master_index": {"keywords": ["equipment", "kitchen"]},
            },
            {
                "page_id": "page-2",
                "page_name": "K-001",
                "discipline": "Kitchen",
                "page_type": "cover",
                "content": "General cover and sheet index.",
                "sheet_reflection": "## Cover Sheet\nGeneral notes and sheet list.",
                "keywords": ["cover"],
                "master_index": {"keywords": ["cover", "index"]},
            },
            {
                "page_id": "page-3",
                "page_name": "K-102",
                "discipline": "Kitchen",
                "page_type": "notes",
                "content": "Equipment notes for kitchen systems.",
                "sheet_reflection": "## Equipment Notes\nSupport notes for equipment plan.",
                "keywords": ["notes", "equipment"],
                "master_index": {"keywords": ["notes", "equipment"]},
            },
        ]

    async def fake_search_pages_and_regions(db, query, project_id):
        return {"page-3": [{"id": "region-1"}]}

    async def fake_select_pages(db, page_ids):
        return {
            "pages": [
                {
                    "page_id": page_id,
                    "page_name": {"page-1": "K-101", "page-2": "K-001", "page-3": "K-102"}.get(page_id, ""),
                    "file_path": f"/tmp/{page_id}.png",
                    "discipline_id": "disc-1",
                    "discipline_name": "Kitchen",
                    "semantic_index": None,
                }
                for page_id in page_ids
            ]
        }

    async def fake_select_pages_smart(*args, **kwargs):
        raise AssertionError("Selector should be skipped when FAST_RANKER_V2 is enabled without rerank")

    monkeypatch.setattr(core_agent, "get_settings", lambda: SimpleNamespace(fast_ranker_v2=True, fast_selector_rerank=False))
    monkeypatch.setattr("app.services.providers.gemini.route_fast_query", fake_route_fast_query)
    monkeypatch.setattr("app.services.providers.gemini.select_pages_smart", fake_select_pages_smart)
    monkeypatch.setattr("app.services.tools.get_project_structure_summary", fake_get_project_structure_summary)
    monkeypatch.setattr("app.services.tools.search_pages", fake_search_pages)
    monkeypatch.setattr("app.services.utils.search.search_pages_and_regions", fake_search_pages_and_regions)
    monkeypatch.setattr("app.services.tools.select_pages", fake_select_pages)
    monkeypatch.setattr(core_agent, "_expand_with_cross_reference_pages", lambda db, project_id, page_ids: page_ids)
    monkeypatch.setattr(
        core_agent,
        "_order_page_ids",
        lambda db, page_ids, sort_by_sheet_number=True: (
            page_ids,
            {pid: SimpleNamespace(page_name={"page-1": "K-101", "page-2": "K-001", "page-3": "K-102"}[pid]) for pid in page_ids},
        ),
    )

    events = asyncio.run(
        _collect_events(
            core_agent.run_agent_query_fast(
                db=SimpleNamespace(),
                project_id="project-1",
                query="equipment floor plan pages",
                history_messages=[],
                viewing_context=None,
            )
        )
    )

    selector_tool_calls = [
        event
        for event in events
        if event.get("type") == "tool_call" and event.get("tool") == "select_pages_smart"
    ]
    assert not selector_tool_calls

    select_pages_call = next(
        event for event in events if event.get("type") == "tool_call" and event.get("tool") == "select_pages"
    )
    assert select_pages_call["input"]["page_ids"][0] == "page-1"

    fast_trace_event = next(
        event for event in events if event.get("type") == "tool_result" and event.get("tool") == "fast_mode_trace"
    )
    assert fast_trace_event["result"]["query_plan"]["ranker"] == "v2"
    assert fast_trace_event["result"]["candidate_sets"]["smart_selector_hits"]["count"] == 0

    done_event = next(event for event in events if event.get("type") == "done")
    assert done_event["usage"] == {"inputTokens": 5, "outputTokens": 2}


def test_extract_med_mode_trace_payload_returns_latest() -> None:
    trace = [
        {"type": "tool_result", "tool": "med_mode_trace", "result": {"query_plan": {"intent": "qa"}}},
        {"type": "tool_result", "tool": "med_mode_trace", "result": {"query_plan": {"intent": "page_navigation"}}},
    ]
    payload = extract_med_mode_trace_payload(trace)
    assert payload is not None
    assert payload["query_plan"]["intent"] == "page_navigation"


def test_resolve_highlights_supports_bboxes_without_ocr_words() -> None:
    pages_data = [
        {
            "page_id": "page-1",
            "semantic_index": {
                "image_width": 1000,
                "image_height": 500,
                "words": [],
            },
        }
    ]
    highlights = [
        {
            "page_id": "page-1",
            "bboxes": [
                {
                    "bbox": [0.1, 0.2, 0.3, 0.4],
                    "category": "detail",
                    "source_text": "Hood detail",
                    "confidence": "medium",
                }
            ],
            "source": "search",
        }
    ]

    resolved = resolve_highlights(pages_data, highlights)
    assert resolved
    assert resolved[0]["page_id"] == "page-1"
    assert resolved[0]["words"][0]["bbox"]["x0"] == 100.0
    assert resolved[0]["words"][0]["bbox"]["y0"] == 100.0


def test_run_agent_query_med_emits_trace_and_highlights(monkeypatch) -> None:
    async def fake_route_fast_query(query, history_context="", viewing_context=""):
        return {
            "intent": "qa",
            "must_terms": ["panel schedule"],
            "preferred_page_types": ["schedule"],
            "strict": False,
            "k": 3,
            "usage": {"input_tokens": 4, "output_tokens": 2},
            "model": "fake-router",
        }

    async def fake_get_project_structure_summary(db, project_id):
        return {
            "disciplines": [
                {
                    "name": "Electrical",
                    "pages": [
                        {"page_id": "page-1", "sheet_number": "E-3.2", "title": "Panel Schedule"},
                        {"page_id": "page-2", "sheet_number": "E-3.1", "title": "One-Line"},
                    ],
                }
            ],
            "total_pages": 2,
        }

    async def fake_search_pages(db, query, project_id, limit):
        return [
            {
                "page_id": "page-1",
                "page_name": "E-3.2",
                "discipline": "Electrical",
                "page_type": "schedule",
                "content": "Panel schedule table with circuit data",
                "sheet_reflection": "## Panel Schedule",
                "keywords": ["panel", "schedule"],
                "master_index": {"keywords": ["panel", "schedule"]},
            },
            {
                "page_id": "page-2",
                "page_name": "E-3.1",
                "discipline": "Electrical",
                "page_type": "plan",
                "content": "One-line diagram and feeder notes",
                "sheet_reflection": "## One-Line Diagram",
                "keywords": ["one-line", "feeder"],
                "master_index": {"keywords": ["one-line", "feeder"]},
            },
        ]

    async def fake_search_pages_and_regions(db, query, project_id, limit=5, similarity_threshold=0.7):
        return {
            "page-1": [
                {
                    "id": "region_schedule",
                    "type": "schedule",
                    "label": "PANEL SCHEDULE",
                    "bbox": {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.7},
                    "_similarity": 0.93,
                }
            ],
        }

    async def fake_select_pages_smart(
        project_structure,
        page_candidates,
        query,
        history_context="",
        viewing_context="",
    ):
        return {
            "selected_pages": [
                {"page_id": "page-1", "relevance": "Panel schedule table answers the query directly."}
            ],
            "page_ids": ["page-1"],
            "chat_title": "Panel Schedule",
            "conversation_title": "Panel Schedule Location",
            "response": "Check E-3.2 first for the main panel schedule table and feeder circuit data.",
            "usage": {"input_tokens": 6, "output_tokens": 3},
        }

    async def fake_select_pages(db, page_ids):
        return {
            "pages": [
                {
                    "page_id": page_id,
                    "page_name": "E-3.2" if page_id == "page-1" else "E-3.1",
                    "file_path": f"/tmp/{page_id}.png",
                    "discipline_id": "disc-1",
                    "discipline_name": "Electrical",
                    "semantic_index": {
                        "image_width": 1200,
                        "image_height": 900,
                        "words": [],
                    },
                }
                for page_id in page_ids
            ]
        }

    page_map = {
        "page-1": SimpleNamespace(
            page_name="E-3.2",
            page_type="schedule",
            regions=[
                {
                    "id": "region_schedule",
                    "type": "schedule",
                    "label": "PANEL SCHEDULE",
                    "bbox": {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.7},
                }
            ],
            discipline=SimpleNamespace(display_name="Electrical"),
            sheet_card={},
            sheet_reflection="## Panel Schedule",
            master_index={"keywords": ["panel", "schedule"]},
            cross_references=[],
        ),
        "page-2": SimpleNamespace(
            page_name="E-3.1",
            page_type="plan",
            regions=[
                {
                    "id": "region_plan",
                    "type": "plan",
                    "label": "ONE-LINE AREA",
                    "bbox": {"x0": 0.2, "y0": 0.2, "x1": 0.8, "y1": 0.6},
                }
            ],
            discipline=SimpleNamespace(display_name="Electrical"),
            sheet_card={},
            sheet_reflection="## One-Line",
            master_index={"keywords": ["one-line"]},
            cross_references=[],
        ),
    }

    monkeypatch.setattr(
        core_agent,
        "get_settings",
        lambda: SimpleNamespace(
            fast_ranker_v2=True,
            fast_selector_rerank=False,
            med_mode_regions=True,
        ),
    )
    monkeypatch.setattr("app.services.providers.gemini.route_fast_query", fake_route_fast_query)
    monkeypatch.setattr("app.services.providers.gemini.select_pages_smart", fake_select_pages_smart)
    monkeypatch.setattr("app.services.tools.get_project_structure_summary", fake_get_project_structure_summary)
    monkeypatch.setattr("app.services.tools.search_pages", fake_search_pages)
    monkeypatch.setattr("app.services.utils.search.search_pages_and_regions", fake_search_pages_and_regions)
    monkeypatch.setattr("app.services.tools.select_pages", fake_select_pages)
    monkeypatch.setattr(core_agent, "_expand_with_cross_reference_pages", lambda db, project_id, page_ids: page_ids)
    monkeypatch.setattr(
        core_agent,
        "_order_page_ids",
        lambda db, page_ids, sort_by_sheet_number=True: (
            page_ids,
            {pid: page_map[pid] for pid in page_ids if pid in page_map},
        ),
    )

    events = asyncio.run(
        _collect_events(
            core_agent.run_agent_query_med(
                db=SimpleNamespace(),
                project_id="project-1",
                query="where is the panel schedule",
                history_messages=[],
                viewing_context=None,
            )
        )
    )

    med_trace_event = next(
        e for e in events if e.get("type") == "tool_result" and e.get("tool") == "med_mode_trace"
    )
    assert med_trace_event["result"]["final_highlights"]["count"] >= 1
    assert med_trace_event["result"]["query_plan"]["ranker"] == "v2"
    assert med_trace_event["result"]["candidate_sets"]["smart_selector_hits"]["count"] == 1

    resolve_event = next(
        e for e in events if e.get("type") == "tool_result" and e.get("tool") == "resolve_highlights"
    )
    resolved_highlights = resolve_event["result"]["highlights"]
    assert resolved_highlights
    assert resolved_highlights[0]["page_id"] == "page-1"
    assert resolved_highlights[0]["words"]
    assert resolved_highlights[0]["words"][0]["bbox"]["width"] > 0

    text_event = next(e for e in events if e.get("type") == "text")
    assert "Check E-3.2 first" in text_event["content"]

    done_event = next(e for e in events if e.get("type") == "done")
    assert done_event["usage"] == {"inputTokens": 10, "outputTokens": 5}
    assert done_event["displayTitle"] == "Panel Schedule"
    assert done_event["conversationTitle"] == "Panel Schedule Location"


def test_extract_deep_mode_trace_payload_returns_latest() -> None:
    trace = [
        {"type": "tool_result", "tool": "deep_mode_trace", "result": {"query_plan": {"intent": "verification"}}},
        {"type": "tool_result", "tool": "deep_mode_trace", "result": {"query_plan": {"intent": "qa"}}},
    ]
    payload = extract_deep_mode_trace_payload(trace)
    assert payload is not None
    assert payload["query_plan"]["intent"] == "qa"


def test_normalize_vision_execution_summary_maps_pass_aliases() -> None:
    summary = normalize_vision_execution_summary(
        {
            "pass_counts": {"1": "3", "2": 2},
            "micro_crop_count": "1",
        }
    )
    assert summary == {"pass_1": 3, "pass_2": 2, "pass_3": 1}


def test_normalize_vision_findings_keeps_verification_metadata() -> None:
    pages = [
        {
            "page_id": "page-1",
            "page_name": "E-3.2",
            "semantic_index": {
                "image_width": 1000,
                "image_height": 1000,
                "words": [
                    {"id": 101, "text": "480V", "bbox": {"x0": 100, "y0": 100, "x1": 180, "y1": 140}},
                ],
            },
        }
    ]
    findings = [
        {
            "category": "electrical",
            "content": "Panel voltage is 480V",
            "page_id": "E-3.2",
            "semantic_refs": [101],
            "confidence": "verified_via_zoom",
            "source_text": "480V",
            "verification_method": "multi pass zoom",
            "verification_pass": "2",
            "candidate_region_id": "region_schedule",
        }
    ]

    normalized = normalize_vision_findings(findings, pages)
    assert len(normalized) == 1
    assert normalized[0]["page_id"] == "page-1"
    assert normalized[0]["verification_method"] == "multi_pass_zoom"
    assert normalized[0]["verification_pass"] == 2
    assert normalized[0]["candidate_region_id"] == "region_schedule"


def test_run_agent_query_deep_v2_emits_trace_and_resolved_highlights(monkeypatch) -> None:
    async def fake_get_project_structure_summary(db, project_id):
        return {
            "disciplines": [
                {
                    "name": "Electrical",
                    "pages": [
                        {"page_id": "page-1", "sheet_number": "E-3.2", "title": "Panel Schedule"},
                    ],
                }
            ],
            "total_pages": 1,
        }

    async def fake_search_pages_and_regions(db, query, project_id):
        return {
            "page-1": [
                {
                    "id": "region_schedule",
                    "type": "schedule",
                    "label": "PANEL SCHEDULE",
                    "bbox": {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.7},
                    "_similarity": 0.92,
                }
            ]
        }

    async def fake_search_pages(db, query, project_id, limit):
        return []

    async def fake_select_pages(db, page_ids):
        return {
            "pages": [
                {
                    "page_id": page_id,
                    "page_name": "E-3.2",
                    "file_path": f"/tmp/{page_id}.png",
                    "discipline_id": "disc-1",
                    "discipline_name": "Electrical",
                    "semantic_index": {
                        "image_width": 1000,
                        "image_height": 1000,
                        "words": [
                                {
                                    "id": 101,
                                    "text": "480V",
                                    "bbox": {
                                        "x0": 120,
                                        "y0": 240,
                                        "x1": 180,
                                        "y1": 270,
                                        "width": 60,
                                        "height": 30,
                                    },
                                    "role": "cell_value",
                                    "region_type": "schedule",
                                }
                        ],
                    },
                }
                for page_id in page_ids
            ]
        }

    async def fake_explore_concept_with_vision_streaming(
        query,
        pages,
        verification_plan=None,
        history_context="",
        viewing_context="",
    ):
        assert isinstance(verification_plan, dict)
        budgets = verification_plan.get("budgets", {})
        assert budgets.get("max_candidate_regions") == core_agent.DEEP_CANDIDATE_REGION_LIMIT
        yield {"type": "thinking", "content": "zoom pass 1"}
        yield {
            "type": "result",
            "data": {
                "concept_name": "Panel Schedule",
                "summary": "Verified panel schedule values.",
                "findings": [
                    {
                        "category": "electrical",
                        "content": "Panel schedule shows 480V service.",
                        "page_id": "page-1",
                        "semantic_refs": [101],
                        "bbox": [0.12, 0.24, 0.18, 0.27],
                        "confidence": "verified_via_zoom",
                        "source_text": "480V",
                        "verification_method": "multi_pass_zoom",
                        "verification_pass": 2,
                        "candidate_region_id": "region_schedule",
                    }
                ],
                "cross_references": [],
                "execution_summary": {
                    "pass_1_crop_count": 3,
                    "pass_2_crop_count": 1,
                    "pass_3_crop_count": 0,
                },
                "gaps": [],
                "response": "Panel schedule verified at 480V.",
                "usage": {"input_tokens": 21, "output_tokens": 9},
            },
        }

    async def fake_load_page_image_bytes(page):
        return b"fake_png"

    page_map = {
        "page-1": SimpleNamespace(
            id="page-1",
            page_name="E-3.2",
            page_type="schedule",
            regions=[
                {
                    "id": "region_schedule",
                    "type": "schedule",
                    "label": "PANEL SCHEDULE",
                    "bbox": {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.7},
                }
            ],
            discipline=SimpleNamespace(display_name="Electrical"),
            sheet_reflection="## Panel Schedule",
            context_markdown="",
            full_context="",
            initial_context="",
            details=[],
            semantic_index={
                "image_width": 1000,
                "image_height": 1000,
                "words": [],
            },
            master_index={"keywords": ["panel", "schedule"]},
        )
    }

    monkeypatch.setattr(
        core_agent,
        "get_settings",
        lambda: SimpleNamespace(deep_mode_vision_v2=True),
    )
    monkeypatch.setattr("app.services.tools.get_project_structure_summary", fake_get_project_structure_summary)
    monkeypatch.setattr("app.services.utils.search.search_pages_and_regions", fake_search_pages_and_regions)
    monkeypatch.setattr("app.services.tools.search_pages", fake_search_pages)
    monkeypatch.setattr("app.services.tools.select_pages", fake_select_pages)
    monkeypatch.setattr("app.services.providers.gemini.explore_concept_with_vision_streaming", fake_explore_concept_with_vision_streaming)
    monkeypatch.setattr(core_agent, "_expand_with_cross_reference_pages", lambda db, project_id, page_ids: page_ids)
    monkeypatch.setattr(
        core_agent,
        "_order_page_ids",
        lambda db, page_ids, sort_by_sheet_number=True: (
            page_ids,
            {pid: page_map[pid] for pid in page_ids if pid in page_map},
        ),
    )
    monkeypatch.setattr(core_agent, "_load_page_image_bytes", fake_load_page_image_bytes)

    events = asyncio.run(
        _collect_events(
            core_agent.run_agent_query_deep(
                db=SimpleNamespace(),
                project_id="project-1",
                query="verify panel schedule voltage",
                history_messages=[],
                viewing_context=None,
            )
        )
    )

    deep_trace_event = next(
        event for event in events if event.get("type") == "tool_result" and event.get("tool") == "deep_mode_trace"
    )
    assert deep_trace_event["result"]["execution_summary"]["deep_v2_enabled"] is True
    assert deep_trace_event["result"]["final_findings"]["verified_via_zoom"] == 1
    assert deep_trace_event["result"]["execution_summary"]["pass_1"] == 3
    assert deep_trace_event["result"]["execution_summary"]["pass_2"] == 1
    assert deep_trace_event["result"]["execution_summary"]["pass_3"] == 0
    assert deep_trace_event["result"]["execution_summary"]["pass_total"] == 4

    resolve_event = next(
        event for event in events if event.get("type") == "tool_result" and event.get("tool") == "resolve_highlights"
    )
    resolved = resolve_event["result"]["highlights"]
    assert resolved
    assert resolved[0]["page_id"] == "page-1"
    assert resolved[0]["words"]

    done_event = next(event for event in events if event.get("type") == "done")
    assert done_event["usage"] == {"inputTokens": 21, "outputTokens": 9}
    assert done_event["findings"]


def test_run_agent_query_deep_v2_falls_back_when_vision_fails(monkeypatch) -> None:
    async def fake_get_project_structure_summary(db, project_id):
        return {
            "disciplines": [
                {
                    "name": "Electrical",
                    "pages": [
                        {"page_id": "page-1", "sheet_number": "E-3.2", "title": "Panel Schedule"},
                    ],
                }
            ],
            "total_pages": 1,
        }

    async def fake_search_pages_and_regions(db, query, project_id):
        return {
            "page-1": [
                {
                    "id": "region_schedule",
                    "type": "schedule",
                    "label": "PANEL SCHEDULE",
                    "bbox": {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.7},
                    "_similarity": 0.92,
                }
            ]
        }

    async def fake_search_pages(db, query, project_id, limit):
        return []

    async def fake_select_pages(db, page_ids):
        return {
            "pages": [
                {
                    "page_id": page_id,
                    "page_name": "E-3.2",
                    "file_path": f"/tmp/{page_id}.png",
                    "discipline_id": "disc-1",
                    "discipline_name": "Electrical",
                    "semantic_index": {
                        "image_width": 1000,
                        "image_height": 1000,
                        "words": [],
                    },
                }
                for page_id in page_ids
            ]
        }

    async def fake_explore_concept_with_vision_streaming(
        query,
        pages,
        verification_plan=None,
        history_context="",
        viewing_context="",
    ):
        if False:
            yield {"type": "result", "data": {}}
        raise RuntimeError("vision execution failed")

    async def fake_load_page_image_bytes(page):
        return b"fake_png"

    page_map = {
        "page-1": SimpleNamespace(
            id="page-1",
            page_name="E-3.2",
            page_type="schedule",
            regions=[
                {
                    "id": "region_schedule",
                    "type": "schedule",
                    "label": "PANEL SCHEDULE",
                    "bbox": {"x0": 0.1, "y0": 0.2, "x1": 0.6, "y1": 0.7},
                }
            ],
            discipline=SimpleNamespace(display_name="Electrical"),
            sheet_reflection="## Panel Schedule",
            context_markdown="",
            full_context="",
            initial_context="",
            details=[],
            semantic_index={"image_width": 1000, "image_height": 1000, "words": []},
            master_index={"keywords": ["panel", "schedule"]},
        )
    }

    monkeypatch.setattr(
        core_agent,
        "get_settings",
        lambda: SimpleNamespace(deep_mode_vision_v2=True),
    )
    monkeypatch.setattr("app.services.tools.get_project_structure_summary", fake_get_project_structure_summary)
    monkeypatch.setattr("app.services.utils.search.search_pages_and_regions", fake_search_pages_and_regions)
    monkeypatch.setattr("app.services.tools.search_pages", fake_search_pages)
    monkeypatch.setattr("app.services.tools.select_pages", fake_select_pages)
    monkeypatch.setattr("app.services.providers.gemini.explore_concept_with_vision_streaming", fake_explore_concept_with_vision_streaming)
    monkeypatch.setattr(core_agent, "_expand_with_cross_reference_pages", lambda db, project_id, page_ids: page_ids)
    monkeypatch.setattr(
        core_agent,
        "_order_page_ids",
        lambda db, page_ids, sort_by_sheet_number=True: (
            page_ids,
            {pid: page_map[pid] for pid in page_ids if pid in page_map},
        ),
    )
    monkeypatch.setattr(core_agent, "_load_page_image_bytes", fake_load_page_image_bytes)

    events = asyncio.run(
        _collect_events(
            core_agent.run_agent_query_deep(
                db=SimpleNamespace(),
                project_id="project-1",
                query="verify panel schedule voltage",
                history_messages=[],
                viewing_context=None,
            )
        )
    )

    assert not any(event.get("type") == "error" for event in events)

    deep_trace_event = next(
        event for event in events if event.get("type") == "tool_result" and event.get("tool") == "deep_mode_trace"
    )
    assert deep_trace_event["result"]["execution_summary"]["fallback_used"] is True
    assert deep_trace_event["result"]["execution_summary"]["pass_total"] == 0

    done_event = next(event for event in events if event.get("type") == "done")
    assert done_event["usage"] == {"inputTokens": 0, "outputTokens": 0}
    assert done_event["findings"] == []
