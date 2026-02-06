"""Tool executor for Maestro V3."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session as DBSession

from app.models.experience_file import ExperienceFile
from app.models.page import Page
from app.models.pointer import Pointer
from app.models.session import MaestroSession
from app.services.utils.search import search_pointers
from app.types.session import LiveSession


async def execute_maestro_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    session: LiveSession,
    db: DBSession,
) -> dict[str, Any] | list[dict[str, Any]]:
    if tool_name == "search_knowledge":
        query = str(tool_args.get("query") or "").strip()
        limit = int(tool_args.get("limit") or 10)
        results = await search_pointers(
            db=db,
            query=query,
            project_id=str(session.project_id),
            limit=limit,
        )
        return [
            {
                "pointer_id": r.get("pointer_id"),
                "title": r.get("title"),
                "description_snippet": r.get("relevance_snippet"),
                "page_name": r.get("page_name"),
                "page_id": r.get("page_id"),
                "confidence": r.get("score"),
            }
            for r in results
        ]

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
        return [
            {
                "path": row.path,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]

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
        return [
            {
                "session_id": row.id,
                "workspace_name": row.workspace_name,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in rows
        ]

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
