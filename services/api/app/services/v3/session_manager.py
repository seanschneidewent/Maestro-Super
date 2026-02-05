"""SessionManager for Maestro V3 (in-memory hot layer with Supabase checkpoints)."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session as DBSession

from app.database.session import SessionLocal
from app.models.session import MaestroSession
from app.types.session import LiveSession, WorkspaceState

logger = logging.getLogger(__name__)


def _to_uuid(value: str | UUID) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _workspace_state_from_dict(data: dict | None) -> WorkspaceState:
    data = data or {}
    return WorkspaceState(
        displayed_pages=list(data.get("displayed_pages", []) or []),
        highlighted_pointers=list(data.get("highlighted_pointers", []) or []),
        pinned_pages=list(data.get("pinned_pages", []) or []),
    )


class SessionManager:
    """Singleton manager for Maestro sessions."""

    _instance: Optional["SessionManager"] = None

    def __init__(self) -> None:
        self._sessions: dict[UUID, LiveSession] = {}

    @classmethod
    def instance(cls) -> "SessionManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def create_session(
        self,
        project_id: str | UUID,
        user_id: str,
        session_type: str,
        workspace_name: str | None,
        db: DBSession,
    ) -> LiveSession:
        session_id = uuid4()
        project_uuid = _to_uuid(project_id)
        session_row = MaestroSession(
            id=str(session_id),
            project_id=str(project_uuid),
            user_id=user_id,
            session_type=session_type,
            workspace_name=workspace_name,
            workspace_state=None if session_type == "telegram" else {
                "displayed_pages": [],
                "highlighted_pointers": [],
                "pinned_pages": [],
            },
            status="active",
        )
        db.add(session_row)
        db.commit()
        db.refresh(session_row)

        live = LiveSession(
            session_id=session_id,
            project_id=project_uuid,
            user_id=user_id,
            session_type=session_type,
            maestro_messages=list(session_row.maestro_messages or []),
            learning_messages=list(session_row.learning_messages or []),
            workspace_state=None
            if session_type == "telegram"
            else _workspace_state_from_dict(session_row.workspace_state),
            dirty=False,
            last_active=time.time(),
        )
        self._sessions[live.session_id] = live
        return live

    def get_session(self, session_id: str | UUID, db: DBSession) -> LiveSession | None:
        session_uuid = _to_uuid(session_id)
        cached = self._sessions.get(session_uuid)
        if cached:
            cached.last_active = time.time()
            return cached

        row = (
            db.query(MaestroSession)
            .filter(MaestroSession.id == str(session_uuid))
            .first()
        )
        if not row:
            return None

        live = LiveSession(
            session_id=session_uuid,
            project_id=_to_uuid(row.project_id),
            user_id=row.user_id,
            session_type=row.session_type,
            maestro_messages=list(row.maestro_messages or []),
            learning_messages=list(row.learning_messages or []),
            workspace_state=None
            if row.session_type == "telegram"
            else _workspace_state_from_dict(row.workspace_state),
            dirty=False,
            last_active=time.time(),
        )
        self._sessions[live.session_id] = live
        return live

    def get_or_create_telegram_session(
        self,
        project_id: str | UUID,
        user_id: str,
        db: DBSession,
    ) -> LiveSession:
        project_uuid = _to_uuid(project_id)
        row = (
            db.query(MaestroSession)
            .filter(MaestroSession.project_id == str(project_uuid))
            .filter(MaestroSession.user_id == user_id)
            .filter(MaestroSession.session_type == "telegram")
            .filter(MaestroSession.status == "active")
            .order_by(MaestroSession.updated_at.desc())
            .first()
        )
        if row:
            return self.get_session(row.id, db) or self.create_session(
                project_uuid, user_id, "telegram", None, db
            )
        return self.create_session(project_uuid, user_id, "telegram", None, db)

    def checkpoint_session(self, session: LiveSession, db: DBSession) -> None:
        row = (
            db.query(MaestroSession)
            .filter(MaestroSession.id == str(session.session_id))
            .first()
        )
        if not row:
            logger.warning("Session %s missing in DB during checkpoint", session.session_id)
            return

        row.maestro_messages = session.maestro_messages
        row.learning_messages = session.learning_messages
        if session.session_type == "telegram":
            row.workspace_state = None
        else:
            row.workspace_state = asdict(session.workspace_state) if session.workspace_state else None

        row.last_active_at = datetime.now(timezone.utc)
        db.commit()
        session.dirty = False

    def checkpoint_all_dirty(self, db: DBSession) -> int:
        dirty_sessions = [s for s in self._sessions.values() if s.dirty]
        for session in dirty_sessions:
            try:
                self.checkpoint_session(session, db)
            except Exception as exc:
                logger.warning("Failed to checkpoint session %s: %s", session.session_id, exc)
        return len(dirty_sessions)

    def rehydrate_active_sessions(self, db: DBSession) -> int:
        rows = (
            db.query(MaestroSession)
            .filter(MaestroSession.status == "active")
            .all()
        )
        count = 0
        for row in rows:
            try:
                session_uuid = _to_uuid(row.id)
            except Exception:
                continue
            if session_uuid in self._sessions:
                continue
            live = LiveSession(
                session_id=session_uuid,
                project_id=_to_uuid(row.project_id),
                user_id=row.user_id,
                session_type=row.session_type,
                maestro_messages=list(row.maestro_messages or []),
                learning_messages=list(row.learning_messages or []),
                workspace_state=None
                if row.session_type == "telegram"
                else _workspace_state_from_dict(row.workspace_state),
                dirty=False,
                last_active=time.time(),
            )
            self._sessions[session_uuid] = live
            count += 1
        if count:
            logger.info("Rehydrated %d active sessions", count)
        return count

    def close_session(self, session_id: str | UUID, db: DBSession) -> None:
        session_uuid = _to_uuid(session_id)
        session = self._sessions.get(session_uuid)
        if session:
            try:
                self.checkpoint_session(session, db)
            except Exception as exc:
                logger.warning("Failed to checkpoint session %s on close: %s", session_uuid, exc)
        row = (
            db.query(MaestroSession)
            .filter(MaestroSession.id == str(session_uuid))
            .first()
        )
        if row:
            row.status = "closed"
            row.updated_at = datetime.now(timezone.utc)
            db.commit()
        self._sessions.pop(session_uuid, None)

    def reset_session(self, session_id: str | UUID, db: DBSession) -> LiveSession:
        session_uuid = _to_uuid(session_id)
        session = self.get_session(session_uuid, db)
        if not session:
            raise ValueError("Session not found")
        self.close_session(session_uuid, db)
        workspace_name = None
        if session.session_type == "workspace":
            workspace_name = "Workspace"
        return self.create_session(
            session.project_id,
            session.user_id,
            session.session_type,
            workspace_name,
            db,
        )

    def compact_session(self, session: LiveSession, db: DBSession) -> None:
        def compact_messages(messages: list[dict], keep: int = 6) -> list[dict]:
            if len(messages) <= keep:
                return messages
            older = messages[:-keep]
            recent = messages[-keep:]
            summary_parts: list[str] = []
            for msg in older:
                role = msg.get("role")
                content = msg.get("content")
                if not content:
                    continue
                summary_parts.append(f"{role}: {str(content).strip()}")
            summary_text = " | ".join(summary_parts)
            summary_text = summary_text[:1200]
            summary_msg = {
                "role": "system",
                "content": f"Summary of earlier conversation: {summary_text}",
            }
            return [summary_msg, *recent]

        session.maestro_messages = compact_messages(session.maestro_messages)
        session.learning_messages = compact_messages(session.learning_messages)
        session.dirty = True
        self.checkpoint_session(session, db)


async def run_checkpoint_loop(interval_seconds: float = 30.0) -> None:
    """Background loop to checkpoint dirty sessions."""
    manager = SessionManager.instance()
    while True:
        db = SessionLocal()
        try:
            manager.checkpoint_all_dirty(db)
        finally:
            db.close()
        await asyncio.sleep(interval_seconds)
