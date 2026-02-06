"""Heartbeat System for Maestro V3.

The heartbeat is NOT a separate agent. It's a Maestro turn where Maestro initiates
instead of the super. This enables proactive insights and calculated scheduling questions.

The heartbeat:
- Runs through the Telegram Maestro session (same conversation, same context)
- Cross-references Schedule × Knowledge × Experience
- Operates in two modes: TELL (proactive insight) or ASK (scheduling question)
- Every response feeds Learning → Experience grows → next heartbeat is smarter
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time as dtime
from typing import Callable

from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.models.session import MaestroSession
from app.services.v3.maestro_agent import run_maestro_turn
from app.services.v3.session_manager import SessionManager
from app.services.v3.telegram_bot import send_message_safe
from app.services.v3.telegram_formatter import format_for_telegram

logger = logging.getLogger(__name__)


HEARTBEAT_TRIGGER_PREFIX = "[HEARTBEAT TRIGGER"

HEARTBEAT_TRIGGER_MESSAGE = """[HEARTBEAT TRIGGER - This is your scheduled check-in. You are initiating this conversation.
Read schedule.md and your Experience. Cross-reference with Knowledge (the plans).
Choose ONE of two modes:
- TELL: Share a proactive insight (upcoming activity × plan detail = actionable info)
- ASK: Ask a calculated scheduling question that fills a gap in your understanding
Your message goes directly to the superintendent via Telegram. Be concise and valuable.]"""


def parse_heartbeat_schedule(schedule_str: str) -> list[tuple[int, int]]:
    """Parse heartbeat schedule string into list of (hour, minute) tuples.

    Args:
        schedule_str: Comma-separated HH:MM times, e.g. "06:30,12:00"

    Returns:
        List of (hour, minute) tuples
    """
    times: list[tuple[int, int]] = []
    if not schedule_str:
        return times

    for part in schedule_str.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            hour_str, minute_str = part.split(":")
            hour = int(hour_str)
            minute = int(minute_str)
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                times.append((hour, minute))
            else:
                logger.warning("Invalid time in heartbeat schedule: %s", part)
        except ValueError:
            logger.warning("Failed to parse heartbeat time: %s", part)

    return times


def is_quiet_hours(
    now: datetime,
    quiet_start: int = 21,  # 9 PM
    quiet_end: int = 6,     # 6 AM
) -> bool:
    """Check if current time is in quiet hours.

    Quiet hours: don't heartbeat before 6 AM or after 9 PM.
    """
    hour = now.hour
    if quiet_start > quiet_end:
        # Quiet hours span midnight (e.g., 21:00 - 06:00)
        return hour >= quiet_start or hour < quiet_end
    else:
        # Quiet hours within same day
        return quiet_start <= hour < quiet_end


def should_trigger_heartbeat(
    schedule: list[tuple[int, int]],
    now: datetime,
    last_heartbeat: datetime | None,
    tolerance_minutes: int = 5,
) -> bool:
    """Check if we should trigger a heartbeat based on schedule.

    Args:
        schedule: List of (hour, minute) for scheduled heartbeats
        now: Current time in the configured timezone
        last_heartbeat: When the last heartbeat was triggered
        tolerance_minutes: Window around scheduled time to trigger

    Returns:
        True if a heartbeat should be triggered
    """
    if is_quiet_hours(now):
        return False

    current_time = dtime(now.hour, now.minute)

    for sched_hour, sched_minute in schedule:
        sched_time = dtime(sched_hour, sched_minute)

        # Check if current time is within tolerance of scheduled time
        sched_minutes = sched_hour * 60 + sched_minute
        current_minutes = now.hour * 60 + now.minute
        diff = abs(current_minutes - sched_minutes)

        if diff <= tolerance_minutes:
            # Check we haven't already triggered for this slot
            if last_heartbeat:
                last_minutes = last_heartbeat.hour * 60 + last_heartbeat.minute
                last_diff = abs(sched_minutes - last_minutes)
                # If last heartbeat was also within tolerance, skip
                if last_diff <= tolerance_minutes and last_heartbeat.date() == now.date():
                    continue

            return True

    return False


async def trigger_heartbeat_turn(
    session_id: str,
    chat_id: int,
    db_factory: Callable[[], DBSession],
) -> dict:
    """Trigger a heartbeat turn for a Telegram session.

    This is the core heartbeat logic:
    1. Get the session from SessionManager
    2. Build the heartbeat trigger message
    3. Call run_maestro_turn (same as regular queries)
    4. Collect the full response (non-streaming for Telegram)
    5. Send via Telegram Bot API
    6. The interaction becomes part of the conversation

    Args:
        session_id: The Telegram session ID
        chat_id: Telegram chat ID to send the response
        db_factory: Factory to create DB sessions

    Returns:
        Dict with heartbeat result info
    """
    db = db_factory()
    try:
        manager = SessionManager.instance()
        session = manager.get_session(session_id, db)

        if not session:
            logger.warning("Heartbeat: Session %s not found", session_id)
            return {"success": False, "error": "Session not found"}

        if session.session_type != "telegram":
            logger.warning("Heartbeat: Session %s is not a Telegram session", session_id)
            return {"success": False, "error": "Not a Telegram session"}

        # Collect the full response (non-streaming)
        response_text = ""
        async for event in run_maestro_turn(session, HEARTBEAT_TRIGGER_MESSAGE, db):
            event_type = event.get("type")
            if event_type == "token":
                response_text += event.get("content", "")
            elif event_type == "done":
                break

        if not response_text.strip():
            logger.info("Heartbeat: Empty response for session %s", session_id)
            return {"success": True, "empty": True}

        # Format and send via Telegram
        formatted_parts = format_for_telegram(response_text)
        sent = True
        for part in formatted_parts:
            if part:
                part_sent = await send_message_safe(chat_id, part)
                if not part_sent:
                    sent = False

        if sent:
            logger.info(
                "Heartbeat sent for session %s: %s...",
                session_id,
                response_text[:100]
            )
        else:
            logger.warning("Heartbeat: Failed to send Telegram message for session %s", session_id)

        return {
            "success": sent,
            "session_id": session_id,
            "response_length": len(response_text),
        }

    except Exception as e:
        logger.exception("Heartbeat turn failed for session %s: %s", session_id, e)
        return {"success": False, "error": str(e)}
    finally:
        db.close()


async def run_heartbeat(
    db_factory: Callable[[], DBSession],
) -> dict:
    """Run heartbeats for all active Telegram sessions.

    This is called by the scheduler when it's time for a heartbeat.

    Args:
        db_factory: Factory to create DB sessions

    Returns:
        Dict with summary of heartbeat run
    """
    db = db_factory()
    try:
        # Find all active Telegram sessions
        rows = (
            db.query(MaestroSession)
            .filter(MaestroSession.session_type == "telegram")
            .filter(MaestroSession.status == "active")
            .all()
        )

        if not rows:
            logger.debug("Heartbeat: No active Telegram sessions")
            return {"triggered": 0, "sessions": []}

        results = []
        for row in rows:
            # Get the chat_id from the user_id (which is the Telegram chat_id for Telegram sessions)
            try:
                chat_id = int(row.user_id)
            except (ValueError, TypeError):
                logger.warning("Heartbeat: Invalid chat_id for session %s", row.id)
                continue

            result = await trigger_heartbeat_turn(row.id, chat_id, db_factory)
            results.append({
                "session_id": row.id,
                "project_id": row.project_id,
                **result,
            })

        logger.info("Heartbeat run complete: %d sessions processed", len(results))
        return {"triggered": len(results), "sessions": results}

    except Exception as e:
        logger.exception("Heartbeat run failed: %s", e)
        return {"triggered": 0, "error": str(e)}
    finally:
        db.close()


async def run_heartbeat_scheduler(
    db_factory: Callable[[], DBSession],
    check_interval: float = 60.0,
) -> None:
    """Background scheduler for heartbeats.

    Runs continuously, checking every minute if it's time for a heartbeat.

    Args:
        db_factory: Factory to create DB sessions
        check_interval: Seconds between schedule checks (default 60)
    """
    settings = get_settings()

    if not settings.heartbeat_enabled:
        logger.info("Heartbeat scheduler disabled")
        return

    schedule = parse_heartbeat_schedule(settings.heartbeat_schedule)
    if not schedule:
        logger.warning("Heartbeat scheduler has no valid schedule times")
        return

    try:
        tz = ZoneInfo(settings.heartbeat_timezone)
    except Exception:
        logger.warning("Invalid heartbeat timezone %s, using UTC", settings.heartbeat_timezone)
        tz = ZoneInfo("UTC")

    logger.info(
        "Heartbeat scheduler started: schedule=%s, timezone=%s",
        settings.heartbeat_schedule,
        settings.heartbeat_timezone,
    )

    last_heartbeat: datetime | None = None

    while True:
        try:
            now = datetime.now(tz)

            if should_trigger_heartbeat(schedule, now, last_heartbeat):
                logger.info("Heartbeat triggered at %s", now.strftime("%H:%M"))
                await run_heartbeat(db_factory)
                last_heartbeat = now

            await asyncio.sleep(check_interval)

        except asyncio.CancelledError:
            logger.info("Heartbeat scheduler stopped")
            raise
        except Exception as e:
            logger.exception("Heartbeat scheduler error: %s", e)
            await asyncio.sleep(check_interval)
