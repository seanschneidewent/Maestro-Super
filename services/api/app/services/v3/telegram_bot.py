"""Telegram Bot API integration for Maestro.

Provides functions to send messages via Telegram Bot API.
Uses webhook mode — Telegram sends updates to our endpoint.

Setup instructions:
1. Create a bot via @BotFather on Telegram
2. Set TELEGRAM_BOT_TOKEN in environment
3. Register bot commands via BotFather:
   /reset - Start fresh conversation
   /compact - Compress older messages
4. Set webhook URL:
   curl -X POST "https://api.telegram.org/bot{TOKEN}/setWebhook" \
        -d "url=https://your-domain.com/v3/telegram/webhook" \
        -d "secret_token={TELEGRAM_WEBHOOK_SECRET}"
"""

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org/bot"


async def send_message(
    chat_id: int,
    text: str,
    parse_mode: str | None = None,
    disable_notification: bool = False,
) -> dict[str, Any]:
    """
    Send a message to a Telegram chat.

    Args:
        chat_id: Telegram chat ID
        text: Message text (max 4096 characters)
        parse_mode: 'MarkdownV2', 'HTML', or None for plain text
        disable_notification: Send silently

    Returns:
        Telegram API response

    Raises:
        httpx.HTTPError: On network error
        ValueError: If bot token not configured
    """
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise ValueError("Telegram bot token not configured")

    url = f"{TELEGRAM_API_BASE}{settings.telegram_bot_token}/sendMessage"

    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "disable_notification": disable_notification,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=30.0)
        response.raise_for_status()
        return response.json()


async def send_message_safe(
    chat_id: int,
    text: str,
    parse_mode: str | None = "MarkdownV2",
) -> bool:
    """
    Send a message with fallback to plain text on parse errors.

    Returns True if sent successfully, False otherwise.
    """
    try:
        result = await send_message(chat_id, text, parse_mode=parse_mode)
        return result.get("ok", False)
    except httpx.HTTPStatusError as e:
        # If MarkdownV2 parsing fails, retry without formatting
        if parse_mode and e.response.status_code == 400:
            logger.warning("MarkdownV2 parse failed, retrying as plain text")
            try:
                # Strip markdown-like syntax for plain text
                plain_text = text.replace("\\", "")
                result = await send_message(chat_id, plain_text, parse_mode=None)
                return result.get("ok", False)
            except Exception:
                logger.exception("Failed to send plain text message")
                return False
        logger.exception("Failed to send Telegram message")
        return False
    except Exception:
        logger.exception("Failed to send Telegram message")
        return False


async def send_chat_action(chat_id: int, action: str = "typing") -> bool:
    """
    Send a chat action (typing indicator, etc.).

    Args:
        chat_id: Telegram chat ID
        action: 'typing', 'upload_photo', 'upload_document', etc.

    Returns:
        True if successful
    """
    settings = get_settings()
    if not settings.telegram_bot_token:
        return False

    url = f"{TELEGRAM_API_BASE}{settings.telegram_bot_token}/sendChatAction"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json={"chat_id": chat_id, "action": action},
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json().get("ok", False)
    except Exception:
        logger.exception("Failed to send chat action")
        return False


async def set_webhook(
    webhook_url: str,
    secret_token: str | None = None,
    drop_pending_updates: bool = False,
) -> dict[str, Any]:
    """
    Set the webhook URL for the bot.

    Call this once during deployment setup.

    Args:
        webhook_url: Full HTTPS URL for webhook endpoint
        secret_token: Optional secret for webhook verification
        drop_pending_updates: Drop pending updates on webhook set

    Returns:
        Telegram API response
    """
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise ValueError("Telegram bot token not configured")

    url = f"{TELEGRAM_API_BASE}{settings.telegram_bot_token}/setWebhook"

    payload: dict[str, Any] = {
        "url": webhook_url,
        "drop_pending_updates": drop_pending_updates,
    }
    if secret_token:
        payload["secret_token"] = secret_token

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, timeout=30.0)
        response.raise_for_status()
        return response.json()


async def delete_webhook() -> dict[str, Any]:
    """Delete the current webhook."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise ValueError("Telegram bot token not configured")

    url = f"{TELEGRAM_API_BASE}{settings.telegram_bot_token}/deleteWebhook"

    async with httpx.AsyncClient() as client:
        response = await client.post(url, timeout=30.0)
        response.raise_for_status()
        return response.json()


async def get_webhook_info() -> dict[str, Any]:
    """Get current webhook info."""
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise ValueError("Telegram bot token not configured")

    url = f"{TELEGRAM_API_BASE}{settings.telegram_bot_token}/getWebhookInfo"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=30.0)
        response.raise_for_status()
        return response.json()


def verify_webhook_secret(provided_secret: str | None) -> bool:
    """
    Verify the webhook secret token from Telegram.

    Args:
        provided_secret: Secret from X-Telegram-Bot-Api-Secret-Token header

    Returns:
        True if valid or no secret configured
    """
    settings = get_settings()
    if not settings.telegram_webhook_secret:
        # No secret configured, allow all
        return True
    return provided_secret == settings.telegram_webhook_secret
