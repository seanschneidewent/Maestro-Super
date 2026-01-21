"""
Sheet Analyzer Service - OCR + Semantic Classification for Construction Sheets

Pipeline:
1. Tiled EasyOCR for bbox detection (handles large images)
2. Geometric bbox stitching across tile boundaries
3. Gemini text labeling (handles vertical/rotated text)
4. Quadrant-based semantic classification (region_type, role)
5. Context markdown generation

Based on ~/Downloads/sheet-analyzer/main.py - production-ready implementation.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# Lazy-loaded EasyOCR instance
_ocr_instance = None


def get_ocr_instance():
    """Get or create EasyOCR reader (lazy loading - models are ~1.5GB)."""
    global _ocr_instance
    if _ocr_instance is None:
        import easyocr
        logger.info("Loading EasyOCR models (first time only)...")
        _ocr_instance = easyocr.Reader(['en'], gpu=False)
        logger.info("EasyOCR models loaded")
    return _ocr_instance


# =============================================================================
# Pass 1: Tiled EasyOCR for bbox detection
# =============================================================================


def process_tile_for_bboxes(args: tuple) -> dict:
    """
    Process a single tile with EasyOCR to extract bounding boxes.
    Designed for parallel execution via ThreadPoolExecutor.

    Args:
        args: tuple of (tile_idx, tile_array, tile_bounds, reader)

    Returns:
        dict with tile_idx, bboxes list, and tile_bounds
    """
    tile_idx, tile_array, tile_bounds, reader = args
    x0, y0 = tile_bounds["x0"], tile_bounds["y0"]

    results = reader.readtext(
        tile_array,
        text_threshold=0.3,
        low_text=0.2,
        link_threshold=0.4
    )

    bboxes = []
    for bbox, text, confidence in results:
        xs = [p[0] for p in bbox]
        ys = [p[1] for p in bbox]
        bx0, bx1 = min(xs), max(xs)
        by0, by1 = min(ys), max(ys)

        # Offset coordinates to full image space
        bboxes.append({
            "x0": int(bx0 + x0),
            "y0": int(by0 + y0),
            "x1": int(bx1 + x0),
            "y1": int(by1 + y0),
            "tile_idx": tile_idx,
            "original_text": text,
            "original_confidence": float(confidence)
        })

    return {
        "tile_idx": tile_idx,
        "tile_bounds": tile_bounds,
        "bboxes": bboxes
    }


def y_coordinates_overlap(bbox1: dict, bbox2: dict, tolerance: int = 20) -> bool:
    """Check if two bboxes overlap vertically (for horizontal stitching)."""
    return not (bbox1["y1"] + tolerance < bbox2["y0"] or
                bbox2["y1"] + tolerance < bbox1["y0"])


def x_coordinates_overlap(bbox1: dict, bbox2: dict, tolerance: int = 20) -> bool:
    """Check if two bboxes overlap horizontally (for vertical stitching)."""
    return not (bbox1["x1"] + tolerance < bbox2["x0"] or
                bbox2["x1"] + tolerance < bbox1["x0"])


def stitch_bboxes_across_tiles(tile_results: list, grid: dict) -> list:
    """
    Stitch bboxes that span across tile boundaries.
    Handles all 4 directions: left, right, top, bottom.

    Args:
        tile_results: list of dicts from process_tile_for_bboxes
        grid: dict with cols, rows

    Returns:
        list of merged bboxes with unique IDs
    """
    EDGE_THRESHOLD = 50

    cols, rows = grid["cols"], grid["rows"]
    tiles_by_idx = {r["tile_idx"]: r for r in tile_results}
    merged_set = set()
    all_bboxes = []

    for tile_result in tile_results:
        tile_idx = tile_result["tile_idx"]
        tile_bounds = tile_result["tile_bounds"]
        tile_x0, tile_y0 = tile_bounds["x0"], tile_bounds["y0"]
        tile_x1, tile_y1 = tile_bounds["x1"], tile_bounds["y1"]

        row = tile_idx // cols
        col = tile_idx % cols

        for bbox_idx, bbox in enumerate(tile_result["bboxes"]):
            if (tile_idx, bbox_idx) in merged_set:
                continue

            merged_bbox = bbox.copy()

            # Check RIGHT edge
            if col < cols - 1 and bbox["x1"] >= tile_x1 - EDGE_THRESHOLD:
                right_tile_idx = tile_idx + 1
                if right_tile_idx in tiles_by_idx:
                    right_tile = tiles_by_idx[right_tile_idx]
                    right_tile_x0 = right_tile["tile_bounds"]["x0"]

                    for r_bbox_idx, r_bbox in enumerate(right_tile["bboxes"]):
                        if (right_tile_idx, r_bbox_idx) in merged_set:
                            continue
                        if r_bbox["x0"] <= right_tile_x0 + EDGE_THRESHOLD:
                            if y_coordinates_overlap(bbox, r_bbox):
                                merged_bbox = {
                                    "x0": min(merged_bbox["x0"], r_bbox["x0"]),
                                    "y0": min(merged_bbox["y0"], r_bbox["y0"]),
                                    "x1": max(merged_bbox["x1"], r_bbox["x1"]),
                                    "y1": max(merged_bbox["y1"], r_bbox["y1"]),
                                    "tile_idx": tile_idx,
                                    "merged_from": [tile_idx, right_tile_idx],
                                    "original_text": bbox.get("original_text", ""),
                                    "original_confidence": bbox.get("original_confidence", 0)
                                }
                                merged_set.add((right_tile_idx, r_bbox_idx))
                                break

            # Check BOTTOM edge
            if row < rows - 1 and bbox["y1"] >= tile_y1 - EDGE_THRESHOLD:
                below_tile_idx = tile_idx + cols
                if below_tile_idx in tiles_by_idx:
                    below_tile = tiles_by_idx[below_tile_idx]
                    below_tile_y0 = below_tile["tile_bounds"]["y0"]

                    for b_bbox_idx, b_bbox in enumerate(below_tile["bboxes"]):
                        if (below_tile_idx, b_bbox_idx) in merged_set:
                            continue
                        if b_bbox["y0"] <= below_tile_y0 + EDGE_THRESHOLD:
                            if x_coordinates_overlap(bbox, b_bbox):
                                merged_bbox = {
                                    "x0": min(merged_bbox["x0"], b_bbox["x0"]),
                                    "y0": min(merged_bbox["y0"], b_bbox["y0"]),
                                    "x1": max(merged_bbox["x1"], b_bbox["x1"]),
                                    "y1": max(merged_bbox["y1"], b_bbox["y1"]),
                                    "tile_idx": tile_idx,
                                    "merged_from": merged_bbox.get("merged_from", [tile_idx]) + [below_tile_idx],
                                    "original_text": bbox.get("original_text", ""),
                                    "original_confidence": bbox.get("original_confidence", 0)
                                }
                                merged_set.add((below_tile_idx, b_bbox_idx))
                                break

            all_bboxes.append(merged_bbox)

    # Assign unique IDs
    for idx, bbox in enumerate(all_bboxes):
        bbox["id"] = idx
        bbox["width"] = bbox["x1"] - bbox["x0"]
        bbox["height"] = bbox["y1"] - bbox["y0"]

    return all_bboxes


def crop_all_bboxes(image: Image.Image, bboxes: list, padding: int = 0) -> list:
    """
    Crop image regions for each bbox.

    Args:
        image: PIL Image
        bboxes: list of bbox dicts with x0, y0, x1, y1, id
        padding: pixels to add around each bbox

    Returns:
        list of (bbox_id, PIL Image crop) tuples
    """
    width, height = image.size
    crops = []

    for bbox in bboxes:
        x0 = max(0, bbox["x0"] - padding)
        y0 = max(0, bbox["y0"] - padding)
        x1 = min(width, bbox["x1"] + padding)
        y1 = min(height, bbox["y1"] + padding)

        crop = image.crop((x0, y0, x1, y1))
        crops.append((bbox["id"], crop))

    return crops


# =============================================================================
# Pass 2: Gemini text labeling (handles vertical text)
# =============================================================================


def label_bboxes_with_gemini(
    crops: list,
    bboxes: list,
    api_key: str,
    batch_size: int = 100
) -> dict:
    """
    Use Gemini to read text from all cropped bbox images.
    Rotates vertical crops 90° CCW so text is horizontal.

    Args:
        crops: List of (bbox_id, PIL Image crop) tuples
        bboxes: List of bbox dicts with id, width, height
        api_key: Gemini API key
        batch_size: Max images per Gemini call

    Returns:
        Dict mapping bbox_id -> {"text": str, "confidence": float}
    """
    if not crops:
        return {}

    from google import genai

    bbox_lookup = {b["id"]: b for b in bboxes}

    # Rotate vertical crops
    prepared_crops = []
    for bbox_id, crop in crops:
        bbox = bbox_lookup.get(bbox_id, {})
        w = bbox.get("width", crop.width)
        h = bbox.get("height", crop.height)

        if h > w * 1.5:
            crop = crop.rotate(90, expand=True)

        prepared_crops.append((bbox_id, crop))

    all_results = {}
    total_batches = (len(prepared_crops) + batch_size - 1) // batch_size
    client = genai.Client(api_key=api_key)

    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(prepared_crops))
        batch = prepared_crops[start:end]

        logger.info(f"[OCR] Pass 2: Gemini batch {batch_idx + 1}/{total_batches} ({len(batch)} images)")

        prompt = f"""Read the text in each of the {len(batch)} cropped images from a construction sheet.

For each image, return the exact text you see. These are cropped regions from architectural/engineering drawings.

Common patterns:
- Dimensions: 1'-11", 3'-0", 2'-6"
- Detail callouts: 8/A601, 5/S301
- Material specs: CONC., GYP. BD., STL.
- Labels: EMBEDDED, MEETING ROOM, etc.
- Abbreviations: TYP., SIM., EQ., VIF.

Return ONLY valid JSON (no markdown):
[
  {{"id": 0, "text": "EMBEDDED"}},
  {{"id": 1, "text": "3'-6\\""}},
  ...
]

Return one entry for EACH image using the 0-based index as "id".
If you cannot read the text clearly, return your best guess."""

        contents = [prompt]
        for idx, (bbox_id, crop_img) in enumerate(batch):
            contents.append(f"Image {idx}:")
            contents.append(crop_img)

        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=contents
            )

            response_text = response.text.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            results = json.loads(response_text)

            if isinstance(results, list):
                for r in results:
                    if "id" in r and "text" in r:
                        idx = r["id"]
                        if 0 <= idx < len(batch):
                            bbox_id = batch[idx][0]
                            all_results[bbox_id] = {
                                "text": (r["text"] or "").strip(),
                                "confidence": 0.9
                            }

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Gemini response for batch {batch_idx + 1}: {e}")
            for bbox_id, _ in batch:
                if bbox_id not in all_results:
                    all_results[bbox_id] = {"text": "", "confidence": 0.0}
        except Exception as e:
            logger.warning(f"Gemini API error for batch {batch_idx + 1}: {e}")
            for bbox_id, _ in batch:
                if bbox_id not in all_results:
                    all_results[bbox_id] = {"text": "", "confidence": 0.0}

    # Ensure all bbox IDs have results
    for bbox_id, _ in crops:
        if bbox_id not in all_results:
            all_results[bbox_id] = {"text": "", "confidence": 0.0}

    return all_results


# =============================================================================
# Main OCR function
# =============================================================================


def run_ocr(image: Image.Image, api_key: str) -> dict:
    """
    Run hybrid OCR pipeline:
    - Pass 1: Tiled EasyOCR for bbox detection
    - Stitch bboxes across tile boundaries
    - Pass 2: Gemini for text labeling (handles vertical text)

    Args:
        image: PIL Image object
        api_key: Gemini API key

    Returns:
        dict with words array, tile_bounds, grid info
    """
    reader = get_ocr_instance()
    width, height = image.size

    MAX_TILE_SIZE = 1400

    cols = max(1, (width + MAX_TILE_SIZE - 1) // MAX_TILE_SIZE)
    rows = max(1, (height + MAX_TILE_SIZE - 1) // MAX_TILE_SIZE)

    tile_width = width // cols
    tile_height = height // rows

    tile_bounds = []
    for row in range(rows):
        for col in range(cols):
            x0 = col * tile_width
            y0 = row * tile_height
            x1 = width if col == cols - 1 else (col + 1) * tile_width
            y1 = height if row == rows - 1 else (row + 1) * tile_height
            tile_bounds.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1})

    logger.info(f"[OCR] Pass 1: Processing {len(tile_bounds)} tiles ({cols}x{rows} grid)...")

    # Pass 1: Extract bboxes from tiles
    tile_results = []
    for tile_idx, bounds in enumerate(tile_bounds):
        tile = image.crop((bounds["x0"], bounds["y0"], bounds["x1"], bounds["y1"]))
        tile_array = np.array(tile)
        result = process_tile_for_bboxes((tile_idx, tile_array, bounds, reader))
        tile_results.append(result)

    total_raw_bboxes = sum(len(r["bboxes"]) for r in tile_results)
    logger.info(f"[OCR] Pass 1 complete: {total_raw_bboxes} raw bboxes detected")

    # Stitch bboxes across tile boundaries
    logger.info("[OCR] Stitching bboxes across tile boundaries...")
    grid = {"cols": cols, "rows": rows}
    stitched_bboxes = stitch_bboxes_across_tiles(tile_results, grid)
    logger.info(f"[OCR] Stitching complete: {len(stitched_bboxes)} bboxes after merging")

    # Pass 2: Extract text using Gemini
    logger.info(f"[OCR] Pass 2: Labeling {len(stitched_bboxes)} bboxes with Gemini...")
    crops = crop_all_bboxes(image, stitched_bboxes, padding=0)
    text_results = label_bboxes_with_gemini(crops, stitched_bboxes, api_key)
    logger.info(f"[OCR] Pass 2 complete: text extracted for {len(text_results)} bboxes")

    # Combine bboxes + text into final words
    all_words = []
    for bbox in stitched_bboxes:
        bbox_id = bbox["id"]
        text_data = text_results.get(bbox_id, {"text": "", "confidence": 0.0})

        all_words.append({
            "id": bbox_id,
            "text": text_data["text"],
            "confidence": text_data["confidence"],
            "bbox": {
                "x0": bbox["x0"],
                "y0": bbox["y0"],
                "x1": bbox["x1"],
                "y1": bbox["y1"],
                "width": bbox["width"],
                "height": bbox["height"]
            },
            "original_text": bbox.get("original_text", ""),
            "original_confidence": bbox.get("original_confidence", 0.0)
        })

    return {
        "image_width": width,
        "image_height": height,
        "word_count": len(all_words),
        "words": all_words,
        "tile_bounds": tile_bounds,
        "grid": {"cols": cols, "rows": rows}
    }


# =============================================================================
# Pass 3: Semantic classification (quadrant-based)
# =============================================================================


def get_quadrant_bounds(image_width: int, image_height: int) -> list:
    """Calculate 2x2 quadrant boundaries."""
    cols, rows = 2, 2
    quad_width = image_width // cols
    quad_height = image_height // rows

    quadrants = []
    for row in range(rows):
        for col in range(cols):
            idx = row * cols + col
            x0 = col * quad_width
            y0 = row * quad_height
            x1 = image_width if col == cols - 1 else (col + 1) * quad_width
            y1 = image_height if row == rows - 1 else (row + 1) * quad_height

            quadrants.append({
                "idx": idx,
                "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                "width": x1 - x0, "height": y1 - y0
            })

    return quadrants


def assign_words_to_quadrants(words: list, quadrant_bounds: list) -> dict:
    """Assign each word to the quadrant containing its center point."""
    quadrant_words = {q["idx"]: [] for q in quadrant_bounds}

    for word in words:
        if not word.get("bbox"):
            continue

        cx = (word["bbox"]["x0"] + word["bbox"]["x1"]) / 2
        cy = (word["bbox"]["y0"] + word["bbox"]["y1"]) / 2

        for quad in quadrant_bounds:
            if (quad["x0"] <= cx < quad["x1"] and
                quad["y0"] <= cy < quad["y1"]):
                quadrant_words[quad["idx"]].append(word)
                break

    return quadrant_words


def classify_quadrant_words(
    image: Image.Image,
    quadrant: dict,
    quadrant_words: list,
    api_key: str
) -> dict:
    """
    Classify words in a quadrant by region_type and role.

    Region types: detail, notes, schedule, title_block, unknown
    Roles: detail_title, dimension, material_spec, reference, note_text, etc.
    """
    if not quadrant_words:
        return {"words": [], "quadrant_idx": quadrant["idx"]}

    from google import genai

    try:
        client = genai.Client(api_key=api_key)

        quad_image = image.crop((quadrant["x0"], quadrant["y0"],
                                  quadrant["x1"], quadrant["y1"]))

        word_list = [{"id": w["id"], "text": w.get("text", "")} for w in quadrant_words]

        prompt = f"""You are classifying text from a construction/architectural sheet.

Here are the text spans detected in this section:
{json.dumps(word_list, indent=2)}

For each text span, classify:
- region_type: "detail", "notes", "schedule", "title_block", or "unknown"
- role: What is its semantic role?
  - For detail: detail_title, detail_number, dimension, material_spec, reference, scale, callout, label
  - For notes: note_number, note_text
  - For schedule: schedule_title, column_header, cell_value, row_label
  - For title_block: sheet_number, project_name, engineer_name, date, revision
  - If unsure: unknown

Return ONLY valid JSON array (no markdown):
[
  {{"id": 0, "region_type": "detail", "role": "detail_title"}},
  {{"id": 1, "region_type": "detail", "role": "dimension"}}
]

CRITICAL: Return one entry for EACH input word, with the SAME ID."""

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[prompt, quad_image]
        )

        response_text = response.text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        classifications = json.loads(response_text)

        class_by_id = {}
        if isinstance(classifications, list):
            for c in classifications:
                if "id" in c:
                    class_by_id[c["id"]] = c

        classified_words = []
        for w in quadrant_words:
            word_id = w["id"]
            classification = class_by_id.get(word_id, {})

            classified_words.append({
                "id": word_id,
                "text": w.get("text", ""),
                "confidence": w.get("confidence"),
                "bbox": w.get("bbox"),
                "region_type": classification.get("region_type", "unknown"),
                "role": classification.get("role", "unknown"),
                "quadrant_idx": quadrant["idx"]
            })

        return {"words": classified_words, "quadrant_idx": quadrant["idx"]}

    except Exception as e:
        logger.warning(f"Gemini classification failed for quadrant {quadrant['idx']}: {e}")
        return {
            "words": [{
                "id": w["id"],
                "text": w.get("text", ""),
                "confidence": w.get("confidence"),
                "bbox": w.get("bbox"),
                "region_type": "unknown",
                "role": "unknown",
                "quadrant_idx": quadrant["idx"]
            } for w in quadrant_words],
            "quadrant_idx": quadrant["idx"],
            "error": str(e)
        }


def run_semantic_analysis(image: Image.Image, ocr_result: dict, api_key: str) -> dict:
    """
    Run semantic classification on OCR results (4 Gemini calls for 2x2 quadrants).

    Args:
        image: Full PIL Image
        ocr_result: Output from run_ocr()
        api_key: Gemini API key

    Returns:
        Semantic index with classified words
    """
    width = ocr_result["image_width"]
    height = ocr_result["image_height"]
    words = ocr_result.get("words", [])

    if not words:
        return {
            "image_width": width,
            "image_height": height,
            "word_count": 0,
            "words": [],
            "indices": {"by_region_type": {}, "by_role": {}}
        }

    quadrant_bounds = get_quadrant_bounds(width, height)
    quadrant_words = assign_words_to_quadrants(words, quadrant_bounds)

    # Classify words in each quadrant (4 Gemini calls)
    all_classified_words = []
    for quad in quadrant_bounds:
        qwords = quadrant_words.get(quad["idx"], [])
        result = classify_quadrant_words(image, quad, qwords, api_key)
        all_classified_words.extend(result.get("words", []))

    # Build lookup indices
    by_region_type = {}
    by_role = {}

    for word in all_classified_words:
        word_id = word.get("id")
        if word_id is None:
            continue

        region_type = word.get("region_type", "unknown")
        if region_type not in by_region_type:
            by_region_type[region_type] = []
        by_region_type[region_type].append(word_id)

        role = word.get("role", "unknown")
        if role not in by_role:
            by_role[role] = []
        by_role[role].append(word_id)

    return {
        "image_width": width,
        "image_height": height,
        "word_count": len(all_classified_words),
        "words": all_classified_words,
        "indices": {
            "by_region_type": by_region_type,
            "by_role": by_role
        },
        "quadrant_bounds": quadrant_bounds
    }


# =============================================================================
# Pass 4: Context markdown generation
# =============================================================================


def generate_context_markdown(image: Image.Image, semantic_index: dict, api_key: str) -> str:
    """
    Generate markdown context summary of the sheet.

    Args:
        image: Full PIL Image
        semantic_index: Output from run_semantic_analysis()
        api_key: Gemini API key

    Returns:
        Markdown string with sheet summary
    """
    from google import genai

    client = genai.Client(api_key=api_key)

    words = semantic_index.get("words", [])
    indices = semantic_index.get("indices", {})
    by_role = indices.get("by_role", {})
    by_region_type = indices.get("by_region_type", {})

    word_lookup = {w["id"]: w for w in words}

    # Extract detail titles
    detail_title_ids = by_role.get("detail_title", [])
    detail_titles = [word_lookup[wid].get("text", "") for wid in detail_title_ids if wid in word_lookup]

    # Extract dimensions
    dimension_ids = by_role.get("dimension", [])
    dimensions = [word_lookup[wid].get("text", "") for wid in dimension_ids if wid in word_lookup]

    # Extract notes
    notes_ids = by_region_type.get("notes", [])
    notes_text = [word_lookup[wid].get("text", "") for wid in notes_ids if wid in word_lookup]

    # Extract materials
    material_ids = by_role.get("material_spec", [])
    materials = [word_lookup[wid].get("text", "") for wid in material_ids if wid in word_lookup]

    detail_titles_str = ", ".join(detail_titles[:20]) if detail_titles else "None identified"
    dimensions_str = ", ".join(dimensions[:30]) if dimensions else "None identified"
    notes_str = " | ".join(notes_text[:50]) if notes_text else "None identified"
    materials_str = ", ".join(materials[:20]) if materials else "None identified"

    prompt = f"""Analyze this construction sheet and create a hierarchical markdown summary.

You have access to OCR data that has been semantically classified:

**Identified Details:** {detail_titles_str}
**Identified Dimensions:** {dimensions_str}
**Identified Materials/Specs:** {materials_str}
**Identified Notes (partial):** {notes_str[:500]}

Using both the IMAGE and this structured data, create a summary with this format:

## Sheet Overview
- Sheet number and title
- Scale(s) used
- Referenced sheets (if any)

## Details
For EACH detail visible on the sheet, create a subsection:

### [DETAIL NAME] ([detail number if visible])
- **Shows:** What this detail visually depicts
- **Materials:** Materials shown IN THIS DETAIL
- **Dimensions:** Key dimensions called out IN THIS DETAIL
- **Notes:** Any notes specific to this detail

## General Notes
Notes that apply to the whole sheet.

---
Focus on accuracy - use the OCR data to verify what you see in the image."""

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[prompt, image]
    )
    return response.text


# =============================================================================
# Full pipeline orchestration
# =============================================================================


async def process_page(
    image: Image.Image,
    api_key: str,
    page_name: str = "Unknown"
) -> dict:
    """
    Run the full sheet-analyzer pipeline on a single page.

    Pipeline:
    1. run_ocr() - Tiled EasyOCR + Gemini text labeling
    2. run_semantic_analysis() - Quadrant classification
    3. generate_context_markdown() - Sheet summary

    Args:
        image: PIL Image of the page
        api_key: Gemini API key
        page_name: Page name for logging

    Returns:
        dict with semantic_index, context_markdown, and details
    """
    import asyncio

    logger.info(f"[{page_name}] Starting sheet-analyzer pipeline...")

    # Pass 1-2: OCR
    logger.info(f"[{page_name}] Running OCR...")
    ocr_result = await asyncio.to_thread(run_ocr, image, api_key)
    logger.info(f"[{page_name}] OCR complete: {ocr_result['word_count']} words")

    # Pass 3: Semantic classification
    logger.info(f"[{page_name}] Running semantic analysis...")
    semantic_index = await asyncio.to_thread(run_semantic_analysis, image, ocr_result, api_key)
    logger.info(f"[{page_name}] Semantic analysis complete")

    # Pass 4: Context markdown
    logger.info(f"[{page_name}] Generating context markdown...")
    context_markdown = await asyncio.to_thread(generate_context_markdown, image, semantic_index, api_key)
    logger.info(f"[{page_name}] Context markdown complete")

    return {
        "semantic_index": semantic_index,
        "context_markdown": context_markdown
    }
