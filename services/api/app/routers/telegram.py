"""
Telegram webhook endpoints for Maestro.

Handles incoming messages and callback queries from Telegram bot.
Superintendents can text Maestro directly via Telegram.
"""

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.telegram import (
    TelegramUpdate,
    TelegramMessage,
    TelegramCallbackQuery,
    ParsedCallback,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])

# Telegram Bot Token from environment
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Handle incoming Telegram webhook updates.
    
    Telegram sends:
    - message: Regular text/voice/photo messages
    - callback_query: Inline button taps
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("Telegram webhook called but TELEGRAM_BOT_TOKEN not set")
        raise HTTPException(status_code=500, detail="Telegram not configured")
    
    try:
        body = await request.json()
        update = TelegramUpdate(**body)
    except Exception as e:
        logger.error(f"Failed to parse Telegram update: {e}")
        return {"ok": False, "error": "Invalid update"}
    
    # Handle callback query (button tap)
    if update.callback_query:
        return await handle_callback_query(update.callback_query, db)
    
    # Handle regular message
    if update.message:
        return await handle_message(update.message, db)
    
    return {"ok": True}


async def handle_message(message: TelegramMessage, db: Session) -> dict:
    """
    Handle incoming text/voice/photo message.
    
    Flow:
    1. Identify user and their active project
    2. Parse message type (text, voice, photo)
    3. Run through Big Maestro
    4. Send response with inline buttons
    """
    chat_id = message.chat.id
    user_id = str(message.from_user.id) if message.from_user else str(chat_id)
    
    logger.info(f"Telegram message from {user_id}: {message.text or '[media]'}")
    
    # TODO: Get user's active project
    # project = await get_user_active_project(db, user_id)
    # if not project:
    #     await send_message(chat_id, "No active project. Set one up in the Maestro app first!")
    #     return {"ok": True}
    
    # Determine message type and extract query
    query = ""
    if message.text:
        query = message.text
    elif message.voice:
        # TODO: Transcribe voice message
        # query = await transcribe_voice(message.voice.file_id)
        await send_message(chat_id, "🎤 Voice messages coming soon!")
        return {"ok": True}
    elif message.photo:
        # TODO: Analyze photo against plans
        # query = message.caption or "What am I looking at?"
        await send_message(chat_id, "📷 Photo analysis coming soon!")
        return {"ok": True}
    else:
        await send_message(chat_id, "Send me text, voice, or a photo!")
        return {"ok": True}
    
    # TODO: Run through Big Maestro
    # For now, send a placeholder response
    await send_message(
        chat_id=chat_id,
        text=f"🔍 Looking up: {query}\n\n(Big Maestro integration coming soon!)",
        buttons=[
            [
                {"text": "📄 View Sheet", "callback_data": "view_sheet:placeholder"},
                {"text": "🔍 Go Deeper", "callback_data": "go_deeper"},
            ],
            [
                {"text": "📋 Schedule", "callback_data": "show_schedule"},
            ],
        ],
    )
    
    return {"ok": True}


async def handle_callback_query(callback: TelegramCallbackQuery, db: Session) -> dict:
    """
    Handle inline button tap.
    
    Flow:
    1. Parse callback data (action:param1:param2)
    2. Execute appropriate action
    3. Send response or update message
    """
    chat_id = callback.message.chat.id if callback.message else None
    if not chat_id:
        return {"ok": False}
    
    callback_data = callback.data or ""
    parsed = ParsedCallback.parse(callback_data)
    
    logger.info(f"Telegram callback: {parsed.action} with params {parsed.params}")
    
    # Acknowledge callback immediately
    await answer_callback_query(callback.id)
    
    # Route based on action
    if parsed.action == "view_sheet":
        page_id = parsed.params[0] if parsed.params else None
        if page_id:
            # TODO: Send sheet image with highlights
            await send_message(chat_id, f"📄 Showing sheet {page_id}...")
    
    elif parsed.action == "go_deeper":
        # TODO: Re-run with deep mode
        await send_message(chat_id, "🔍 Going deeper...")
    
    elif parsed.action == "show_schedule":
        # TODO: Extract and show schedule
        await send_message(chat_id, "📋 Showing schedule...")
    
    elif parsed.action == "back":
        # TODO: Navigate back in context stack
        await send_message(chat_id, "⬅️ Going back...")
    
    else:
        await send_message(chat_id, f"Unknown action: {parsed.action}")
    
    return {"ok": True}


# Telegram API helpers

async def send_message(
    chat_id: int,
    text: str,
    buttons: list[list[dict[str, str]]] | None = None,
    reply_to: int | None = None,
) -> dict | None:
    """Send a text message via Telegram API."""
    import httpx
    
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("Cannot send Telegram message: TELEGRAM_BOT_TOKEN not set")
        return None
    
    data: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    
    if buttons:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(**btn) for btn in row]
                for row in buttons
            ]
        )
        data["reply_markup"] = keyboard.model_dump()
    
    if reply_to:
        data["reply_to_message_id"] = reply_to
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TELEGRAM_API_BASE}/sendMessage",
            json=data,
        )
        return response.json()


async def send_photo(
    chat_id: int,
    photo: bytes | str,
    caption: str | None = None,
    buttons: list[list[dict[str, str]]] | None = None,
) -> dict | None:
    """Send a photo via Telegram API."""
    import httpx
    
    if not TELEGRAM_BOT_TOKEN:
        return None
    
    data: dict[str, Any] = {
        "chat_id": chat_id,
    }
    
    if caption:
        data["caption"] = caption
        data["parse_mode"] = "Markdown"
    
    if buttons:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(**btn) for btn in row]
                for row in buttons
            ]
        )
        data["reply_markup"] = keyboard.model_dump()
    
    async with httpx.AsyncClient() as client:
        if isinstance(photo, bytes):
            # Upload as file
            files = {"photo": ("image.jpg", photo, "image/jpeg")}
            response = await client.post(
                f"{TELEGRAM_API_BASE}/sendPhoto",
                data=data,
                files=files,
            )
        else:
            # Send file_id or URL
            data["photo"] = photo
            response = await client.post(
                f"{TELEGRAM_API_BASE}/sendPhoto",
                json=data,
            )
        return response.json()


async def answer_callback_query(callback_query_id: str, text: str | None = None) -> dict | None:
    """Acknowledge a callback query."""
    import httpx
    
    if not TELEGRAM_BOT_TOKEN:
        return None
    
    data: dict[str, Any] = {
        "callback_query_id": callback_query_id,
    }
    if text:
        data["text"] = text
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TELEGRAM_API_BASE}/answerCallbackQuery",
            json=data,
        )
        return response.json()


async def edit_message(
    chat_id: int,
    message_id: int,
    text: str,
    buttons: list[list[dict[str, str]]] | None = None,
) -> dict | None:
    """Edit an existing message."""
    import httpx
    
    if not TELEGRAM_BOT_TOKEN:
        return None
    
    data: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown",
    }
    
    if buttons:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(**btn) for btn in row]
                for row in buttons
            ]
        )
        data["reply_markup"] = keyboard.model_dump()
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TELEGRAM_API_BASE}/editMessageText",
            json=data,
        )
        return response.json()


async def delete_message(chat_id: int, message_id: int) -> dict | None:
    """Delete a message."""
    import httpx
    
    if not TELEGRAM_BOT_TOKEN:
        return None
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{TELEGRAM_API_BASE}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
        )
        return response.json()
