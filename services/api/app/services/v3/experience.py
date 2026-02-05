"""
Experience file management for V3.

Handles seeding default Experience files when a project is created,
and reading Experience context for Maestro queries (Phase 2+).
"""

import logging
from uuid import uuid4

from sqlalchemy.orm import Session as DBSession

from app.models.experience_file import ExperienceFile

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Default Experience files — seeded on project creation
# ─────────────────────────────────────────────────────────────────────

DEFAULT_EXPERIENCE_FILES: dict[str, str] = {
    "routing_rules.md": """# Routing Rules

## Default Routes
- Equipment queries → check Pointer cross-references to E-series pages
- Dimension queries → include detail sheets + plan views for cross-verification

## Extended Knowledge
<!-- Learning agent adds entries here as deep threads emerge -->

## Learned Patterns
<!-- Learning agent adds observed user patterns here -->
""",
    "corrections.md": """# Corrections

<!-- Truth corrections from the superintendent.
     Learning agent logs corrections here when the user
     identifies errors in Maestro's responses or Knowledge. -->
""",
    "preferences.md": """# User Preferences

<!-- Behavioral patterns observed by Learning.
     Examples: "Super always wants dimensions first, then specs"
     "Prefers short answers on Telegram, detailed in workspace" -->
""",
    "schedule.md": """# Project Schedule

<!-- Schedule information gathered from conversations.
     Learning agent updates this when the super shares
     scheduling info via workspace or Telegram. -->

## Active
<!-- Currently active work items -->

## Coming Up
<!-- Upcoming work items and milestones -->

## Notes
<!-- Scheduling notes from the superintendent -->
""",
    "gaps.md": """# Knowledge Gaps

<!-- Tracked gaps in Maestro's understanding.
     Learning agent logs gaps here when Maestro flags
     uncertainty or the user reveals missing information. -->

## Open Gaps
<!-- Unresolved gaps -->

## Resolved
<!-- Gaps that have been filled -->
""",
}


def seed_default_experience(project_id: str, db: DBSession) -> int:
    """
    Seed default Experience files for a new project.

    Creates the 5 default files (routing_rules, corrections, preferences,
    schedule, gaps) with starter content. Uses INSERT ... ON CONFLICT
    DO NOTHING so this is idempotent.

    Args:
        project_id: The project to seed Experience for
        db: Database session

    Returns:
        Number of files created (0 if all already existed)
    """
    created = 0

    for path, content in DEFAULT_EXPERIENCE_FILES.items():
        # Check if already exists (idempotent)
        existing = (
            db.query(ExperienceFile)
            .filter(
                ExperienceFile.project_id == project_id,
                ExperienceFile.path == path,
            )
            .first()
        )
        if existing:
            continue

        file = ExperienceFile(
            id=str(uuid4()),
            project_id=project_id,
            path=path,
            content=content,
        )
        db.add(file)
        created += 1

    if created > 0:
        db.commit()
        logger.info(
            "Seeded %d default Experience files for project %s",
            created,
            project_id,
        )

    return created
