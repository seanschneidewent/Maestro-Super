"""Telegram message formatting utilities.

Converts Maestro responses to Telegram-compatible format:
- Escapes special characters for MarkdownV2
- Converts tables to bullet lists
- Splits long messages (Telegram max: 4096 chars)
"""

import re


# Characters that need escaping in Telegram MarkdownV2
# See: https://core.telegram.org/bots/api#markdownv2-style
ESCAPE_CHARS = r"_*[]()~`>#+-=|{}.!"


def escape_markdown_v2(text: str) -> str:
    """
    Escape special characters for Telegram MarkdownV2.

    Note: This escapes ALL special characters. For formatted text,
    use format_for_telegram() which handles formatting conversion.
    """
    pattern = f"([{re.escape(ESCAPE_CHARS)}])"
    return re.sub(pattern, r"\\\1", text)


def _convert_bold(text: str) -> str:
    """Convert **bold** to Telegram *bold*."""
    # Match **text** but not ****
    return re.sub(r"\*\*([^*]+)\*\*", r"*\1*", text)


def _convert_italic(text: str) -> str:
    """Convert _italic_ to Telegram _italic_ (already compatible)."""
    return text


def _convert_code(text: str) -> str:
    """Convert `code` to Telegram `code` (already compatible)."""
    return text


def _convert_code_blocks(text: str) -> str:
    """Convert ```code blocks``` to Telegram format."""
    # Telegram supports ```language\ncode\n```
    # This is already compatible
    return text


def _convert_links(text: str) -> str:
    """Convert [text](url) to Telegram format (already compatible)."""
    return text


def _convert_tables_to_lists(text: str) -> str:
    """
    Convert markdown tables to bullet lists.

    Telegram doesn't support tables, so we convert:
    | Header1 | Header2 |
    |---------|---------|
    | Cell1   | Cell2   |

    To:
    - Header1: Cell1
    - Header2: Cell2
    """
    lines = text.split("\n")
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Check if this looks like a table row
        if "|" in line and line.strip().startswith("|"):
            # Collect all table rows
            table_rows = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip().startswith("|"):
                row = lines[i].strip()
                # Skip separator rows (|---|---|)
                if not re.match(r"^\|[\s\-:|]+\|$", row):
                    # Extract cells
                    cells = [c.strip() for c in row.split("|")[1:-1]]
                    if cells:
                        table_rows.append(cells)
                i += 1

            # Convert to bullet list
            if len(table_rows) >= 1:
                headers = table_rows[0] if table_rows else []
                data_rows = table_rows[1:] if len(table_rows) > 1 else []

                if not data_rows:
                    # Just headers, list them
                    for header in headers:
                        if header:
                            result.append(f"- {header}")
                else:
                    # Headers + data
                    for row in data_rows:
                        for j, cell in enumerate(row):
                            if j < len(headers) and headers[j]:
                                result.append(f"- {headers[j]}: {cell}")
                            elif cell:
                                result.append(f"- {cell}")
                        result.append("")  # Blank line between rows
        else:
            result.append(line)
            i += 1

    return "\n".join(result)


def _escape_outside_formatting(text: str) -> str:
    """
    Escape special characters outside of formatting markers.

    This is a simplified approach that:
    1. Preserves *bold*, _italic_, `code`, and [links](url)
    2. Escapes other special characters
    """
    # For simplicity, we'll escape the most problematic characters
    # that aren't used in formatting
    for char in ".!>+-=|{}":
        text = text.replace(char, f"\\{char}")

    # Escape # only at start of line (not headers we want to preserve)
    lines = text.split("\n")
    result = []
    for line in lines:
        # Convert # headers to bold
        if line.startswith("# "):
            line = f"*{line[2:]}*"
        elif line.startswith("## "):
            line = f"*{line[3:]}*"
        elif line.startswith("### "):
            line = f"*{line[4:]}*"
        result.append(line)

    return "\n".join(result)


def format_for_telegram(response_text: str) -> list[str]:
    """
    Convert Maestro response to Telegram MarkdownV2 format.

    Args:
        response_text: The raw response from Maestro

    Returns:
        List of message strings (split if > 4000 chars)
    """
    if not response_text:
        return [""]

    # Step 1: Convert tables to bullet lists
    text = _convert_tables_to_lists(response_text)

    # Step 2: Convert markdown formatting
    text = _convert_bold(text)
    text = _convert_italic(text)
    text = _convert_code(text)
    text = _convert_code_blocks(text)
    text = _convert_links(text)

    # Step 3: Escape special characters outside formatting
    text = _escape_outside_formatting(text)

    # Step 4: Split into chunks if needed (max 4000 chars for safety margin)
    messages = split_message(text, max_length=4000)

    return messages


def split_message(text: str, max_length: int = 4000) -> list[str]:
    """
    Split a long message into chunks that fit Telegram's limit.

    Attempts to split at paragraph breaks, then sentence breaks,
    then word breaks.
    """
    if len(text) <= max_length:
        return [text]

    messages = []
    remaining = text

    while remaining:
        if len(remaining) <= max_length:
            messages.append(remaining)
            break

        # Find a good split point
        chunk = remaining[:max_length]

        # Try to split at paragraph break
        split_idx = chunk.rfind("\n\n")
        if split_idx == -1 or split_idx < max_length // 2:
            # Try to split at newline
            split_idx = chunk.rfind("\n")
        if split_idx == -1 or split_idx < max_length // 2:
            # Try to split at sentence
            for punct in [". ", "! ", "? "]:
                idx = chunk.rfind(punct)
                if idx > split_idx:
                    split_idx = idx + 1
        if split_idx == -1 or split_idx < max_length // 2:
            # Try to split at word
            split_idx = chunk.rfind(" ")
        if split_idx == -1:
            # Force split
            split_idx = max_length

        messages.append(remaining[:split_idx].strip())
        remaining = remaining[split_idx:].strip()

    return messages


def format_plain_text(response_text: str) -> list[str]:
    """
    Format response as plain text for Telegram (no MarkdownV2).

    Use this as a fallback if MarkdownV2 parsing fails.
    """
    if not response_text:
        return [""]

    # Convert tables to lists
    text = _convert_tables_to_lists(response_text)

    # Strip markdown formatting
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)  # Remove bold
    text = re.sub(r"__([^_]+)__", r"\1", text)  # Remove bold
    text = re.sub(r"\*([^*]+)\*", r"\1", text)  # Remove italic
    text = re.sub(r"_([^_]+)_", r"\1", text)  # Remove italic
    text = re.sub(r"```[^`]*```", "", text)  # Remove code blocks
    text = re.sub(r"`([^`]+)`", r"\1", text)  # Remove inline code

    return split_message(text, max_length=4000)
