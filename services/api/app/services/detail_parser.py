"""
Detail Parser - Extract structured detail information from Gemini markdown.

Parses markdown sections like:
    ### EMBEDDED POST DETAIL (8)
    - **Shows:** 2-1/2" sq post embedded in concrete...
    - **Materials:** CONC., REINFORCEMENT BAR
    - **Dimensions:** 2-1/2", 1/4" DIA.

Into structured JSON:
    {
        "title": "EMBEDDED POST DETAIL",
        "number": "8",
        "shows": "2-1/2\" sq post embedded...",
        "materials": ["CONC.", "REINFORCEMENT BAR"],
        "dimensions": ["2-1/2\"", "1/4\" DIA."]
    }
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def parse_detail_section(section: str) -> Optional[dict]:
    """
    Parse a single detail section from markdown.

    Args:
        section: Markdown text starting with ### DETAIL NAME

    Returns:
        Structured detail dict or None if parsing fails
    """
    lines = section.strip().split('\n')
    if not lines:
        return None

    # Parse header: ### DETAIL NAME (number) or ### DETAIL NAME
    header = lines[0].lstrip('#').strip()

    # Extract detail number if present: "DETAIL NAME (8)" or "DETAIL NAME (8/A601)"
    number_match = re.search(r'\(([^)]+)\)\s*$', header)
    if number_match:
        detail_number = number_match.group(1)
        detail_title = header[:number_match.start()].strip()
    else:
        detail_number = None
        detail_title = header

    detail = {
        "title": detail_title,
        "number": detail_number,
        "shows": None,
        "materials": [],
        "dimensions": [],
        "notes": None
    }

    # Parse bullet points
    current_field = None
    for line in lines[1:]:
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # Check for field markers: - **Shows:** or **Shows:**
        field_match = re.match(r'^[-*]?\s*\*\*([^:*]+)\*\*:\s*(.*)$', line)
        if field_match:
            field_name = field_match.group(1).lower().strip()
            field_value = field_match.group(2).strip()

            if field_name == 'shows':
                detail['shows'] = field_value
            elif field_name == 'materials':
                # Split by comma, handling edge cases
                if field_value:
                    detail['materials'] = [m.strip() for m in re.split(r',\s*', field_value) if m.strip()]
            elif field_name == 'dimensions':
                if field_value:
                    detail['dimensions'] = [d.strip() for d in re.split(r',\s*', field_value) if d.strip()]
            elif field_name in ('notes', 'note'):
                detail['notes'] = field_value

            current_field = field_name
        elif current_field and line.startswith('-'):
            # Continuation list item
            item = line.lstrip('-').strip()
            if current_field == 'materials' and item:
                detail['materials'].append(item)
            elif current_field == 'dimensions' and item:
                detail['dimensions'].append(item)

    return detail if detail['title'] else None


def parse_context_markdown(markdown: str) -> list[dict]:
    """
    Parse full context markdown and extract all details.

    Args:
        markdown: Full markdown output from generate_context_markdown()

    Returns:
        List of detail dicts
    """
    if not markdown:
        return []

    details = []

    # Split by ### headers (detail sections)
    # Pattern: ### followed by anything that's not another header
    sections = re.split(r'(?=^###\s+)', markdown, flags=re.MULTILINE)

    for section in sections:
        section = section.strip()
        if not section or not section.startswith('###'):
            continue

        # Skip non-detail sections (Sheet Overview, General Notes, etc.)
        header_line = section.split('\n')[0].lower()
        skip_headers = ['sheet overview', 'general notes', 'notes', 'references', 'legend']
        if any(skip in header_line for skip in skip_headers):
            continue

        # Parse as detail
        detail = parse_detail_section(section)
        if detail:
            details.append(detail)

    logger.info(f"Parsed {len(details)} details from markdown")
    return details


def extract_sheet_info(markdown: str) -> dict:
    """
    Extract sheet-level info from markdown.

    Args:
        markdown: Full context markdown

    Returns:
        Dict with sheet_number, title, scales, references
    """
    info = {
        "sheet_number": None,
        "title": None,
        "scales": [],
        "references": []
    }

    if not markdown:
        return info

    # Look for Sheet Overview section
    overview_match = re.search(
        r'##\s*Sheet Overview\s*\n(.*?)(?=\n##|\Z)',
        markdown,
        re.DOTALL | re.IGNORECASE
    )

    if overview_match:
        overview = overview_match.group(1)

        # Extract sheet number and title
        # Pattern: "A101 - FLOOR PLAN" or "Sheet: A101" or "- Sheet number: A101"
        sheet_match = re.search(
            r'(?:sheet[:\s]+|^[-*]\s*)([A-Z]?\d+(?:\.\d+)?)\s*[-–—]\s*([^\n]+)',
            overview,
            re.IGNORECASE | re.MULTILINE
        )
        if sheet_match:
            info['sheet_number'] = sheet_match.group(1).strip()
            info['title'] = sheet_match.group(2).strip()

        # Extract scales
        scale_matches = re.findall(
            r'(\d+(?:/\d+)?["\']?\s*=\s*\d+[\'"-]+\d*["\']?)',
            overview
        )
        if scale_matches:
            info['scales'] = list(set(scale_matches))

        # Extract references
        ref_matches = re.findall(
            r'([A-Z]?\d+/[A-Z]+\d+(?:\.\d+)?)',
            overview
        )
        if ref_matches:
            info['references'] = list(set(ref_matches))

    return info
