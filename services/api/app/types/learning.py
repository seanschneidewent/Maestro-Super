"""Learning-related types for Maestro V3."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InteractionPackage:
    """What Learning receives after each Maestro turn."""

    user_query: str
    maestro_response: str
    pointers_retrieved: list[dict]
    experience_context_used: list[str]
    workspace_actions: list[dict]
    turn_number: int
    timestamp: float
