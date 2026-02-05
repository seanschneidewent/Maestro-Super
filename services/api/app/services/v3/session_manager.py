"""SessionManager for Maestro V3 (in-memory hot layer with Supabase checkpoints)."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy.orm import Session as DBSession

from app.database.session import SessionLocal
from app.models.session import MaestroSession
from app.services.v3.learning_agent import run_learning_worker
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
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _spawn_learning_worker(self, session: LiveSession) -> None:
        if session.learning_task and not session.learning_task.done():
            return
        loop = self._loop
        if loop is None or not loop.is_running():
            logger.debug("Learning worker loop not available for session %s", session.session_id)
            return

        def _create_task() -> None:
            if session.learning_task and not session.learning_task.done():
                return
            task = loop.create_task(run_learning_worker(session, SessionLocal))
            session.learning_task = task
            session.learning_task_loop = loop

        try:
            if asyncio.get_running_loop() is loop:
                _create_task()
            else:
                loop.call_soon_threadsafe(_create_task)
        except RuntimeError:
            loop.call_soon_threadsafe(_create_task)

    def _cancel_learning_worker(self, session: LiveSession) -> None:
        task = session.learning_task
        if not task or task.done():
            return
        loop = session.learning_task_loop or self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(task.cancel)
        else:
            task.cancel()
        session.learning_task = None
        session.learning_task_loop = None

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
            workspace_name=workspace_name,
            maestro_messages=list(session_row.maestro_messages or []),
            learning_messages=list(session_row.learning_messages or []),
            workspace_state=None
            if session_type == "telegram"
            else _workspace_state_from_dict(session_row.workspace_state),
            dirty=False,
            last_active=time.time(),
        )
        self._sessions[live.session_id] = live
        self._spawn_learning_worker(live)
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

        if row.status != "active":
            row.status = "active"
            row.last_active_at = datetime.now(timezone.utc)
            row.updated_at = datetime.now(timezone.utc)
            db.commit()

        live = LiveSession(
            session_id=session_uuid,
            project_id=_to_uuid(row.project_id),
            user_id=row.user_id,
            session_type=row.session_type,
            workspace_name=row.workspace_name,
            maestro_messages=list(row.maestro_messages or []),
            learning_messages=list(row.learning_messages or []),
            workspace_state=None
            if row.session_type == "telegram"
            else _workspace_state_from_dict(row.workspace_state),
            dirty=False,
            last_active=time.time(),
        )
        self._sessions[live.session_id] = live
        self._spawn_learning_worker(live)
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
        row.workspace_name = session.workspace_name
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
                workspace_name=row.workspace_name,
                maestro_messages=list(row.maestro_messages or []),
                learning_messages=list(row.learning_messages or []),
                workspace_state=None
                if row.session_type == "telegram"
                else _workspace_state_from_dict(row.workspace_state),
                dirty=False,
                last_active=time.time(),
            )
            self._sessions[session_uuid] = live
            self._spawn_learning_worker(live)
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
            self._cancel_learning_worker(session)
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
            workspace_name = session.workspace_name or "Workspace"
        return self.create_session(
            session.project_id,
            session.user_id,
            session.session_type,
            workspace_name,
            db,
        )

    def _evict_session(self, session_id: UUID) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            self._cancel_learning_worker(session)

    def _cleanup_idle_sessions(self, db: DBSession) -> None:
        now = datetime.now(timezone.utc)
        idle_cutoff = now - timedelta(hours=24)
        close_cutoff = now - timedelta(days=7)

        to_idle = (
            db.query(MaestroSession)
            .filter(MaestroSession.status == "active")
            .filter(MaestroSession.last_active_at < idle_cutoff)
            .all()
        )
        to_close = (
            db.query(MaestroSession)
            .filter(MaestroSession.status == "idle")
            .filter(MaestroSession.last_active_at < close_cutoff)
            .all()
        )

        if not to_idle and not to_close:
            return

        for row in to_idle:
            row.status = "idle"
            row.updated_at = now

        for row in to_close:
            row.status = "closed"
            row.updated_at = now

        db.commit()

        for row in [*to_idle, *to_close]:
            try:
                self._evict_session(_to_uuid(row.id))
            except Exception:
                continue

    def list_sessions(
        self,
        project_id: str | UUID,
        session_type: str | None,
        status: list[str] | None,
        db: DBSession,
    ) -> list[MaestroSession]:
        project_uuid = _to_uuid(project_id)
        self._cleanup_idle_sessions(db)
        query = db.query(MaestroSession).filter(MaestroSession.project_id == str(project_uuid))
        if session_type:
            query = query.filter(MaestroSession.session_type == session_type)
        if status:
            query = query.filter(MaestroSession.status.in_(status))
        return query.order_by(MaestroSession.updated_at.desc()).all()

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
