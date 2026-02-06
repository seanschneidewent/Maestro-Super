"""Benchmark logging service for Phase 7 — The Benchmark.

Captures structured data from every Maestro interaction for emergent scoring.
Learning fills in assessments async. User signals are inferred from follow-ups.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.models.benchmark_log import BenchmarkLog

logger = logging.getLogger(__name__)


def log_benchmark(
    session_id: str,
    project_id: str,
    turn_number: int,
    user_query: str,
    maestro_response: str,
    model: str,
    latency_ms: Optional[int] = None,
    tokens_input: Optional[int] = None,
    tokens_output: Optional[int] = None,
    experience_paths_read: Optional[list[str]] = None,
    pointers_retrieved: Optional[list[dict[str, Any]]] = None,
    workspace_actions: Optional[list[dict[str, Any]]] = None,
    is_heartbeat: bool = False,
    db: Optional[DBSession] = None,
) -> Optional[str]:
    """
    Log a benchmark entry for a Maestro interaction.

    Creates a benchmark_logs row with input/output data. Returns the benchmark_id
    for later Learning updates. Returns None if benchmarking is disabled or fails.

    Args:
        session_id: The session this interaction belongs to
        project_id: The project this interaction belongs to
        turn_number: The turn number within the session
        user_query: The user's query
        maestro_response: Maestro's response
        model: The model that generated the response
        latency_ms: Response latency in milliseconds
        tokens_input: Number of input tokens
        tokens_output: Number of output tokens
        experience_paths_read: Which Experience files were used
        pointers_retrieved: [{pointer_id, title, relevance_score}]
        workspace_actions: [{action, targets}]
        is_heartbeat: Whether this was a heartbeat-triggered turn
        db: Database session

    Returns:
        benchmark_id (str) or None if logging failed/disabled
    """
    settings = get_settings()
    if not settings.benchmark_enabled:
        return None

    if db is None:
        logger.warning("Benchmark logging skipped: no database session provided")
        return None

    try:
        benchmark_id = str(uuid4())

        log_entry = BenchmarkLog(
            id=benchmark_id,
            session_id=session_id,
            project_id=project_id,
            turn_number=turn_number,
            is_heartbeat=is_heartbeat,
            user_query=user_query,
            experience_paths_read=experience_paths_read,
            pointers_retrieved=pointers_retrieved,
            workspace_actions=workspace_actions,
            maestro_response=maestro_response,
            response_model=model,
            response_latency_ms=latency_ms,
            token_count_input=tokens_input,
            token_count_output=tokens_output,
        )

        db.add(log_entry)
        db.commit()

        logger.debug(
            "Logged benchmark %s for session %s turn %d",
            benchmark_id,
            session_id,
            turn_number,
        )
        return benchmark_id

    except Exception as exc:
        logger.warning("Failed to log benchmark: %s", exc)
        db.rollback()
        return None


def update_benchmark_learning(
    benchmark_id: str,
    assessment: dict[str, Any],
    scores: dict[str, float],
    experience_updates: Optional[list[dict[str, Any]]] = None,
    knowledge_edits: Optional[list[dict[str, Any]]] = None,
    db: Optional[DBSession] = None,
) -> bool:
    """
    Update a benchmark entry with Learning's evaluation.

    Called by Learning after it processes the interaction.

    Args:
        benchmark_id: The benchmark entry to update
        assessment: Free-form evaluation from Learning
        scores: Emergent scoring dimensions {dimension: score}
        experience_updates: What Learning wrote to Experience
        knowledge_edits: What Learning edited in Knowledge
        db: Database session

    Returns:
        True if update succeeded, False otherwise
    """
    if db is None:
        logger.warning("Benchmark update skipped: no database session provided")
        return False

    try:
        log_entry = (
            db.query(BenchmarkLog)
            .filter(BenchmarkLog.id == benchmark_id)
            .first()
        )

        if not log_entry:
            logger.warning("Benchmark entry not found: %s", benchmark_id)
            return False

        log_entry.learning_assessment = assessment
        log_entry.scoring_dimensions = scores
        log_entry.experience_updates = experience_updates
        log_entry.knowledge_edits = knowledge_edits

        db.commit()

        logger.debug("Updated benchmark %s with Learning evaluation", benchmark_id)
        return True

    except Exception as exc:
        logger.warning("Failed to update benchmark Learning: %s", exc)
        db.rollback()
        return False


# User signal detection patterns
CORRECTION_PATTERNS = [
    r"\bno\b.*\b(that's|thats|it's|its)\s+(wrong|incorrect|not right)",
    r"\b(actually|incorrect|wrong)\b",
    r"\bthat's not\b",
    r"\bit('s| is) not\b",
    r"\byou('re| are) wrong\b",
    r"\bi meant\b",
    r"\bi said\b.*\bnot\b",
]

REPHRASING_PATTERNS = [
    r"^(i mean|what i meant|let me rephrase)",
    r"^(sorry|no),?\s*(i|what)",
    r"\b(try again|one more time)\b",
    r"^(so|like)\s+.{0,20}\?$",  # Short question rephrasing
]


def detect_user_signals(
    previous_response: str,
    current_query: str,
) -> dict[str, bool]:
    """
    Detect user signals from the follow-up message.

    Infers: correction, rephrasing, follow-up, or topic change.

    Args:
        previous_response: Maestro's last response
        current_query: The user's current query

    Returns:
        {user_followed_up, user_corrected, user_rephrased, user_moved_on}
    """
    query_lower = current_query.lower().strip()

    # Check for correction signals
    user_corrected = any(
        re.search(pattern, query_lower, re.IGNORECASE)
        for pattern in CORRECTION_PATTERNS
    )

    # Check for rephrasing signals
    user_rephrased = any(
        re.search(pattern, query_lower, re.IGNORECASE)
        for pattern in REPHRASING_PATTERNS
    )

    # Extract key terms from previous response for topic continuity
    # Simple heuristic: check if query references terms from response
    prev_terms = set(
        word.lower()
        for word in re.findall(r"\b\w{4,}\b", previous_response)
    )
    query_terms = set(
        word.lower()
        for word in re.findall(r"\b\w{4,}\b", current_query)
    )

    # If there's significant overlap, it's a follow-up
    overlap = prev_terms & query_terms
    # Exclude common words
    common_words = {"that", "this", "what", "when", "where", "there", "here", "about", "have", "been", "were", "with"}
    meaningful_overlap = overlap - common_words

    user_followed_up = len(meaningful_overlap) >= 2 or user_corrected or user_rephrased
    user_moved_on = not user_followed_up and not user_corrected and not user_rephrased

    return {
        "user_followed_up": user_followed_up,
        "user_corrected": user_corrected,
        "user_rephrased": user_rephrased,
        "user_moved_on": user_moved_on,
    }


def update_benchmark_user_signals(
    benchmark_id: str,
    previous_response: str,
    current_query: str,
    db: Optional[DBSession] = None,
) -> bool:
    """
    Update a benchmark entry with inferred user signals.

    Called during the NEXT Maestro turn — looks at the user's follow-up message.

    Args:
        benchmark_id: The benchmark entry to update
        previous_response: Maestro's response from the previous turn
        current_query: The user's current query
        db: Database session

    Returns:
        True if update succeeded, False otherwise
    """
    if db is None:
        logger.warning("Benchmark signal update skipped: no database session provided")
        return False

    try:
        log_entry = (
            db.query(BenchmarkLog)
            .filter(BenchmarkLog.id == benchmark_id)
            .first()
        )

        if not log_entry:
            logger.warning("Benchmark entry not found: %s", benchmark_id)
            return False

        signals = detect_user_signals(previous_response, current_query)

        log_entry.user_followed_up = signals["user_followed_up"]
        log_entry.user_corrected = signals["user_corrected"]
        log_entry.user_rephrased = signals["user_rephrased"]
        log_entry.user_moved_on = signals["user_moved_on"]

        db.commit()

        logger.debug(
            "Updated benchmark %s with user signals: %s",
            benchmark_id,
            signals,
        )
        return True

    except Exception as exc:
        logger.warning("Failed to update benchmark user signals: %s", exc)
        db.rollback()
        return False


def get_last_benchmark_id(
    session_id: str,
    db: DBSession,
) -> Optional[str]:
    """
    Get the benchmark_id from the most recent turn in a session.

    Used to update user signals when processing the next turn.
    """
    try:
        log_entry = (
            db.query(BenchmarkLog)
            .filter(BenchmarkLog.session_id == session_id)
            .order_by(BenchmarkLog.created_at.desc())
            .first()
        )
        return log_entry.id if log_entry else None
    except Exception as exc:
        logger.warning("Failed to get last benchmark: %s", exc)
        return None
