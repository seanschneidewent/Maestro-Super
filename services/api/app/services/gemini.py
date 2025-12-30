"""
Gemini AI service for context extraction.

TODO: Implement in AI integration phase.
"""


async def analyze_pointer(image_base64: str, context: str) -> dict:
    """
    Analyze a context pointer image using Gemini.

    Args:
        image_base64: Base64 encoded image of the pointer region
        context: Surrounding context text for better analysis

    Returns:
        Dictionary with AI analysis results:
        - technical_description: str
        - trade_category: str
        - elements: list[dict]
        - measurements: list[dict]
        - recommendations: str
        - issues: list[dict]
    """
    raise NotImplementedError("Gemini integration not yet implemented")


async def analyze_page_pass1(image_base64: str, page_number: int) -> dict:
    """
    Pass 1: Analyze a page for sheet metadata and context.

    Args:
        image_base64: Base64 encoded page image
        page_number: Page number in document

    Returns:
        Dictionary with pass 1 analysis results
    """
    raise NotImplementedError("Gemini integration not yet implemented")


async def analyze_page_pass2(
    image_base64: str,
    pass1_output: dict,
    cross_references: list[dict],
) -> dict:
    """
    Pass 2: Enrich page context with cross-references.

    Args:
        image_base64: Base64 encoded page image
        pass1_output: Output from pass 1 analysis
        cross_references: References to/from other pages

    Returns:
        Dictionary with pass 2 analysis results
    """
    raise NotImplementedError("Gemini integration not yet implemented")


async def analyze_discipline_pass3(
    discipline_code: str,
    page_contexts: list[dict],
) -> dict:
    """
    Pass 3: Roll up discipline context from all pages.

    Args:
        discipline_code: Discipline code (A, S, M, E, P, etc.)
        page_contexts: List of page context summaries

    Returns:
        Dictionary with discipline-level analysis
    """
    raise NotImplementedError("Gemini integration not yet implemented")
