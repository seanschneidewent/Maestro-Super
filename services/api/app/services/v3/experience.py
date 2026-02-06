"""
Experience file management for V3.

Handles seeding default Experience files when a project is created,
and reading Experience context for Maestro queries (Phase 2+).
"""

import logging
import re
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


def _parse_routing_rules(content: str) -> list[tuple[list[str], list[str]]]:
    """
    Parse routing_rules.md into keyword -> paths rules.

    Supports lines like:
      - cooler, walk-in -> subs/walk_in_cooler.md
      - concrete | slab => subs/concrete.md
      - foundations: subs/structural.md
    """
    rules: list[tuple[list[str], list[str]]] = []
    for raw_line in (content or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-", "*")):
            line = line[1:].strip()
        splitter = None
        for token in ("->", "=>", ":"):
            if token in line:
                splitter = token
                break
        if not splitter:
            continue
        left, right = line.split(splitter, 1)
        keywords = [
            kw.strip().strip('"').strip("'")
            for kw in re.split(r",|\bor\b|\|", left, flags=re.IGNORECASE)
            if kw.strip()
        ]
        paths = re.findall(r"[\w\-./]+\.md", right)
        if not paths:
            candidate = right.strip().strip('"').strip("'")
            if candidate.endswith(".md"):
                paths = [candidate]
        if keywords and paths:
            rules.append((keywords, paths))
    return rules


def read_experience_for_query(
    project_id: str,
    user_query: str,
    db: DBSession,
) -> tuple[str, list[str]]:
    """
    Read Experience context for a query.

    Returns a formatted context string and list of paths read.
    """
    default_paths = list(DEFAULT_EXPERIENCE_FILES.keys())
    files = (
        db.query(ExperienceFile)
        .filter(ExperienceFile.project_id == project_id)
        .filter(ExperienceFile.path.in_(default_paths))
        .all()
    )
    file_map = {f.path: f.content for f in files}

    routing_content = file_map.get("routing_rules.md", "")
    rules = _parse_routing_rules(routing_content)

    matched_paths: list[str] = []
    query_lower = (user_query or "").lower()
    for keywords, paths in rules:
        if any(keyword.lower() in query_lower for keyword in keywords):
            matched_paths.extend(paths)

    # Deduplicate while preserving order
    seen: set[str] = set()
    ordered_paths: list[str] = []
    for path in [*default_paths, *matched_paths]:
        if path in seen:
            continue
        seen.add(path)
        ordered_paths.append(path)

    # Fetch matched extended files
    extended_paths = [p for p in ordered_paths if p not in file_map]
    if extended_paths:
        extended_files = (
            db.query(ExperienceFile)
            .filter(ExperienceFile.project_id == project_id)
            .filter(ExperienceFile.path.in_(extended_paths))
            .all()
        )
        for f in extended_files:
            file_map[f.path] = f.content

    sections: list[str] = []
    paths_read: list[str] = []
    for path in ordered_paths:
        content = file_map.get(path)
        if content is None:
            continue
        paths_read.append(path)
        sections.append(f"## {path}\n{content.strip()}")

    context = "\n\n".join(sections).strip()
    return context, paths_read
