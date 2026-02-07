"""Tool executor for Maestro V3."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import case, or_
from sqlalchemy.orm import Session as DBSession

from app.models.discipline import Discipline
from app.models.experience_file import ExperienceFile
from app.models.page import Page
from app.models.pointer import Pointer
from app.models.session import MaestroSession
from app.services.utils.search import search_pointers
from app.types.session import LiveSession

logger = logging.getLogger(__name__)


def _coerce_limit(raw: Any, default: int = 10, min_value: int = 1, max_value: int = 50) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(min_value, min(value, max_value))


def _pointer_result_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "pointer_id": item.get("pointer_id"),
        "title": item.get("title"),
        "description_snippet": item.get("relevance_snippet"),
        "page_name": item.get("page_name"),
        "page_id": item.get("page_id"),
        "confidence": item.get("score"),
    }


def _fallback_search_pointers(
    db: DBSession,
    project_id: str,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    query_text = query.strip()
    token_patterns = [f"%{token}%" for token in query_text.split() if token]
    full_pattern = f"%{query_text}%" if query_text else None

    fallback_query = (
        db.query(Pointer, Page)
        .join(Page, Pointer.page_id == Page.id)
        .join(Discipline, Page.discipline_id == Discipline.id)
        .filter(Discipline.project_id == project_id)
    )

    filters = []
    if full_pattern:
        filters.extend([Pointer.title.ilike(full_pattern), Pointer.description.ilike(full_pattern)])
    for pattern in token_patterns:
        filters.extend([Pointer.title.ilike(pattern), Pointer.description.ilike(pattern)])
    if filters:
        fallback_query = fallback_query.filter(or_(*filters))

    if full_pattern:
        relevance_sort = case(
            (
                or_(Pointer.title.ilike(full_pattern), Pointer.description.ilike(full_pattern)),
                1,
            ),
            else_=0,
        ).desc()
        fallback_query = fallback_query.order_by(relevance_sort, Pointer.updated_at.desc())
    else:
        fallback_query = fallback_query.order_by(Pointer.updated_at.desc())

    rows = fallback_query.limit(limit).all()
    return [
        {
            "pointer_id": pointer.id,
            "title": pointer.title,
            "page_id": pointer.page_id,
            "page_name": page.page_name if page else None,
            "relevance_snippet": (pointer.description or "")[:200],
            "score": None,
        }
        for pointer, page in rows
    ]


async def execute_maestro_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    session: LiveSession,
    db: DBSession,
) -> dict[str, Any]:
    if tool_name == "search_knowledge":
        query = str(tool_args.get("query") or "").strip()
        limit = _coerce_limit(tool_args.get("limit"), default=10)
        hybrid_results: list[dict[str, Any]] = []
        fallback_results: list[dict[str, Any]] = []
        used_fallback = False

        if query:
            try:
                hybrid_results = await search_pointers(
                    db=db,
                    query=query,
                    project_id=str(session.project_id),
                    limit=limit,
                )
            except Exception as exc:
                logger.warning(
                    "search_knowledge hybrid search failed project_id=%s query=%r limit=%d: %s",
                    str(session.project_id),
                    query,
                    limit,
                    exc,
                )

        if not hybrid_results:
            try:
                fallback_results = _fallback_search_pointers(
                    db=db,
                    project_id=str(session.project_id),
                    query=query,
                    limit=limit,
                )
            except Exception as exc:
                logger.warning(
                    "search_knowledge fallback search failed project_id=%s query=%r limit=%d: %s",
                    str(session.project_id),
                    query,
                    limit,
                    exc,
                )
                fallback_results = []
            used_fallback = bool(fallback_results)

        selected_results = hybrid_results or fallback_results
        payload_results = [_pointer_result_payload(item) for item in selected_results]
        if used_fallback:
            logger.warning(
                "search_knowledge fallback engaged",
                extra={
                    "event": "v3_search_fallback",
                    "project_id": str(session.project_id),
                    "query": query,
                    "hybrid_count": len(hybrid_results),
                    "fallback_count": len(fallback_results),
                    "used_fallback": used_fallback,
                },
            )
        logger.info(
            "search_knowledge project_id=%s query=%r limit=%d hybrid_count=%d fallback_count=%d used_fallback=%s",
            str(session.project_id),
            query,
            limit,
            len(hybrid_results),
            len(fallback_results),
            used_fallback,
        )
        return {
            "query": query,
            "count": len(payload_results),
            "used_fallback": used_fallback,
            "results": payload_results,
        }

    if tool_name == "read_pointer":
        pointer_id = str(tool_args.get("pointer_id") or "")
        pointer = db.query(Pointer).filter(Pointer.id == pointer_id).first()
        if not pointer:
            return {"error": "Pointer not found"}
        return {
            "pointer_id": pointer.id,
            "title": pointer.title,
            "description": pointer.description,
            "cross_references": pointer.cross_references or [],
        }

    if tool_name == "read_experience":
        path = str(tool_args.get("path") or "")
        row = (
            db.query(ExperienceFile)
            .filter(ExperienceFile.project_id == str(session.project_id))
            .filter(ExperienceFile.path == path)
            .first()
        )
        if not row:
            return {"error": "Experience file not found", "path": path}
        return {"path": row.path, "content": row.content}

    if tool_name == "list_experience":
        rows = (
            db.query(ExperienceFile)
            .filter(ExperienceFile.project_id == str(session.project_id))
            .order_by(ExperienceFile.path.asc())
            .all()
        )
        results = [
            {
                "path": row.path,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]
        return {"results": results, "count": len(results)}

    if tool_name == "add_pages":
        page_ids = [str(pid) for pid in (tool_args.get("page_ids") or []) if pid]
        if session.workspace_state is None:
            return {"error": "Workspace session required"}

        existing = set(session.workspace_state.displayed_pages)
        for pid in page_ids:
            if pid not in existing:
                session.workspace_state.displayed_pages.append(pid)
        pages = (
            db.query(Page)
            .filter(Page.id.in_(page_ids))
            .all()
        )
        return {
            "page_ids": page_ids,
            "pages": [
                {
                    "page_id": p.id,
                    "page_name": p.page_name,
                    "file_path": p.page_image_path or p.file_path,
                    "discipline_id": p.discipline_id,
                }
                for p in pages
            ],
        }

    if tool_name == "remove_pages":
        page_ids = [str(pid) for pid in (tool_args.get("page_ids") or []) if pid]
        if session.workspace_state is None:
            return {"error": "Workspace session required"}
        session.workspace_state.displayed_pages = [
            pid for pid in session.workspace_state.displayed_pages if pid not in page_ids
        ]
        return {"page_ids": page_ids}

    if tool_name == "highlight_pointers":
        pointer_ids = [str(pid) for pid in (tool_args.get("pointer_ids") or []) if pid]
        if session.workspace_state is None:
            return {"error": "Workspace session required"}
        session.workspace_state.highlighted_pointers = pointer_ids
        pointers = (
            db.query(Pointer)
            .filter(Pointer.id.in_(pointer_ids))
            .all()
        )
        return {
            "pointer_ids": pointer_ids,
            "pointers": [
                {
                    "pointer_id": p.id,
                    "title": p.title,
                    "page_id": p.page_id,
                    "bbox_x": p.bbox_x,
                    "bbox_y": p.bbox_y,
                    "bbox_width": p.bbox_width,
                    "bbox_height": p.bbox_height,
                }
                for p in pointers
            ],
        }

    if tool_name == "pin_page":
        page_id = str(tool_args.get("page_id") or "")
        if session.workspace_state is None:
            return {"error": "Workspace session required"}
        if page_id and page_id not in session.workspace_state.pinned_pages:
            session.workspace_state.pinned_pages.append(page_id)
        return {"page_id": page_id, "pinned_pages": list(session.workspace_state.pinned_pages)}

    # Telegram-only tools
    if tool_name == "list_workspaces":
        rows = (
            db.query(MaestroSession)
            .filter(MaestroSession.project_id == str(session.project_id))
            .filter(MaestroSession.session_type == "workspace")
            .filter(MaestroSession.status == "active")
            .order_by(MaestroSession.updated_at.desc())
            .all()
        )
        results = [
            {
                "session_id": row.id,
                "workspace_name": row.workspace_name,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]
        return {"results": results, "count": len(results)}

    if tool_name == "workspace_action":
        action = str(tool_args.get("action") or "")
        target_session_id = str(tool_args.get("session_id") or "")
        page_ids = [str(pid) for pid in (tool_args.get("page_ids") or []) if pid]
        pointer_ids = [str(pid) for pid in (tool_args.get("pointer_ids") or []) if pid]

        target = (
            db.query(MaestroSession)
            .filter(MaestroSession.id == target_session_id)
            .first()
        )
        if not target:
            return {"error": "Workspace not found"}
        workspace_state = target.workspace_state or {
            "displayed_pages": [],
            "highlighted_pointers": [],
            "pinned_pages": [],
        }

        if action == "add_pages":
            for pid in page_ids:
                if pid not in workspace_state.get("displayed_pages", []):
                    workspace_state.setdefault("displayed_pages", []).append(pid)
        elif action == "remove_pages":
            workspace_state["displayed_pages"] = [
                pid for pid in workspace_state.get("displayed_pages", []) if pid not in page_ids
            ]
        elif action == "highlight_pointers":
            workspace_state["highlighted_pointers"] = pointer_ids
        elif action == "pin_page":
            if page_ids:
                page_id = page_ids[0]
                if page_id not in workspace_state.get("pinned_pages", []):
                    workspace_state.setdefault("pinned_pages", []).append(page_id)

        target.workspace_state = workspace_state
        db.commit()
        return {"action": action, "workspace_state": workspace_state}

    return {"error": f"Unknown tool: {tool_name}"}
