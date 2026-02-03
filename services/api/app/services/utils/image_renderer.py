"""
Image rendering utilities for Maestro.

Renders sheet images with bbox highlights for Telegram and other mobile channels.
"""

import hashlib
import io
import logging
from typing import Any

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Constants
MOBILE_MAX_WIDTH = 2048
TARGET_JPEG_QUALITY = 85
HIGHLIGHT_FILL = (255, 230, 0, 100)  # Semi-transparent yellow
HIGHLIGHT_BORDER = (255, 200, 0, 255)  # Solid yellow border
BORDER_WIDTH = 4
LABEL_BG = (0, 0, 0, 200)
LABEL_TEXT = (255, 255, 255, 255)


def render_with_highlights(
    image_bytes: bytes,
    bboxes: list[dict[str, float]],
    labels: list[str] | None = None,
    max_width: int = MOBILE_MAX_WIDTH,
) -> bytes:
    """
    Render an image with highlighted bounding boxes.
    
    Args:
        image_bytes: Source image as bytes
        bboxes: List of bbox dicts with x0, y0, x1, y1 (normalized 0-1)
        labels: Optional labels for each bbox
        max_width: Maximum width for output image
    
    Returns:
        JPEG bytes with highlights applied
    """
    image = Image.open(io.BytesIO(image_bytes))
    
    # Resize if needed for mobile
    if image.width > max_width:
        ratio = max_width / image.width
        new_height = int(image.height * ratio)
        image = image.resize((max_width, new_height), Image.Resampling.LANCZOS)
    
    # Convert to RGBA for transparency compositing
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    
    # Create overlay layer
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    width, height = image.size
    
    # Draw each bbox highlight
    for i, bbox in enumerate(bboxes):
        x0 = int(bbox.get("x0", 0) * width)
        y0 = int(bbox.get("y0", 0) * height)
        x1 = int(bbox.get("x1", 0) * width)
        y1 = int(bbox.get("y1", 0) * height)
        
        # Ensure valid coordinates
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        
        # Draw semi-transparent fill
        draw.rectangle([x0, y0, x1, y1], fill=HIGHLIGHT_FILL)
        
        # Draw border
        draw.rectangle([x0, y0, x1, y1], outline=HIGHLIGHT_BORDER, width=BORDER_WIDTH)
        
        # Add label if provided
        if labels and i < len(labels) and labels[i]:
            _draw_label(draw, labels[i], x0, y0)
    
    # Composite overlay onto base
    result = Image.alpha_composite(image, overlay)
    
    # Convert to RGB for JPEG
    result = result.convert("RGB")
    
    # Encode as JPEG
    output = io.BytesIO()
    result.save(output, format="JPEG", quality=TARGET_JPEG_QUALITY, optimize=True)
    return output.getvalue()


def render_comparison(
    image1_bytes: bytes,
    image2_bytes: bytes,
    bbox1: dict[str, float] | None = None,
    bbox2: dict[str, float] | None = None,
    label1: str | None = None,
    label2: str | None = None,
    orientation: str = "horizontal",
    max_height: int = 1024,
) -> bytes:
    """
    Render two images side by side for comparison.
    
    Useful for showing conflicts or cross-references.
    """
    img1 = Image.open(io.BytesIO(image1_bytes))
    img2 = Image.open(io.BytesIO(image2_bytes))
    
    # Resize to same height
    target_height = min(img1.height, img2.height, max_height)
    
    ratio1 = target_height / img1.height
    img1 = img1.resize(
        (int(img1.width * ratio1), target_height),
        Image.Resampling.LANCZOS
    )
    
    ratio2 = target_height / img2.height
    img2 = img2.resize(
        (int(img2.width * ratio2), target_height),
        Image.Resampling.LANCZOS
    )
    
    # Add highlights if provided
    if bbox1:
        img1_bytes = render_with_highlights(
            _image_to_bytes(img1),
            [bbox1],
            [label1] if label1 else None,
            max_width=img1.width,
        )
        img1 = Image.open(io.BytesIO(img1_bytes))
    
    if bbox2:
        img2_bytes = render_with_highlights(
            _image_to_bytes(img2),
            [bbox2],
            [label2] if label2 else None,
            max_width=img2.width,
        )
        img2 = Image.open(io.BytesIO(img2_bytes))
    
    # Ensure RGB
    img1 = img1.convert("RGB")
    img2 = img2.convert("RGB")
    
    # Combine based on orientation
    gap = 10
    bg_color = (40, 40, 40)
    
    if orientation == "horizontal":
        combined_width = img1.width + img2.width + gap
        combined = Image.new("RGB", (combined_width, target_height), bg_color)
        combined.paste(img1, (0, 0))
        combined.paste(img2, (img1.width + gap, 0))
    else:
        combined_height = img1.height + img2.height + gap
        max_width = max(img1.width, img2.width)
        combined = Image.new("RGB", (max_width, combined_height), bg_color)
        combined.paste(img1, (0, 0))
        combined.paste(img2, (0, img1.height + gap))
    
    # Encode
    output = io.BytesIO()
    combined.save(output, format="JPEG", quality=85)
    return output.getvalue()


def render_detail_crop(
    image_bytes: bytes,
    bbox: dict[str, float],
    zoom: float = 2.0,
    context_padding: float = 0.15,
    max_size: int = 2048,
) -> bytes:
    """
    Render a cropped and zoomed view of a specific area.
    
    Great for showing details on mobile.
    """
    image = Image.open(io.BytesIO(image_bytes))
    width, height = image.size
    
    # Calculate crop area with padding
    bbox_width = bbox.get("x1", 0) - bbox.get("x0", 0)
    bbox_height = bbox.get("y1", 0) - bbox.get("y0", 0)
    
    pad_x = bbox_width * context_padding
    pad_y = bbox_height * context_padding
    
    x0 = max(0, int((bbox.get("x0", 0) - pad_x) * width))
    y0 = max(0, int((bbox.get("y0", 0) - pad_y) * height))
    x1 = min(width, int((bbox.get("x1", 0) + pad_x) * width))
    y1 = min(height, int((bbox.get("y1", 0) + pad_y) * height))
    
    # Crop
    cropped = image.crop((x0, y0, x1, y1))
    
    # Calculate zoom dimensions
    new_width = int(cropped.width * zoom)
    new_height = int(cropped.height * zoom)
    
    # Cap at max size
    if new_width > max_size or new_height > max_size:
        scale = min(max_size / new_width, max_size / new_height)
        new_width = int(new_width * scale)
        new_height = int(new_height * scale)
    
    zoomed = cropped.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    # Add highlight border around the center (the actual bbox area)
    zoomed = zoomed.convert("RGBA")
    overlay = Image.new("RGBA", zoomed.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Calculate center area (accounting for padding)
    total_pad = 2 * context_padding
    center_ratio = 1 / (1 + total_pad)
    margin_ratio = context_padding / (1 + total_pad)
    
    cx0 = int(margin_ratio * zoomed.width)
    cy0 = int(margin_ratio * zoomed.height)
    cx1 = int((1 - margin_ratio) * zoomed.width)
    cy1 = int((1 - margin_ratio) * zoomed.height)
    
    draw.rectangle([cx0, cy0, cx1, cy1], outline=HIGHLIGHT_BORDER, width=3)
    
    result = Image.alpha_composite(zoomed, overlay).convert("RGB")
    
    output = io.BytesIO()
    result.save(output, format="JPEG", quality=90)
    return output.getvalue()


def _draw_label(draw: ImageDraw.Draw, label: str, x: int, y: int):
    """Draw a label above a highlighted area."""
    try:
        # Try to load a good font
        font = ImageFont.truetype("arial.ttf", 20)
    except:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        except:
            font = ImageFont.load_default()
    
    # Get text dimensions
    bbox = draw.textbbox((0, 0), label, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    # Position above the highlight
    text_x = x
    text_y = max(0, y - text_height - 8)
    
    # Draw background
    padding = 4
    draw.rectangle(
        [text_x - padding, text_y - padding, text_x + text_width + padding, text_y + text_height + padding],
        fill=LABEL_BG
    )
    
    # Draw text
    draw.text((text_x, text_y), label, fill=LABEL_TEXT, font=font)


def _image_to_bytes(image: Image.Image, format: str = "PNG") -> bytes:
    """Convert PIL Image to bytes."""
    output = io.BytesIO()
    image.save(output, format=format)
    return output.getvalue()


def build_cache_key(page_id: str, bboxes: list[dict[str, float]]) -> str:
    """Build a cache key for a rendered image."""
    bbox_str = str(sorted([tuple(sorted(b.items())) for b in bboxes]))
    hash_part = hashlib.md5(bbox_str.encode()).hexdigest()[:8]
    return f"render:{page_id}:{hash_part}"
