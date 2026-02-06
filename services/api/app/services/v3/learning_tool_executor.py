"""Tool executor for the Learning agent (V3)."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from app.models.experience_file import ExperienceFile
from app.models.page import Page
from app.models.pointer import Pointer
from app.services.core.reground import trigger_reground
from app.services.providers.voyage import embed_pointer
from app.services.utils.search import search_pointers
from app.types.session import LiveSession

logger = logging.getLogger(__name__)


def _parse_reference_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                pass
        return [item.strip() for item in raw.split(",") if item.strip()]
    return []


async def execute_learning_tool(
    tool_name: str,
    tool_args: dict[str, Any],
    session: LiveSession,
    db: DBSession,
) -> dict[str, Any] | list[dict[str, Any]]:
    if tool_name == "read_file":
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

    if tool_name == "write_file":
        path = str(tool_args.get("path") or "").strip()
        content = str(tool_args.get("content") or "")
        if not path:
            return {"error": "Path is required"}

        db.execute(
            text(
                """
                INSERT INTO experience_files (id, project_id, path, content, updated_by_session)
                VALUES (:id, :project_id, :path, :content, :updated_by_session)
                ON CONFLICT (project_id, path)
                DO UPDATE SET
                    content = EXCLUDED.content,
                    updated_by_session = EXCLUDED.updated_by_session,
                    updated_at = now()
                """
            ),
            {
                "id": str(uuid4()),
                "project_id": str(session.project_id),
                "path": path,
                "content": content,
                "updated_by_session": str(session.session_id),
            },
        )
        db.commit()
        return {"path": path, "status": "written"}

    if tool_name == "edit_file":
        path = str(tool_args.get("path") or "").strip()
        old_text = str(tool_args.get("old_text") or "")
        new_text = str(tool_args.get("new_text") or "")
        row = (
            db.query(ExperienceFile)
            .filter(ExperienceFile.project_id == str(session.project_id))
            .filter(ExperienceFile.path == path)
            .first()
        )
        if not row:
            return {"error": "Experience file not found", "path": path}
        if old_text not in (row.content or ""):
            return {"error": "Old text not found in file", "path": path}

        updated = (row.content or "").replace(old_text, new_text)
        db.execute(
            text(
                """
                INSERT INTO experience_files (id, project_id, path, content, updated_by_session)
                VALUES (:id, :project_id, :path, :content, :updated_by_session)
                ON CONFLICT (project_id, path)
                DO UPDATE SET
                    content = EXCLUDED.content,
                    updated_by_session = EXCLUDED.updated_by_session,
                    updated_at = now()
                """
            ),
            {
                "id": str(uuid4()),
                "project_id": str(session.project_id),
                "path": path,
                "content": updated,
                "updated_by_session": str(session.session_id),
            },
        )
        db.commit()
        return {"path": path, "status": "edited"}

    if tool_name == "list_files":
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
            "enrichment_metadata": pointer.enrichment_metadata or {},
        }

    if tool_name == "read_page":
        page_id = str(tool_args.get("page_id") or "")
        page = db.query(Page).filter(Page.id == page_id).first()
        if not page:
            return {"error": "Page not found"}
        return {
            "page_id": page.id,
            "page_name": page.page_name,
            "sheet_reflection": page.sheet_reflection or "",
            "cross_references": page.cross_references or [],
            "page_type": page.page_type,
        }

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

    if tool_name == "edit_pointer":
        pointer_id = str(tool_args.get("pointer_id") or "")
        field = str(tool_args.get("field") or "")
        new_content = tool_args.get("new_content")

        pointer = db.query(Pointer).filter(Pointer.id == pointer_id).first()
        if not pointer:
            return {"error": "Pointer not found"}

        if field == "description":
            pointer.description = str(new_content or "")
            try:
                embedding = await embed_pointer(
                    pointer.title,
                    pointer.description,
                    pointer.text_spans or [],
                )
                pointer.embedding = embedding
                pointer.needs_embedding = False
            except Exception as exc:
                logger.warning("Failed to regenerate embedding for %s: %s", pointer_id, exc)
                pointer.needs_embedding = True
        elif field == "cross_references":
            pointer.cross_references = _parse_reference_list(new_content)
        else:
            return {"error": "Invalid field", "field": field}

        db.commit()
        return {
            "pointer_id": pointer.id,
            "field": field,
            "status": "updated",
        }

    if tool_name == "edit_page":
        page_id = str(tool_args.get("page_id") or "")
        field = str(tool_args.get("field") or "")
        new_content = tool_args.get("new_content")

        page = db.query(Page).filter(Page.id == page_id).first()
        if not page:
            return {"error": "Page not found"}

        if field == "sheet_reflection":
            page.sheet_reflection = str(new_content or "")
        elif field == "cross_references":
            page.cross_references = _parse_reference_list(new_content)
        else:
            return {"error": "Invalid field", "field": field}

        db.commit()
        return {
            "page_id": page.id,
            "field": field,
            "status": "updated",
        }

    if tool_name == "update_cross_references":
        pointer_id = str(tool_args.get("pointer_id") or "")
        references = tool_args.get("references")
        pointer = db.query(Pointer).filter(Pointer.id == pointer_id).first()
        if not pointer:
            return {"error": "Pointer not found"}

        pointer.cross_references = _parse_reference_list(references)
        db.commit()
        return {"pointer_id": pointer.id, "status": "updated"}

    if tool_name == "trigger_reground":
        page_id = str(tool_args.get("page_id") or "")
        instruction = str(tool_args.get("instruction") or "")
        try:
            pointer_ids = await trigger_reground(page_id, instruction, db)
            return {"page_id": page_id, "new_pointer_ids": pointer_ids}
        except Exception as exc:
            logger.warning("Re-ground failed for page %s: %s", page_id, exc)
            return {"error": "Re-ground failed", "page_id": page_id, "detail": str(exc)}

    return {"error": f"Unknown tool: {tool_name}"}
