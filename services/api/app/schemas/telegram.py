"""Telegram webhook schemas for Maestro."""

from typing import Any
from pydantic import BaseModel, Field


class TelegramUser(BaseModel):
    """Telegram user object."""
    id: int
    is_bot: bool = False
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None


class TelegramChat(BaseModel):
    """Telegram chat object."""
    id: int
    type: str  # "private", "group", "supergroup", "channel"
    title: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class TelegramVoice(BaseModel):
    """Telegram voice message object."""
    file_id: str
    file_unique_id: str
    duration: int
    mime_type: str | None = None
    file_size: int | None = None


class TelegramPhotoSize(BaseModel):
    """Telegram photo size object."""
    file_id: str
    file_unique_id: str
    width: int
    height: int
    file_size: int | None = None


class TelegramMessage(BaseModel):
    """Telegram message object."""
    message_id: int
    date: int
    chat: TelegramChat
    from_user: TelegramUser | None = Field(default=None, alias="from")
    text: str | None = None
    caption: str | None = None
    voice: TelegramVoice | None = None
    photo: list[TelegramPhotoSize] | None = None
    reply_to_message: "TelegramMessage | None" = None
    
    class Config:
        populate_by_name = True


class TelegramCallbackQuery(BaseModel):
    """Telegram callback query from inline button."""
    id: str
    from_user: TelegramUser = Field(alias="from")
    message: TelegramMessage | None = None
    chat_instance: str
    data: str | None = None  # Callback data from button
    
    class Config:
        populate_by_name = True


class TelegramUpdate(BaseModel):
    """Telegram webhook update."""
    update_id: int
    message: TelegramMessage | None = None
    callback_query: TelegramCallbackQuery | None = None


class InlineKeyboardButton(BaseModel):
    """Inline keyboard button."""
    text: str
    callback_data: str | None = None
    url: str | None = None


class InlineKeyboardMarkup(BaseModel):
    """Inline keyboard markup."""
    inline_keyboard: list[list[InlineKeyboardButton]]


class SendMessageRequest(BaseModel):
    """Request to send a message via Telegram API."""
    chat_id: int
    text: str
    parse_mode: str | None = "Markdown"
    reply_markup: InlineKeyboardMarkup | None = None
    reply_to_message_id: int | None = None


class SendPhotoRequest(BaseModel):
    """Request to send a photo via Telegram API."""
    chat_id: int
    photo: str  # file_id or URL
    caption: str | None = None
    parse_mode: str | None = "Markdown"
    reply_markup: InlineKeyboardMarkup | None = None


# Response action types for Big Maestro → Telegram
class MaestroTelegramResponse(BaseModel):
    """Response from Maestro for Telegram delivery."""
    text: str
    buttons: list[list[dict[str, str]]] | None = None  # [[{text, callback_data}]]
    sheet_images: list[dict[str, Any]] | None = None  # [{page_id, bboxes, caption}]
    voice_response: bool = False  # If True, also send as voice


# Callback data parsing
class ParsedCallback(BaseModel):
    """Parsed callback data from button tap."""
    action: str
    params: list[str] = Field(default_factory=list)
    
    @classmethod
    def parse(cls, data: str) -> "ParsedCallback":
        """Parse callback_data string like 'action:param1:param2'."""
        parts = data.split(":")
        return cls(action=parts[0], params=parts[1:] if len(parts) > 1 else [])
