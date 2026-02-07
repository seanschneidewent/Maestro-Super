"""Regression tests for V3 session SSE streaming behavior."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.routers import v3_sessions


def _parse_sse_events(raw_body: str) -> list[dict]:
    events: list[dict] = []
    for block in raw_body.split("\n\n"):
        text = block.strip()
        if not text or text.startswith(":"):
            continue
        for line in text.splitlines():
            if not line.startswith("data: "):
                continue
            payload = line[len("data: ") :].strip()
            if not payload:
                continue
            events.append(json.loads(payload))
    return events


def _create_workspace_session(client: TestClient) -> str:
    project = client.post("/projects", json={"name": "SSE Test Project"}).json()
    response = client.post(
        "/v3/sessions",
        json={"project_id": project["id"], "session_type": "workspace"},
    )
    assert response.status_code == 200
    return response.json()["session_id"]


def test_v3_query_stream_emits_error_event_when_turn_crashes(
    client: TestClient,
    monkeypatch,
) -> None:
    session_id = _create_workspace_session(client)

    async def _failing_turn(*_args, **_kwargs):
        yield {"type": "token", "content": "partial"}
        raise RuntimeError("simulated stream failure")

    monkeypatch.setattr(v3_sessions, "run_maestro_turn", _failing_turn)

    response = client.post(
        f"/v3/sessions/{session_id}/query",
        json={"message": "hello maestro"},
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    event_types = [event.get("type") for event in events]

    assert "token" in event_types
    assert "error" in event_types
    assert any(
        event.get("type") == "error"
        and "interrupted" in str(event.get("message", "")).lower()
        for event in events
    )
    assert any(
        event.get("type") == "error"
        and event.get("code") == "stream_interrupted"
        for event in events
    )


def test_v3_query_stream_has_sse_antibuffering_headers(
    client: TestClient,
    monkeypatch,
) -> None:
    session_id = _create_workspace_session(client)

    async def _successful_turn(*_args, **_kwargs):
        yield {"type": "token", "content": "ok"}
        yield {"type": "done"}

    monkeypatch.setattr(v3_sessions, "run_maestro_turn", _successful_turn)

    response = client.post(
        f"/v3/sessions/{session_id}/query",
        json={"message": "quick ping"},
    )

    assert response.status_code == 200
    assert response.headers.get("x-accel-buffering") == "no"
    assert "no-transform" in (response.headers.get("cache-control") or "")
