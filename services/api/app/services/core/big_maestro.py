"""
Big Maestro - The orchestrating agent with memory.

Big Maestro is a superintendent's partner that:
- Holds deep context about the project and user
- Detects corrections and teaching intent
- Updates memory files based on learning
- Spawns sub-agents (Fast/Med/Deep) with context injection
- Shows visible thinking during learning
"""

import logging
import re
from typing import Any, AsyncIterator, Literal, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.memory import (
    build_memory_context,
    append_to_memory_file,
    log_learning_event,
    get_memory_file_content,
    upsert_memory_file,
    FILE_TYPE_CORE,
    FILE_TYPE_ROUTING,
    FILE_TYPE_PREFERENCES,
    FILE_TYPE_FAST_CONTEXT,
    FILE_TYPE_MED_CONTEXT,
    FILE_TYPE_DEEP_CONTEXT,
    FILE_TYPE_LEARNING,
)

logger = logging.getLogger(__name__)

# Patterns that indicate correction/teaching intent
CORRECTION_PATTERNS = [
    r"\bno[,.]?\s+(?:that'?s?\s+)?(?:wrong|incorrect|not right)",
    r"\byou(?:'re|\s+are)?\s+(?:wrong|incorrect|missing)",
    r"\bthat'?s?\s+not\s+(?:right|correct|it)",
    r"\byou\s+missed",
    r"\byou\s+forgot",
    r"\bactually[,.]?\s+(?:it'?s?|the)",
    r"\bshould\s+(?:be|have|also|include|check)",
    r"\balways\s+(?:check|include|look|use)",
    r"\bnever\s+(?:use|include|check)",
    r"\bdon'?t\s+forget",
    r"\bmake\s+sure\s+(?:to|you)",
    r"\bremember\s+(?:to|that)",
    r"\b(?:on\s+)?this\s+project[,.]?\s+(?:\w+\s+)?means?",
    r"\bhere[,.]?\s+(?:\w+\s+)?means?",
    r"\bwhen\s+(?:i|someone)\s+asks?\s+(?:about|for)",
    r"\bfor\s+(?:\w+\s+)?questions?\s+(?:about|on)",
]

# Patterns that indicate specific learning types
ROUTING_PATTERNS = [
    r"\bcheck\s+(?:sheet\s+)?([A-Z]?-?\d+(?:\.\d+)?)",
    r"\bon\s+(?:sheet\s+)?([A-Z]?-?\d+(?:\.\d+)?)",
    r"\bsheet\s+([A-Z]?-?\d+(?:\.\d+)?)\s+(?:has|shows|contains)",
    r"\b([A-Z]?-?\d+(?:\.\d+)?)\s+(?:has|shows|contains)",
    r"\blook\s+(?:at|on)\s+(?:sheet\s+)?([A-Z]?-?\d+(?:\.\d+)?)",
    r"\binclude\s+(?:sheet\s+)?([A-Z]?-?\d+(?:\.\d+)?)",
]

TRUTH_PATTERNS = [
    r"\bmeans?\s+",
    r"\brefers?\s+to",
    r"\bis\s+(?:the|called|known)",
    r"\bon\s+this\s+project",
    r"\bhere[,.]",
    r"\bwe\s+call\s+(?:it|that|this)",
]

PREFERENCE_PATTERNS = [
    r"\balways\s+(?:cite|include|show|give)",
    r"\bi\s+(?:like|prefer|want)\s+",
    r"\bkeep\s+(?:it|responses?)\s+",
    r"\bdon'?t\s+(?:need|want)\s+",
]

AGENT_BEHAVIOR_PATTERNS = [
    r"\bfast\s+mode\s+(?:should|needs?|keeps?)",
    r"\bmed\s+mode\s+(?:should|needs?|keeps?)",
    r"\bdeep\s+mode\s+(?:should|needs?|keeps?)",
    r"\bwhen\s+(?:doing\s+)?(?:fast|quick)\s+",
    r"\bwhen\s+(?:doing\s+)?(?:detail|med)",
    r"\bwhen\s+(?:extracting|verifying|deep)",
]


def detect_teaching_intent(query: str, previous_response: Optional[str] = None) -> bool:
    """
    Detect if the user's message contains correction or teaching intent.
    
    Returns True if the message appears to be teaching/correcting rather than asking.
    """
    query_lower = query.lower()
    
    # Check for correction patterns
    for pattern in CORRECTION_PATTERNS:
        if re.search(pattern, query_lower):
            return True
    
    # Check if it's a statement about sheets (likely teaching) vs a question
    has_sheet_reference = bool(re.search(r"[A-Z]?-?\d+(?:\.\d+)?", query))
    is_question = query.strip().endswith("?") or query_lower.startswith(("what", "where", "which", "how", "can", "could", "would", "is", "are", "does", "do"))
    
    if has_sheet_reference and not is_question:
        # Statements about sheets are often teaching
        teaching_verbs = ["has", "shows", "contains", "is on", "check", "look at", "include", "always"]
        if any(verb in query_lower for verb in teaching_verbs):
            return True
    
    return False


def classify_learning(query: str) -> dict[str, Any]:
    """
    Classify what type of learning this is and which file to update.
    
    Returns:
        {
            "type": "routing" | "truth" | "preference" | "fast_behavior" | "med_behavior" | "deep_behavior",
            "file_type": FILE_TYPE_*,
            "confidence": float,
            "extracted_content": str | None,
        }
    """
    query_lower = query.lower()
    
    # Check for agent-specific behavior first
    for pattern in AGENT_BEHAVIOR_PATTERNS:
        if re.search(pattern, query_lower):
            if "fast" in query_lower:
                return {
                    "type": "fast_behavior",
                    "file_type": FILE_TYPE_FAST_CONTEXT,
                    "confidence": 0.9,
                    "extracted_content": None,
                }
            elif "med" in query_lower or "detail" in query_lower:
                return {
                    "type": "med_behavior",
                    "file_type": FILE_TYPE_MED_CONTEXT,
                    "confidence": 0.9,
                    "extracted_content": None,
                }
            elif "deep" in query_lower or "extract" in query_lower or "verif" in query_lower:
                return {
                    "type": "deep_behavior",
                    "file_type": FILE_TYPE_DEEP_CONTEXT,
                    "confidence": 0.9,
                    "extracted_content": None,
                }
    
    # Check for preference patterns
    for pattern in PREFERENCE_PATTERNS:
        if re.search(pattern, query_lower):
            return {
                "type": "preference",
                "file_type": FILE_TYPE_PREFERENCES,
                "confidence": 0.85,
                "extracted_content": None,
            }
    
    # Check for truth/terminology patterns
    for pattern in TRUTH_PATTERNS:
        if re.search(pattern, query_lower):
            return {
                "type": "truth",
                "file_type": FILE_TYPE_CORE,
                "confidence": 0.85,
                "extracted_content": None,
            }
    
    # Check for routing patterns (most common)
    for pattern in ROUTING_PATTERNS:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            sheet_ref = match.group(1) if match.groups() else None
            return {
                "type": "routing",
                "file_type": FILE_TYPE_ROUTING,
                "confidence": 0.9,
                "extracted_content": sheet_ref,
            }
    
    # Default to routing if it mentions sheets
    if re.search(r"[A-Z]?-?\d+(?:\.\d+)?", query):
        return {
            "type": "routing",
            "file_type": FILE_TYPE_ROUTING,
            "confidence": 0.7,
            "extracted_content": None,
        }
    
    # Can't classify with confidence
    return {
        "type": "unknown",
        "file_type": None,
        "confidence": 0.3,
        "extracted_content": None,
    }


def extract_learning_content(query: str, classification: dict[str, Any]) -> str:
    """
    Extract the content to be added to the memory file.
    
    Formats the learning in a concise, actionable way.
    """
    learning_type = classification.get("type", "unknown")
    
    # Clean up the query for storage
    query_clean = query.strip()
    
    # Remove common prefixes
    prefixes_to_remove = [
        r"^no[,.]?\s*",
        r"^actually[,.]?\s*",
        r"^you\s+missed[,.]?\s*",
        r"^remember[,.]?\s*",
        r"^make\s+sure[,.]?\s*",
    ]
    for prefix in prefixes_to_remove:
        query_clean = re.sub(prefix, "", query_clean, flags=re.IGNORECASE)
    
    # Format based on type
    if learning_type == "routing":
        # Extract subject and sheets
        sheets = re.findall(r"[A-Z]?-?\d+(?:\.\d+)?", query_clean)
        sheets_str = ", ".join(sheets) if sheets else "check relevant sheets"
        
        # Try to extract subject
        subject_patterns = [
            r"(?:for|about|on)\s+(?:the\s+)?(\w+(?:\s+\w+)?)",
            r"(\w+(?:\s+\w+)?)\s+(?:is|are|should|check)",
        ]
        subject = None
        for pattern in subject_patterns:
            match = re.search(pattern, query_clean, re.IGNORECASE)
            if match:
                subject = match.group(1)
                break
        
        if subject:
            return f"- {subject} → {sheets_str}"
        else:
            return f"- {query_clean}"
    
    elif learning_type == "truth":
        return f"- {query_clean}"
    
    elif learning_type == "preference":
        return f"- {query_clean}"
    
    elif learning_type in ("fast_behavior", "med_behavior", "deep_behavior"):
        return f"- {query_clean}"
    
    else:
        return f"- {query_clean}"


async def process_learning(
    db: Session,
    project_id: UUID,
    user_id: str,
    query: str,
    previous_query: Optional[str] = None,
    previous_response: Optional[str] = None,
) -> AsyncIterator[dict]:
    """
    Process a learning/teaching message.
    
    Yields thinking events showing the learning process, then updates memory.
    
    Yields:
        {"type": "thinking", "content": "..."}
        {"type": "learning_complete", "file_updated": "...", "content_added": "..."}
    """
    # Classify the learning
    classification = classify_learning(query)
    learning_type = classification.get("type", "unknown")
    file_type = classification.get("file_type")
    confidence = classification.get("confidence", 0.0)
    
    # Yield thinking about classification
    yield {
        "type": "thinking",
        "content": f"I see you're teaching me. Classifying: {learning_type} (confidence: {confidence:.0%})"
    }
    
    if not file_type or confidence < 0.5:
        yield {
            "type": "thinking", 
            "content": "I'm not quite sure how to classify this. Could you clarify what you'd like me to remember?"
        }
        yield {
            "type": "clarification_needed",
            "question": "Could you tell me more specifically what you'd like me to remember? For example:\n- Is this about where to find something in the plans?\n- Is this about what a term means on this project?\n- Is this about how you prefer responses?"
        }
        return
    
    # Extract the content to add
    content_to_add = extract_learning_content(query, classification)
    
    yield {
        "type": "thinking",
        "content": f"Updating {file_type}: {content_to_add}"
    }
    
    # Determine which section to add to
    section_map = {
        FILE_TYPE_ROUTING: _infer_routing_section(query),
        FILE_TYPE_CORE: "Terminology" if "means" in query.lower() else "Project-Specific Notes",
        FILE_TYPE_PREFERENCES: "Communication Style",
        FILE_TYPE_FAST_CONTEXT: "Routing Overrides",
        FILE_TYPE_MED_CONTEXT: "Display Preferences",
        FILE_TYPE_DEEP_CONTEXT: "Verification Rules",
    }
    section = section_map.get(file_type, None)
    
    # Update the memory file
    await append_to_memory_file(
        db, project_id, user_id, file_type, content_to_add, section
    )
    
    # Log the learning event
    await log_learning_event(
        db,
        project_id=project_id,
        user_id=user_id,
        event_type="teaching",
        classification=learning_type,
        original_query=previous_query,
        original_response=previous_response,
        correction_text=query,
        file_updated=file_type,
        update_content=content_to_add,
    )
    
    # Also update the learning log
    from datetime import datetime
    log_entry = f"| {datetime.now().strftime('%Y-%m-%d %H:%M')} | {query[:50]}... | {file_type} |"
    await append_to_memory_file(
        db, project_id, user_id, FILE_TYPE_LEARNING, log_entry, None
    )
    
    yield {
        "type": "thinking",
        "content": f"Got it. I've updated my {_file_type_to_display(file_type)}."
    }
    
    yield {
        "type": "learning_complete",
        "file_updated": file_type,
        "content_added": content_to_add,
        "classification": learning_type,
    }


def _infer_routing_section(query: str) -> str:
    """Infer which section of ROUTING.md to add to based on query content."""
    query_lower = query.lower()
    
    if any(term in query_lower for term in ["electrical", "panel", "circuit", "e-"]):
        return "Electrical"
    elif any(term in query_lower for term in ["mechanical", "hvac", "duct", "m-"]):
        return "Mechanical"
    elif any(term in query_lower for term in ["plumbing", "pipe", "fixture", "p-"]):
        return "Plumbing"
    elif any(term in query_lower for term in ["detail", "d-"]):
        return "Details"
    elif any(term in query_lower for term in ["equipment", "appliance", "cooler", "hood"]):
        return "Equipment"
    elif any(term in query_lower for term in ["cross", "reference", "see also"]):
        return "Cross-References"
    else:
        return "Equipment"  # Default


def _file_type_to_display(file_type: str) -> str:
    """Convert file type to display name."""
    display_map = {
        FILE_TYPE_CORE: "project notes",
        FILE_TYPE_ROUTING: "routing knowledge",
        FILE_TYPE_PREFERENCES: "preferences",
        FILE_TYPE_MEMORY: "memory",
        FILE_TYPE_LEARNING: "learning log",
        FILE_TYPE_FAST_CONTEXT: "fast mode context",
        FILE_TYPE_MED_CONTEXT: "med mode context",
        FILE_TYPE_DEEP_CONTEXT: "deep mode context",
    }
    return display_map.get(file_type, file_type)


async def run_with_learning(
    db: Session,
    project_id: str,
    user_id: str,
    query: str,
    history_messages: list[dict[str, Any]] | None = None,
    viewing_context: dict[str, Any] | None = None,
    mode: Literal["fast", "med", "deep"] = "fast",
) -> AsyncIterator[dict]:
    """
    Main entry point for Big Maestro.
    
    Detects if query is teaching/correction, processes learning if so,
    then runs the appropriate agent with memory context injected.
    
    Yields all events from learning and query processing.
    """
    from app.services.core.agent import run_agent_query
    
    project_uuid = UUID(project_id) if isinstance(project_id, str) else project_id
    
    # Get previous query/response from history for context
    previous_query = None
    previous_response = None
    if history_messages and len(history_messages) >= 2:
        for msg in reversed(history_messages):
            if msg.get("role") == "assistant" and not previous_response:
                previous_response = msg.get("content", "")
            elif msg.get("role") == "user" and not previous_query:
                previous_query = msg.get("content", "")
            if previous_query and previous_response:
                break
    
    # Check if this is teaching/correction
    is_teaching = detect_teaching_intent(query, previous_response)
    
    if is_teaching:
        # Process the learning
        async for event in process_learning(
            db, project_uuid, user_id, query, previous_query, previous_response
        ):
            yield event
        
        # Check if we need clarification
        # If the last event was clarification_needed, don't continue to query
        # (The frontend should handle this and wait for user response)
        
        # If learning is complete, offer to retry
        yield {
            "type": "text",
            "content": "Want me to try that again with this new knowledge, or is there something else?"
        }
        yield {"type": "done", "trace": [], "usage": {}}
        return
    
    # Not teaching - run normal query with memory context
    # Build memory context for injection
    memory_context = await build_memory_context(db, project_uuid, user_id, mode)
    
    # For now, we'll pass memory context through viewing_context
    # (TODO: Modify agent to accept memory_context directly)
    enriched_viewing_context = viewing_context or {}
    if memory_context:
        enriched_viewing_context["memory_context"] = memory_context
    
    # Run the normal agent
    async for event in run_agent_query(
        db, project_id, query, history_messages, enriched_viewing_context, mode
    ):
        yield event
