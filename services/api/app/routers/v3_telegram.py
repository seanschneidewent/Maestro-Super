"""Telegram webhook endpoint for Maestro V3.

Receives updates from Telegram Bot API and routes them to Maestro sessions.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.session import SessionLocal
from app.models.telegram_user import TelegramUser
from app.services.v3.maestro_agent import run_maestro_turn
from app.services.v3.session_manager import SessionManager
from app.services.v3.telegram_bot import send_chat_action, send_message_safe, verify_webhook_secret
from app.services.v3.telegram_formatter import format_for_telegram

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v3/telegram", tags=["telegram"])


class TelegramUpdate(BaseModel):
    """Telegram update object (subset of fields we care about)."""

    update_id: int
    message: dict[str, Any] | None = None


def _get_telegram_user(telegram_user_id: int, db: Session) -> TelegramUser | None:
    """Look up Telegram user mapping."""
    return (
        db.query(TelegramUser)
        .filter(TelegramUser.telegram_user_id == telegram_user_id)
        .first()
    )


async def _handle_command(
    command: str,
    chat_id: int,
    telegram_user: TelegramUser,
    db: Session,
) -> str:
    """Handle bot commands (/reset, /compact)."""
    manager = SessionManager.instance()

    if command == "/reset":
        # Find and reset their Telegram session
        session = manager.get_or_create_telegram_session(
            project_id=telegram_user.project_id,
            user_id=telegram_user.user_id,
            db=db,
        )
        manager.reset_session(session.session_id, db)
        return "Fresh start. What's on your mind?"

    if command == "/compact":
        session = manager.get_or_create_telegram_session(
            project_id=telegram_user.project_id,
            user_id=telegram_user.user_id,
            db=db,
        )
        manager.compact_session(session, db)
        return "Conversation compacted. Ready."

    if command == "/start":
        return "Hey! I'm Maestro, your construction plan partner. Ask me anything about the plans."

    return f"Unknown command: {command}"


async def _handle_message(
    text: str,
    chat_id: int,
    telegram_user: TelegramUser,
    db: Session,
) -> list[str]:
    """Handle regular text message — run Maestro turn and collect response."""
    manager = SessionManager.instance()

    session = manager.get_or_create_telegram_session(
        project_id=telegram_user.project_id,
        user_id=telegram_user.user_id,
        db=db,
    )

    # Collect full response (no streaming for Telegram)
    full_response = ""
    async for event in run_maestro_turn(session, text, db):
        event_type = event.get("type")
        if event_type == "token":
            full_response += event.get("content", "")
        elif event_type == "done":
            break

    if not full_response.strip():
        full_response = "I'm not sure how to respond to that. Could you rephrase?"

    # Format for Telegram
    return format_for_telegram(full_response)


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None),
) -> dict[str, bool]:
    """
    Receive updates from Telegram Bot API.

    Telegram sends updates to this endpoint when users message the bot.
    We verify the secret token, parse the update, and route to Maestro.
    """
    settings = get_settings()

    # Verify webhook secret
    if not verify_webhook_secret(x_telegram_bot_api_secret_token):
        logger.warning("Invalid Telegram webhook secret")
        raise HTTPException(status_code=403, detail="Invalid secret")

    # Parse update
    try:
        body = await request.json()
        update = TelegramUpdate(**body)
    except Exception as e:
        logger.error("Failed to parse Telegram update: %s", e)
        raise HTTPException(status_code=400, detail="Invalid update")

    # We only handle message updates
    if not update.message:
        return {"ok": True}

    message = update.message
    chat_id = message.get("chat", {}).get("id")
    from_user = message.get("from", {})
    telegram_user_id = from_user.get("id")
    text = message.get("text", "").strip()

    if not chat_id or not telegram_user_id or not text:
        return {"ok": True}

    # Look up the Telegram user mapping
    db = SessionLocal()
    try:
        telegram_user = _get_telegram_user(telegram_user_id, db)

        if not telegram_user:
            # User not linked — check if there's a default project
            if settings.telegram_default_project_id:
                # Auto-create mapping with default project
                telegram_user = TelegramUser(
                    telegram_user_id=telegram_user_id,
                    user_id=str(telegram_user_id),  # Use Telegram ID as user ID for now
                    project_id=settings.telegram_default_project_id,
                )
                db.add(telegram_user)
                db.commit()
                db.refresh(telegram_user)
                logger.info(
                    "Auto-linked Telegram user %s to default project %s",
                    telegram_user_id,
                    settings.telegram_default_project_id,
                )
            else:
                # No mapping and no default — tell user to link account
                await send_message_safe(
                    chat_id,
                    "I don't recognize your account yet. Ask your admin to link your Telegram to Maestro.",
                )
                return {"ok": True}

        if not telegram_user.project_id:
            await send_message_safe(
                chat_id,
                "Your account isn't linked to a project yet. Ask your admin to set one up.",
            )
            return {"ok": True}

        # Send typing indicator
        await send_chat_action(chat_id, "typing")

        # Handle commands
        if text.startswith("/"):
            command = text.split()[0].lower()
            response = await _handle_command(command, chat_id, telegram_user, db)
            await send_message_safe(chat_id, response)
            return {"ok": True}

        # Handle regular message
        responses = await _handle_message(text, chat_id, telegram_user, db)

        # Send response(s) — may be split if too long
        for response in responses:
            if response.strip():
                await send_message_safe(chat_id, response)

    except Exception as e:
        logger.exception("Error handling Telegram update: %s", e)
        # Don't expose internal errors to user
        await send_message_safe(
            chat_id,
            "Something went wrong on my end. Try again in a moment.",
        )
    finally:
        db.close()

    return {"ok": True}
