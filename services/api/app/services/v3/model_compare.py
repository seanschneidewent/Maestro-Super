"""Model comparison harness for Phase 7 — The Benchmark.

Replays queries across different model providers and compares quality.
This is an admin/developer tool, not user-facing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session as DBSession

from app.config import get_settings
from app.models.benchmark_log import BenchmarkLog
from app.models.experience_file import ExperienceFile
from app.services.v3.experience import read_experience_for_query
from app.services.v3.providers import chat_completion

logger = logging.getLogger(__name__)


@dataclass
class ComparisonResult:
    """Result of comparing two model responses for a single query."""

    query_id: str
    user_query: str
    original_response: str
    original_model: str
    original_scores: Optional[dict[str, float]]

    model_a: str
    response_a: str
    latency_a_ms: int
    scores_a: Optional[dict[str, float]]

    model_b: str
    response_b: str
    latency_b_ms: int
    scores_b: Optional[dict[str, float]]


def _build_comparison_system_prompt(
    experience_context: str,
    project_name: Optional[str] = None,
) -> str:
    """Build a minimal system prompt for comparison runs."""
    parts = [
        "You are Maestro, a construction plan analysis partner for superintendents.",
        "Be honest about uncertainty. If you are unsure, say so.",
    ]
    if project_name:
        parts.append(f"Project: {project_name}")
    parts.append("Experience context (read-only):")
    parts.append(experience_context or "(No Experience context available.)")
    parts.append(
        "Answer the user's question using the Experience context and your knowledge."
    )
    return "\n\n".join(parts)


async def _run_single_model(
    model: str,
    messages: list[dict[str, Any]],
) -> tuple[str, int]:
    """Run a single model and return (response, latency_ms)."""
    start_time = time.time()
    response_text = ""

    async for chunk in chat_completion(messages, tools=[], model=model, stream=True):
        event_type = chunk.get("type")
        if event_type == "token":
            response_text += chunk.get("content") or ""
        elif event_type == "done":
            break

    latency_ms = int((time.time() - start_time) * 1000)
    return response_text, latency_ms


async def _evaluate_with_learning(
    user_query: str,
    maestro_response: str,
    db: DBSession,
) -> dict[str, float]:
    """
    Run Learning-style evaluation on a response.

    Returns emergent scoring dimensions {dimension: score}.
    This is a simplified version that uses the same model to score.
    """
    settings = get_settings()
    model = settings.learning_model

    eval_prompt = f"""Evaluate this Maestro response. Generate scoring dimensions that emerge from what you observe.

User query: {user_query}

Maestro response: {maestro_response}

Provide a JSON object with scoring dimensions (0-1 scale).
Common dimensions: retrieval_relevance, response_accuracy, gap_identification, confidence_calibration.
But let the interaction tell you what matters — don't force dimensions that don't apply.

Return ONLY a JSON object like: {{"dimension_name": score, ...}}"""

    messages = [{"role": "user", "content": eval_prompt}]

    response_text = ""
    async for chunk in chat_completion(messages, tools=[], model=model, stream=True):
        if chunk.get("type") == "token":
            response_text += chunk.get("content") or ""
        elif chunk.get("type") == "done":
            break

    # Parse JSON from response
    try:
        # Try to extract JSON from the response
        import re

        json_match = re.search(r"\{[^}]+\}", response_text)
        if json_match:
            return json.loads(json_match.group())
    except Exception:
        pass

    return {}


async def run_model_comparison(
    project_id: str | UUID,
    model_a: str,
    model_b: str,
    query_ids: Optional[list[str]] = None,
    limit: int = 20,
    db: Optional[DBSession] = None,
) -> list[ComparisonResult]:
    """
    Run model comparison on recent queries.

    For each query:
    1. Reconstruct the input: user_query + Experience context
    2. Run through Model A -> capture response
    3. Run through Model B -> capture response
    4. Run Learning evaluation on both responses
    5. Return comparison report

    Args:
        project_id: The project to run comparisons for
        model_a: First model to compare (e.g., "gemini-3-flash-preview")
        model_b: Second model to compare (e.g., "claude-opus-4-5")
        query_ids: Specific benchmark IDs to compare (optional)
        limit: Max number of queries to compare if query_ids not specified
        db: Database session

    Returns:
        List of ComparisonResult objects
    """
    if db is None:
        raise ValueError("Database session required for model comparison")

    project_id_str = str(project_id)

    # Get benchmark entries to compare
    if query_ids:
        entries = (
            db.query(BenchmarkLog)
            .filter(BenchmarkLog.id.in_(query_ids))
            .filter(BenchmarkLog.project_id == project_id_str)
            .all()
        )
    else:
        entries = (
            db.query(BenchmarkLog)
            .filter(BenchmarkLog.project_id == project_id_str)
            .order_by(BenchmarkLog.created_at.desc())
            .limit(limit)
            .all()
        )

    if not entries:
        logger.info("No benchmark entries found for comparison")
        return []

    results: list[ComparisonResult] = []

    for entry in entries:
        try:
            # Reconstruct Experience context
            experience_context, _ = read_experience_for_query(
                project_id=project_id_str,
                user_query=entry.user_query,
                db=db,
            )

            system_prompt = _build_comparison_system_prompt(experience_context)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": entry.user_query},
            ]

            # Run both models in parallel
            task_a = _run_single_model(model_a, messages)
            task_b = _run_single_model(model_b, messages)

            (response_a, latency_a), (response_b, latency_b) = await asyncio.gather(
                task_a, task_b
            )

            # Evaluate both responses
            eval_a = await _evaluate_with_learning(entry.user_query, response_a, db)
            eval_b = await _evaluate_with_learning(entry.user_query, response_b, db)

            result = ComparisonResult(
                query_id=entry.id,
                user_query=entry.user_query,
                original_response=entry.maestro_response,
                original_model=entry.response_model,
                original_scores=entry.scoring_dimensions,
                model_a=model_a,
                response_a=response_a,
                latency_a_ms=latency_a,
                scores_a=eval_a,
                model_b=model_b,
                response_b=response_b,
                latency_b_ms=latency_b,
                scores_b=eval_b,
            )
            results.append(result)

            logger.debug(
                "Compared query %s: %s (%dms) vs %s (%dms)",
                entry.id,
                model_a,
                latency_a,
                model_b,
                latency_b,
            )

        except Exception as exc:
            logger.warning("Failed to compare query %s: %s", entry.id, exc)
            continue

    return results


def format_comparison_report(results: list[ComparisonResult]) -> dict[str, Any]:
    """
    Format comparison results into a summary report.

    Returns:
        {
            model_a: str,
            model_b: str,
            total_queries: int,
            avg_latency_a_ms: float,
            avg_latency_b_ms: float,
            dimension_comparison: {dimension: {avg_a, avg_b, winner}},
            queries: [{query_id, user_query_preview, scores_a, scores_b}]
        }
    """
    if not results:
        return {"error": "No comparison results"}

    model_a = results[0].model_a
    model_b = results[0].model_b

    # Calculate averages
    latencies_a = [r.latency_a_ms for r in results]
    latencies_b = [r.latency_b_ms for r in results]

    # Aggregate scores by dimension
    dimension_scores_a: dict[str, list[float]] = {}
    dimension_scores_b: dict[str, list[float]] = {}

    for r in results:
        if r.scores_a:
            for dim, score in r.scores_a.items():
                dimension_scores_a.setdefault(dim, []).append(score)
        if r.scores_b:
            for dim, score in r.scores_b.items():
                dimension_scores_b.setdefault(dim, []).append(score)

    # Calculate dimension comparison
    all_dimensions = set(dimension_scores_a.keys()) | set(dimension_scores_b.keys())
    dimension_comparison = {}

    for dim in all_dimensions:
        scores_a = dimension_scores_a.get(dim, [])
        scores_b = dimension_scores_b.get(dim, [])
        avg_a = sum(scores_a) / len(scores_a) if scores_a else 0
        avg_b = sum(scores_b) / len(scores_b) if scores_b else 0

        winner = None
        if avg_a > avg_b + 0.05:
            winner = model_a
        elif avg_b > avg_a + 0.05:
            winner = model_b

        dimension_comparison[dim] = {
            "avg_a": round(avg_a, 3),
            "avg_b": round(avg_b, 3),
            "winner": winner,
        }

    return {
        "model_a": model_a,
        "model_b": model_b,
        "total_queries": len(results),
        "avg_latency_a_ms": round(sum(latencies_a) / len(latencies_a), 1),
        "avg_latency_b_ms": round(sum(latencies_b) / len(latencies_b), 1),
        "dimension_comparison": dimension_comparison,
        "queries": [
            {
                "query_id": r.query_id,
                "user_query_preview": r.user_query[:100],
                "scores_a": r.scores_a,
                "scores_b": r.scores_b,
            }
            for r in results
        ],
    }
