"""Benchmark evolution tracking for Phase 7 — The Benchmark.

Generates reports showing how Maestro quality trends over time.
Tracks emergent scoring dimensions, user correction rates, and learning activity.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession

from app.models.benchmark_log import BenchmarkLog
from app.models.experience_file import ExperienceFile

logger = logging.getLogger(__name__)


def generate_evolution_report(
    project_id: str | UUID,
    days: int = 30,
    db: Optional[DBSession] = None,
) -> dict[str, Any]:
    """
    Generate an evolution report showing Maestro quality trends over time.

    Args:
        project_id: The project to analyze
        days: Number of days to include in the report
        db: Database session

    Returns:
        {
            project_id: str,
            time_range: {start, end},
            total_interactions: int,
            dimensions: [{name, scores_over_time, trend}],
            correction_rate_over_time: [{date, rate}],
            heartbeat_response_rate: float,
            experience_file_count: int,
            insights: [str]
        }
    """
    if db is None:
        raise ValueError("Database session required for evolution report")

    project_id_str = str(project_id)
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=days)

    # Get all benchmark entries in the time range
    entries = (
        db.query(BenchmarkLog)
        .filter(BenchmarkLog.project_id == project_id_str)
        .filter(BenchmarkLog.created_at >= start_time)
        .filter(BenchmarkLog.created_at <= end_time)
        .order_by(BenchmarkLog.created_at.asc())
        .all()
    )

    if not entries:
        return {
            "project_id": project_id_str,
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
            "total_interactions": 0,
            "dimensions": [],
            "correction_rate_over_time": [],
            "heartbeat_response_rate": 0,
            "experience_file_count": 0,
            "insights": ["No benchmark data available for this time range."],
        }

    # Aggregate scoring dimensions by day
    dimension_by_day: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    corrections_by_day: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "corrections": 0}
    )
    heartbeat_counts = {"total": 0, "with_response": 0}

    for entry in entries:
        date_key = entry.created_at.strftime("%Y-%m-%d")

        # Aggregate scoring dimensions
        if entry.scoring_dimensions:
            for dim, score in entry.scoring_dimensions.items():
                if isinstance(score, (int, float)):
                    dimension_by_day[dim][date_key].append(score)

        # Track correction rate
        corrections_by_day[date_key]["total"] += 1
        if entry.user_corrected:
            corrections_by_day[date_key]["corrections"] += 1

        # Track heartbeat response rate
        if entry.is_heartbeat:
            heartbeat_counts["total"] += 1
            # A heartbeat got a response if the next turn exists (user followed up)
            if entry.user_followed_up:
                heartbeat_counts["with_response"] += 1

    # Calculate dimension trends
    dimensions_result = []
    for dim_name, daily_scores in dimension_by_day.items():
        sorted_dates = sorted(daily_scores.keys())
        scores_over_time = []

        for date in sorted_dates:
            scores = daily_scores[date]
            avg = sum(scores) / len(scores) if scores else 0
            scores_over_time.append({"date": date, "avg_score": round(avg, 3)})

        # Calculate trend (simple linear regression)
        trend = _calculate_trend(scores_over_time)

        dimensions_result.append({
            "name": dim_name,
            "scores_over_time": scores_over_time,
            "trend": trend,
        })

    # Calculate correction rate over time
    correction_rate_over_time = []
    sorted_correction_dates = sorted(corrections_by_day.keys())
    for date in sorted_correction_dates:
        data = corrections_by_day[date]
        rate = data["corrections"] / data["total"] if data["total"] > 0 else 0
        correction_rate_over_time.append({
            "date": date,
            "rate": round(rate, 3),
            "total": data["total"],
            "corrections": data["corrections"],
        })

    # Calculate overall correction rate trend
    correction_trend = "stable"
    if len(correction_rate_over_time) >= 3:
        first_half = correction_rate_over_time[:len(correction_rate_over_time) // 2]
        second_half = correction_rate_over_time[len(correction_rate_over_time) // 2:]
        first_avg = sum(d["rate"] for d in first_half) / len(first_half)
        second_avg = sum(d["rate"] for d in second_half) / len(second_half)
        if second_avg < first_avg - 0.05:
            correction_trend = "improving"
        elif second_avg > first_avg + 0.05:
            correction_trend = "declining"

    # Calculate heartbeat response rate
    heartbeat_response_rate = (
        heartbeat_counts["with_response"] / heartbeat_counts["total"]
        if heartbeat_counts["total"] > 0
        else 0
    )

    # Count Experience files
    experience_count = (
        db.query(func.count(ExperienceFile.id))
        .filter(ExperienceFile.project_id == project_id_str)
        .scalar()
        or 0
    )

    # Generate insights
    insights = _generate_insights(
        total_interactions=len(entries),
        dimensions=dimensions_result,
        correction_trend=correction_trend,
        heartbeat_response_rate=heartbeat_response_rate,
        experience_count=experience_count,
    )

    return {
        "project_id": project_id_str,
        "time_range": {
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
        },
        "total_interactions": len(entries),
        "dimensions": dimensions_result,
        "correction_rate_over_time": correction_rate_over_time,
        "correction_trend": correction_trend,
        "heartbeat_response_rate": round(heartbeat_response_rate, 3),
        "experience_file_count": experience_count,
        "insights": insights,
    }


def _calculate_trend(scores_over_time: list[dict[str, Any]]) -> str:
    """Calculate trend direction from time series data."""
    if len(scores_over_time) < 3:
        return "insufficient_data"

    # Simple: compare first half average to second half average
    first_half = scores_over_time[:len(scores_over_time) // 2]
    second_half = scores_over_time[len(scores_over_time) // 2:]

    first_avg = sum(d["avg_score"] for d in first_half) / len(first_half)
    second_avg = sum(d["avg_score"] for d in second_half) / len(second_half)

    if second_avg > first_avg + 0.05:
        return "improving"
    elif second_avg < first_avg - 0.05:
        return "declining"
    return "stable"


def _generate_insights(
    total_interactions: int,
    dimensions: list[dict[str, Any]],
    correction_trend: str,
    heartbeat_response_rate: float,
    experience_count: int,
) -> list[str]:
    """Generate human-readable insights from the data."""
    insights = []

    # Interaction volume insight
    if total_interactions < 10:
        insights.append(
            f"Low interaction volume ({total_interactions} total). "
            "More data needed for reliable trends."
        )
    elif total_interactions >= 100:
        insights.append(
            f"Strong interaction volume ({total_interactions} total). "
            "Trends are statistically meaningful."
        )

    # Dimension insights
    improving_dims = [d["name"] for d in dimensions if d["trend"] == "improving"]
    declining_dims = [d["name"] for d in dimensions if d["trend"] == "declining"]

    if improving_dims:
        insights.append(
            f"Improving dimensions: {', '.join(improving_dims)}"
        )
    if declining_dims:
        insights.append(
            f"Attention needed on declining dimensions: {', '.join(declining_dims)}"
        )

    # Correction rate insight
    if correction_trend == "improving":
        insights.append(
            "Correction rate is decreasing over time. Maestro is getting more accurate."
        )
    elif correction_trend == "declining":
        insights.append(
            "Correction rate is increasing. Review recent Knowledge edits or model changes."
        )

    # Heartbeat insight
    if heartbeat_response_rate > 0.5:
        insights.append(
            f"Heartbeats are engaging: {round(heartbeat_response_rate * 100)}% response rate."
        )
    elif heartbeat_response_rate > 0 and heartbeat_response_rate < 0.2:
        insights.append(
            "Low heartbeat engagement. Consider adjusting heartbeat content or timing."
        )

    # Experience insight
    if experience_count > 5:
        insights.append(
            f"Learning is active: {experience_count} Experience files. "
            "Check routing_rules.md for learned patterns."
        )
    elif experience_count == 5:
        insights.append(
            "Only default Experience files present. "
            "Learning hasn't written extended knowledge yet."
        )

    return insights


def get_dimension_summary(
    project_id: str | UUID,
    db: DBSession,
) -> dict[str, dict[str, float]]:
    """
    Get a summary of all scoring dimensions and their average values.

    Returns:
        {dimension_name: {avg, min, max, count}}
    """
    project_id_str = str(project_id)

    entries = (
        db.query(BenchmarkLog)
        .filter(BenchmarkLog.project_id == project_id_str)
        .filter(BenchmarkLog.scoring_dimensions.isnot(None))
        .all()
    )

    dimension_values: dict[str, list[float]] = defaultdict(list)

    for entry in entries:
        if entry.scoring_dimensions:
            for dim, score in entry.scoring_dimensions.items():
                if isinstance(score, (int, float)):
                    dimension_values[dim].append(score)

    summary = {}
    for dim, values in dimension_values.items():
        if values:
            summary[dim] = {
                "avg": round(sum(values) / len(values), 3),
                "min": round(min(values), 3),
                "max": round(max(values), 3),
                "count": len(values),
            }

    return summary


def get_recent_corrections(
    project_id: str | UUID,
    limit: int = 10,
    db: Optional[DBSession] = None,
) -> list[dict[str, Any]]:
    """
    Get recent interactions where the user corrected Maestro.

    Useful for reviewing what Maestro got wrong.
    """
    if db is None:
        return []

    project_id_str = str(project_id)

    entries = (
        db.query(BenchmarkLog)
        .filter(BenchmarkLog.project_id == project_id_str)
        .filter(BenchmarkLog.user_corrected == True)  # noqa: E712
        .order_by(BenchmarkLog.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "benchmark_id": entry.id,
            "user_query": entry.user_query,
            "maestro_response": entry.maestro_response[:500],
            "created_at": entry.created_at.isoformat(),
            "scoring_dimensions": entry.scoring_dimensions,
        }
        for entry in entries
    ]
