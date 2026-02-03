"""
Memory file management service for Big Maestro.

Handles CRUD operations for project memory files and learning events.
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.models.project_memory import ProjectMemoryFile, LearningEvent

logger = logging.getLogger(__name__)

# File type constants
FILE_TYPE_CORE = "core"
FILE_TYPE_ROUTING = "routing"
FILE_TYPE_PREFERENCES = "preferences"
FILE_TYPE_MEMORY = "memory"
FILE_TYPE_LEARNING = "learning"
FILE_TYPE_FAST_CONTEXT = "fast_context"
FILE_TYPE_MED_CONTEXT = "med_context"
FILE_TYPE_DEEP_CONTEXT = "deep_context"

ALL_FILE_TYPES = [
    FILE_TYPE_CORE,
    FILE_TYPE_ROUTING,
    FILE_TYPE_PREFERENCES,
    FILE_TYPE_MEMORY,
    FILE_TYPE_LEARNING,
    FILE_TYPE_FAST_CONTEXT,
    FILE_TYPE_MED_CONTEXT,
    FILE_TYPE_DEEP_CONTEXT,
]

# Default file contents (templates)
DEFAULT_FILE_CONTENTS = {
    FILE_TYPE_CORE: """# Project Truths

*Things that are always true on this project.*

## Terminology


## Key Relationships


## Project-Specific Notes

""",
    FILE_TYPE_ROUTING: """# Routing

*Where to find things in the plans.*

## Equipment


## Electrical


## Mechanical


## Plumbing


## Details


## Cross-References

""",
    FILE_TYPE_PREFERENCES: """# User Preferences

*How this superintendent likes to work.*

## Communication Style


## Response Format


## Priorities

""",
    FILE_TYPE_MEMORY: """# Conversation Memory

*Context from recent conversations.*

## Recent Context


## Ongoing Threads


## Open Questions

""",
    FILE_TYPE_LEARNING: """# Learning Log

*Record of what's been taught.*

| Date | What Was Taught | File Updated |
|------|-----------------|--------------|

""",
    FILE_TYPE_FAST_CONTEXT: """# Fast Mode Context

*Nudges for quick sheet identification.*

## Routing Overrides


## Always Check


## Common Mistakes

""",
    FILE_TYPE_MED_CONTEXT: """# Med Mode Context

*Nudges for region highlighting.*

## Display Preferences


## Detail Level


## Region Handling

""",
    FILE_TYPE_DEEP_CONTEXT: """# Deep Mode Context

*Nudges for verified extraction.*

## Verification Rules


## Extraction Patterns


## Precision Requirements


## Source Priority

""",
}


async def get_memory_file(
    db: Session,
    project_id: UUID,
    user_id: str,
    file_type: str,
) -> Optional[ProjectMemoryFile]:
    """Get a specific memory file for a project."""
    return db.query(ProjectMemoryFile).filter(
        ProjectMemoryFile.project_id == project_id,
        ProjectMemoryFile.file_type == file_type,
    ).first()


async def get_memory_file_content(
    db: Session,
    project_id: UUID,
    user_id: str,
    file_type: str,
) -> str:
    """Get memory file content, returning default template if not exists."""
    file = await get_memory_file(db, project_id, user_id, file_type)
    if file:
        return file.file_content or ""
    return DEFAULT_FILE_CONTENTS.get(file_type, "")


async def get_all_memory_files(
    db: Session,
    project_id: UUID,
    user_id: str,
) -> dict[str, str]:
    """Get all memory files for a project as a dict of type -> content."""
    files = db.query(ProjectMemoryFile).filter(
        ProjectMemoryFile.project_id == project_id,
    ).all()
    
    result = {}
    for file in files:
        result[file.file_type] = file.file_content or ""
    
    # Fill in defaults for missing files
    for file_type in ALL_FILE_TYPES:
        if file_type not in result:
            result[file_type] = DEFAULT_FILE_CONTENTS.get(file_type, "")
    
    return result


async def upsert_memory_file(
    db: Session,
    project_id: UUID,
    user_id: str,
    file_type: str,
    content: str,
) -> ProjectMemoryFile:
    """Create or update a memory file."""
    existing = await get_memory_file(db, project_id, user_id, file_type)
    
    if existing:
        existing.file_content = content
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing
    else:
        new_file = ProjectMemoryFile(
            project_id=project_id,
            user_id=user_id,
            file_type=file_type,
            file_content=content,
        )
        db.add(new_file)
        db.commit()
        db.refresh(new_file)
        return new_file


async def append_to_memory_file(
    db: Session,
    project_id: UUID,
    user_id: str,
    file_type: str,
    content_to_append: str,
    section: Optional[str] = None,
) -> ProjectMemoryFile:
    """Append content to a memory file, optionally to a specific section."""
    current_content = await get_memory_file_content(db, project_id, user_id, file_type)
    
    if section:
        # Try to find the section and append after it
        section_marker = f"## {section}"
        if section_marker in current_content:
            # Find the next section or end of file
            section_start = current_content.index(section_marker)
            section_end = len(current_content)
            
            # Look for next ## header
            remaining = current_content[section_start + len(section_marker):]
            next_section = remaining.find("\n## ")
            if next_section != -1:
                section_end = section_start + len(section_marker) + next_section
            
            # Insert content before next section
            new_content = (
                current_content[:section_end].rstrip() + 
                "\n" + content_to_append.strip() + "\n\n" +
                current_content[section_end:].lstrip()
            )
        else:
            # Section not found, append to end
            new_content = current_content.rstrip() + "\n\n" + content_to_append.strip() + "\n"
    else:
        # Just append to end
        new_content = current_content.rstrip() + "\n\n" + content_to_append.strip() + "\n"
    
    return await upsert_memory_file(db, project_id, user_id, file_type, new_content)


async def log_learning_event(
    db: Session,
    project_id: UUID,
    user_id: str,
    event_type: str,
    classification: Optional[str] = None,
    original_query: Optional[str] = None,
    original_response: Optional[str] = None,
    correction_text: Optional[str] = None,
    file_updated: Optional[str] = None,
    update_content: Optional[str] = None,
) -> LearningEvent:
    """Log a learning event."""
    event = LearningEvent(
        project_id=project_id,
        user_id=user_id,
        event_type=event_type,
        classification=classification,
        original_query=original_query,
        original_response=original_response,
        correction_text=correction_text,
        file_updated=file_updated,
        update_content=update_content,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


async def get_recent_learning_events(
    db: Session,
    project_id: UUID,
    limit: int = 10,
) -> list[LearningEvent]:
    """Get recent learning events for a project."""
    return db.query(LearningEvent).filter(
        LearningEvent.project_id == project_id,
    ).order_by(
        LearningEvent.created_at.desc()
    ).limit(limit).all()


async def build_memory_context(
    db: Session,
    project_id: UUID,
    user_id: str,
    mode: str = "fast",
) -> str:
    """
    Build memory context string for injection into agent prompts.
    
    Returns a formatted string with relevant memory content based on mode.
    """
    files = await get_all_memory_files(db, project_id, user_id)
    
    context_parts = []
    
    # Always include core and routing (if they have content beyond template)
    core = files.get(FILE_TYPE_CORE, "").strip()
    if core and "## Terminology" in core and len(core) > 100:
        context_parts.append("## Project Notes\n" + _extract_filled_sections(core))
    
    routing = files.get(FILE_TYPE_ROUTING, "").strip()
    if routing and len(routing) > 100:
        context_parts.append("## Routing Notes\n" + _extract_filled_sections(routing))
    
    preferences = files.get(FILE_TYPE_PREFERENCES, "").strip()
    if preferences and len(preferences) > 100:
        context_parts.append("## User Preferences\n" + _extract_filled_sections(preferences))
    
    # Add mode-specific context
    mode_file_map = {
        "fast": FILE_TYPE_FAST_CONTEXT,
        "med": FILE_TYPE_MED_CONTEXT,
        "deep": FILE_TYPE_DEEP_CONTEXT,
    }
    mode_file_type = mode_file_map.get(mode.lower())
    if mode_file_type:
        mode_content = files.get(mode_file_type, "").strip()
        if mode_content and len(mode_content) > 100:
            context_parts.append(f"## {mode.title()} Mode Notes\n" + _extract_filled_sections(mode_content))
    
    if not context_parts:
        return ""
    
    return "\n\n".join(context_parts)


def _extract_filled_sections(content: str) -> str:
    """Extract only sections that have content (not just headers)."""
    lines = content.split("\n")
    result_lines = []
    current_section = []
    in_section = False
    
    for line in lines:
        if line.startswith("## "):
            # New section - save previous if it had content
            if current_section and any(l.strip() and not l.startswith("#") for l in current_section):
                result_lines.extend(current_section)
                result_lines.append("")
            current_section = [line]
            in_section = True
        elif line.startswith("# "):
            # Skip top-level headers
            continue
        elif in_section:
            current_section.append(line)
    
    # Don't forget the last section
    if current_section and any(l.strip() and not l.startswith("#") for l in current_section):
        result_lines.extend(current_section)
    
    return "\n".join(result_lines).strip()
