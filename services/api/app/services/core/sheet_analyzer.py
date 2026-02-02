"""
DEPRECATED: Legacy OCR sheet analyzer pipeline.

Brain Mode now uses Agentic Vision via:
  - app.services.core.brain_mode_processor.process_page_brain_mode()
  - app.services.providers.gemini.analyze_sheet_brain_mode()

This module is kept only for backwards compatibility and rollback reference.
It will be removed in a future release.
"""

from __future__ import annotations

import warnings

DEPRECATION_MESSAGE = (
    "app.services.core.sheet_analyzer is deprecated. "
    "Use app.services.core.brain_mode_processor instead."
)

warnings.warn(DEPRECATION_MESSAGE, DeprecationWarning, stacklevel=2)
