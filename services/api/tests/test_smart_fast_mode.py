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
from app.services.providers.gemini import select_pages_smart


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

    monkeypatch.setattr("app.services.tools.get_project_structure_summary", fake_get_project_structure_summary)
    monkeypatch.setattr("app.services.tools.search_pages", fake_search_pages)
    monkeypatch.setattr("app.services.tools.select_pages", fake_select_pages)
    monkeypatch.setattr("app.services.utils.search.search_pages_and_regions", fake_search_pages_and_regions)
    monkeypatch.setattr("app.services.providers.gemini.select_pages_smart", fake_select_pages_smart)
    monkeypatch.setattr(core_agent, "_expand_with_cross_reference_pages", lambda db, project_id, page_ids: page_ids)
    monkeypatch.setattr(
        core_agent,
        "_order_page_ids",
        lambda db, page_ids: (
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

    monkeypatch.setattr("app.services.tools.get_project_structure_summary", fake_get_project_structure_summary)
    monkeypatch.setattr("app.services.tools.search_pages", fake_search_pages)
    monkeypatch.setattr("app.services.tools.select_pages", fake_select_pages)
    monkeypatch.setattr("app.services.utils.search.search_pages_and_regions", fake_search_pages_and_regions)
    monkeypatch.setattr("app.services.providers.gemini.select_pages_smart", fake_select_pages_smart)
    monkeypatch.setattr(core_agent, "_expand_with_cross_reference_pages", lambda db, project_id, page_ids: page_ids)
    monkeypatch.setattr(
        core_agent,
        "_order_page_ids",
        lambda db, page_ids: (
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
