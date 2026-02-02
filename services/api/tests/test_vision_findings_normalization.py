"""Tests for deep-query finding bbox normalization."""

from __future__ import annotations

import sys
from types import SimpleNamespace

# Optional dependency used by other provider modules during package import.
sys.modules.setdefault("voyageai", SimpleNamespace(Client=lambda *args, **kwargs: None))
sys.modules.setdefault("supabase", SimpleNamespace(create_client=lambda *args, **kwargs: None))
sys.modules.setdefault("pdf2image", SimpleNamespace(convert_from_bytes=lambda *args, **kwargs: []))

from app.services.providers.gemini import normalize_vision_findings


def test_normalize_vision_findings_converts_0_to_1000_bbox_to_unit_space() -> None:
    pages = [
        {
            "page_id": "page-1",
            "page_name": "A2.3",
            "semantic_index": {
                "image_width": 2400,
                "image_height": 1600,
                "words": [],
            },
        }
    ]
    findings = [
        {
            "category": "detail",
            "content": "Top clearance note",
            "page_id": "page-1",
            "bbox": [450, 300, 600, 450],
        }
    ]

    normalized = normalize_vision_findings(findings, pages)
    assert len(normalized) == 1
    assert normalized[0]["bbox"] == [0.45, 0.3, 0.6, 0.45]


def test_normalize_vision_findings_resolves_page_name_and_semantic_refs() -> None:
    pages = [
        {
            "page_id": "page-1",
            "page_name": "A2.3",
            "semantic_index": {
                "image_width": 2000,
                "image_height": 1200,
                "words": [
                    {
                        "id": 42,
                        "bbox": {"x0": 0.2, "y0": 0.1, "x1": 0.3, "y1": 0.2},
                    }
                ],
            },
        }
    ]
    findings = [
        {
            "category": "detail",
            "content": "Mounting bracket callout",
            "page_id": "A2.3",
            "semantic_refs": [42],
        }
    ]

    normalized = normalize_vision_findings(findings, pages)
    assert len(normalized) == 1
    assert normalized[0]["page_id"] == "page-1"
    assert normalized[0]["bbox"] == [0.2, 0.1, 0.3, 0.2]


def test_normalize_vision_findings_supports_xywh_bbox_dict() -> None:
    pages = [
        {
            "page_id": "page-1",
            "page_name": "A2.3",
            "semantic_index": {
                "image_width": 3000,
                "image_height": 2000,
                "words": [],
            },
        }
    ]
    findings = [
        {
            "category": "dimensions",
            "content": "Clear width",
            "page_id": "page-1",
            "bbox": {"x": 100, "y": 200, "width": 300, "height": 400},
        }
    ]

    normalized = normalize_vision_findings(findings, pages)
    assert len(normalized) == 1
    assert normalized[0]["bbox"] == [0.1, 0.2, 0.4, 0.6]
