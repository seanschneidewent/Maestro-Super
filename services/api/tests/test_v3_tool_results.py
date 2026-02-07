from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.models.experience_file import ExperienceFile
from app.models.session import MaestroSession
from app.services.v3.maestro_agent import _search_knowledge_items
from app.services.v3.providers import _gemini_messages
from app.services.v3.tool_executor import execute_maestro_tool


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self._limit = None

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def limit(self, value):
        self._limit = value
        return self

    def all(self):
        if self._limit is None:
            return self._rows
        return self._rows[: self._limit]

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, *, experience_rows=None, workspace_rows=None):
        self.experience_rows = experience_rows or []
        self.workspace_rows = workspace_rows or []

    def query(self, *entities):
        if len(entities) == 1 and entities[0] is ExperienceFile:
            return _FakeQuery(self.experience_rows)
        if len(entities) == 1 and entities[0] is MaestroSession:
            return _FakeQuery(self.workspace_rows)
        return _FakeQuery([])


def test_search_knowledge_returns_dict_envelope_from_hybrid(monkeypatch):
    async def _fake_search_pointers(**kwargs):
        return [
            {
                "pointer_id": "p-1",
                "title": "Anchor Bolt",
                "relevance_snippet": "Use 3/4 in anchor bolt",
                "page_name": "S1.01",
                "page_id": "pg-1",
                "score": 0.86,
            }
        ]

    monkeypatch.setattr("app.services.v3.tool_executor.search_pointers", _fake_search_pointers)
    session = SimpleNamespace(project_id="proj-1", workspace_state=None)

    result = asyncio.run(
        execute_maestro_tool("search_knowledge", {"query": "anchor bolt"}, session, _FakeDB())
    )

    assert isinstance(result, dict)
    assert result["used_fallback"] is False
    assert result["count"] == 1
    assert result["results"][0]["pointer_id"] == "p-1"
    assert result["results"][0]["description_snippet"] == "Use 3/4 in anchor bolt"


def test_search_knowledge_uses_fallback_when_hybrid_empty(monkeypatch):
    async def _fake_search_pointers(**kwargs):
        return []

    def _fake_fallback(*args, **kwargs):
        return [
            {
                "pointer_id": "p-fallback",
                "title": "Footing",
                "relevance_snippet": "Fallback pointer",
                "page_name": "S2.01",
                "page_id": "pg-2",
                "score": None,
            }
        ]

    monkeypatch.setattr("app.services.v3.tool_executor.search_pointers", _fake_search_pointers)
    monkeypatch.setattr("app.services.v3.tool_executor._fallback_search_pointers", _fake_fallback)
    session = SimpleNamespace(project_id="proj-1", workspace_state=None)

    result = asyncio.run(
        execute_maestro_tool("search_knowledge", {"query": "footing"}, session, _FakeDB())
    )

    assert result["used_fallback"] is True
    assert result["count"] == 1
    assert result["results"][0]["pointer_id"] == "p-fallback"


def test_search_knowledge_uses_fallback_when_hybrid_raises(monkeypatch):
    async def _broken_search_pointers(**kwargs):
        raise RuntimeError("hybrid unavailable")

    def _fake_fallback(*args, **kwargs):
        return [
            {
                "pointer_id": "p-fallback",
                "title": "Fallback Match",
                "relevance_snippet": "Recovered by fallback",
                "page_name": "A1.01",
                "page_id": "pg-9",
                "score": None,
            }
        ]

    monkeypatch.setattr("app.services.v3.tool_executor.search_pointers", _broken_search_pointers)
    monkeypatch.setattr("app.services.v3.tool_executor._fallback_search_pointers", _fake_fallback)
    session = SimpleNamespace(project_id="proj-1", workspace_state=None)

    result = asyncio.run(
        execute_maestro_tool("search_knowledge", {"query": "equipment"}, session, _FakeDB())
    )

    assert result["used_fallback"] is True
    assert result["count"] == 1
    assert result["results"][0]["pointer_id"] == "p-fallback"


def test_search_knowledge_coerces_bad_limit(monkeypatch):
    captured = {}

    async def _fake_search_pointers(**kwargs):
        captured["limit"] = kwargs.get("limit")
        return []

    monkeypatch.setattr("app.services.v3.tool_executor.search_pointers", _fake_search_pointers)
    monkeypatch.setattr("app.services.v3.tool_executor._fallback_search_pointers", lambda *a, **k: [])
    session = SimpleNamespace(project_id="proj-1", workspace_state=None)

    result = asyncio.run(
        execute_maestro_tool("search_knowledge", {"query": "equipment", "limit": "not-a-number"}, session, _FakeDB())
    )

    assert captured["limit"] == 10
    assert result["count"] == 0
    assert result["used_fallback"] is False


def test_list_tools_return_dict_envelopes():
    now = datetime.now(timezone.utc)
    db = _FakeDB(
        experience_rows=[SimpleNamespace(path="schedule.md", updated_at=now)],
        workspace_rows=[SimpleNamespace(id="sess-1", workspace_name="WS1", updated_at=now)],
    )
    session = SimpleNamespace(project_id="proj-1", workspace_state=None)

    list_exp = asyncio.run(execute_maestro_tool("list_experience", {}, session, db))
    list_ws = asyncio.run(execute_maestro_tool("list_workspaces", {}, session, db))

    assert list_exp["count"] == 1
    assert isinstance(list_exp["results"], list)
    assert list_exp["results"][0]["path"] == "schedule.md"
    assert list_ws["count"] == 1
    assert isinstance(list_ws["results"], list)
    assert list_ws["results"][0]["session_id"] == "sess-1"


def test_gemini_messages_wraps_non_dict_tool_payloads():
    for content, expected in [
        ([], {"results": []}),
        ("[]", {"results": []}),
        ("123", {"results": 123}),
        ({"ok": True}, {"ok": True}),
    ]:
        _, contents = _gemini_messages(
            [
                {"role": "system", "content": "sys"},
                {"role": "tool", "name": "search_knowledge", "content": content},
            ]
        )
        response = contents[0].parts[0].function_response.response
        assert response == expected


def test_search_knowledge_item_extraction_supports_new_and_legacy_shapes():
    wrapped = {"results": [{"pointer_id": "a"}, {"pointer_id": "b"}]}
    legacy = [{"pointer_id": "c"}]

    assert _search_knowledge_items(wrapped) == [{"pointer_id": "a"}, {"pointer_id": "b"}]
    assert _search_knowledge_items(legacy) == [{"pointer_id": "c"}]
    assert _search_knowledge_items({"results": "invalid"}) == []
