# Maestro Super: Complete System Architecture

This document contains the distilled knowledge from the prototype implementation. Use it as the authoritative reference for how this system works.

---

## Part I: The Normalized Coordinate System

**The Core Principle:** Every point, every bounding box, every annotation exists in a 0-1 coordinate space.

```typescript
// User clicks at pixel (342, 567) on an 800x1131 canvas
const xNorm = (pixelX - canvasLeft) / canvasWidth;  // → 0.4275
const yNorm = (pixelY - canvasTop) / canvasHeight;  // → 0.5013
```

This normalization happens the instant a pointer event fires. From that moment forward, the coordinate is:
- Zoom-agnostic
- Container-agnostic  
- Resolution-agnostic

The same `(0.4275, 0.5013)` renders correctly at 50% zoom or 400% zoom, in a 400px panel or 2000px panel.

**Rendering Back to Pixels:**
```typescript
const x = pointer.bounds.xNorm * canvas.width;
const y = pointer.bounds.yNorm * canvas.height;
const w = pointer.bounds.wNorm * canvas.width;
const h = pointer.bounds.hNorm * canvas.height;
```

**Why This Matters:** The normalized system is the lingua franca between:
- PdfViewer draw events
- Backend storage
- 150 DPI screenshot capture
- Canvas rendering at any zoom
- Navigation zoom-to-bounds

---

## Part II: Context Pointer Data Structure

A context pointer is a user-drawn box on a PDF page with AI-enriched metadata.

```typescript
interface ContextPointer {
  id: string;                      // UUID
  fileId: string;                  // FK → ProjectFile
  pageContextId?: string;          // FK → PageContext
  pageNumber: number;

  // Normalized bounds (0-1)
  bounds: {
    xNorm: number;  // Top-left X
    yNorm: number;  // Top-left Y
    wNorm: number;  // Width
    hNorm: number;  // Height
  };

  // Visual style
  style: {
    color: string;        // "#ff0000"
    strokeWidth: number;  // 2
  };

  // Content
  title: string;
  description: string;
  snapshotDataUrl: string;  // Base64 PNG (150 DPI crop)

  // AI Analysis (populated by Gemini)
  aiTechnicalDescription?: string;
  aiTradeCategory?: string;        // "ELEC", "MECH", "PLMB", etc.
  aiElements?: Array<{name: string; type: string; details: string}>;
  aiRecommendations?: string;
  aiMeasurements?: Array<{value: string; unit: string; context: string}>;
  aiIssues?: Array<{severity: string; description: string}>;

  // Extracted text from region (hybrid OCR)
  textContent?: {
    textElements: Array<{id: string; text: string}>;
  };

  // Lifecycle
  status: 'generating' | 'complete' | 'error';
  committedAt?: Date;  // null = draft, timestamp = published
  createdAt: Date;
}
```

---

## Part III: The Three-Pass AI Processing Pipeline

Construction documents form a web of cross-references. A detail on sheet A-401 references section AS2.1, which references specs on G-001. The three-pass system reconstructs these relationships.

### Pass 1: Page Analysis (Parallel)

**Purpose:** Analyze each page independently, identify outbound references.

**Input:** All context pointers on a page with their text content.

**Output:**
```json
{
  "discipline": "E",
  "sheet_number": "E-2.1",
  "summary": "Electrical power distribution plan showing branch circuits, panel schedules, and equipment connections for office zones A-C.",
  "pointers": [
    {
      "pointer_id": "ptr_abc123",
      "summary": "Panel P-101 schedule with 20-amp branch circuits.",
      "outbound_refs": [
        {
          "ref": "E-3.2",
          "type": "sheet",
          "source_element_id": "native_42",
          "source_text": "SEE SHEET E-3.2 FOR FEEDER SIZING"
        }
      ]
    }
  ]
}
```

**State Transition:** `unprocessed` → `pass1_processing` → `pass1_complete`

### Inbound Reference Computation

After all Pass 1 completes, invert the relationship graph:

```
For each page's outbound_refs:
  - Find target page by normalized sheet number
  - Add inbound_entry to target's inbound_references list
```

Now page E-3.2 knows that E-2.1 references it.

### Pass 2: Cross-Reference Context (Sequential)

**Purpose:** Enrich outbound refs with context from target pages.

**Input:** Pass 1 output + summaries of all other pages.

**Output:**
```json
{
  "outbound_refs_context": [
    {
      "ref": "E-3.2",
      "context": "Feeder sizing table showing conductor sizes, conduit fill calculations, and voltage drop analysis."
    }
  ]
}
```

After Pass 2, propagate context to target page's inbound references.

**State Transition:** `pass1_complete` → `pass2_processing` → `pass2_complete`

### Pass 3: Discipline Rollup (Sequential)

**Purpose:** Aggregate pages into discipline-level summaries.

**Trigger:** All pages in a discipline reach `pass2_complete`.

**Output:**
```json
{
  "context": "Electrical discipline covers power distribution from main switchgear through branch panelboards. Includes receptacle schedules, lighting controls, and fire alarm integration.",
  "key_contents": [
    {"item": "Panel Schedule P-101", "type": "schedule", "sheet": "E-2.1"},
    {"item": "Feeder Sizing Table", "type": "spec", "sheet": "E-3.2"}
  ],
  "connections": [
    {"discipline": "M", "relationship": "Coordinates cable tray with HVAC ductwork"},
    {"discipline": "FP", "relationship": "Fire alarm devices powered from dedicated circuits"}
  ]
}
```

**State Transition:** `waiting` → `ready` → `processing` → `complete`

---

## Part IV: Page Context Data Structure

```typescript
interface PageContext {
  id: string;
  fileId: string;
  pageNumber: number;

  // Basic metadata
  pageTitle?: string;
  sheetNumber?: string;           // "M3.2"
  disciplineCode?: string;        // A, S, M, E, P, FP, C, L, G

  // Pass 1 output
  contextDescription?: string;    // Page summary
  pass1Output?: {
    discipline: string;
    sheet_number: string;
    summary: string;
    pointers: Array<{
      pointer_id: string;
      summary: string;
      outbound_refs: Array<{
        ref: string;
        type: string;
        source_element_id?: string;
        source_text?: string;
      }>;
    }>;
  };

  // Pass 2 output
  pass2Output?: {
    outbound_refs_context: Array<{
      ref: string;
      context: string;
    }>;
  };

  // Computed after Pass 1
  inboundReferences?: Array<{
    source_sheet: string;
    source_page_id: string;
    from_pointer: string;
    type: string;
    original_ref: string;
    context?: string;  // Filled after Pass 2
  }>;

  // Processing state machine
  processingStatus: 'unprocessed' | 'pass1_processing' | 'pass1_complete' | 'pass2_processing' | 'pass2_complete';
  retryCount: number;
}
```

---

## Part V: Discipline Context Data Structure

```typescript
interface DisciplineContext {
  id: string;
  projectId: string;
  code: string;        // A, S, M, E, P, FP, C, L, G
  name: string;        // Architectural, Structural, etc.

  // Pass 3 output
  contextDescription?: string;
  keyContents?: Array<{
    item: string;
    type: string;
    sheet: string;
  }>;
  connections?: Array<{
    discipline: string;
    relationship: string;
  }>;

  processingStatus: 'waiting' | 'ready' | 'processing' | 'complete';
}
```

**Discipline Codes:**
- A = Architectural
- S = Structural
- M = Mechanical
- E = Electrical
- P = Plumbing
- FP = Fire Protection
- C = Civil
- L = Landscape
- G = General

---

## Part VI: Hybrid Text Extraction

Construction PDFs contain two types of text:
1. **Native text:** Vector text embedded in PDF (extractable via PyMuPDF)
2. **Raster text:** Text rendered into images (requires OCR)

### IoU-Based Deduplication

```python
def merge_text_spans(pymupdf_spans, ocr_spans):
    """
    Include all PyMuPDF spans (higher precision).
    Add OCR spans only if IoU < 0.5 with all PyMuPDF spans.
    """
    merged = list(pymupdf_spans)
    
    for ocr_span in ocr_spans:
        is_duplicate = any(
            bbox_iou(ocr_span["bbox"], native["bbox"]) >= 0.5
            for native in pymupdf_spans
        )
        if not is_duplicate:
            merged.append(ocr_span)
    
    return merged
```

**IoU Calculation:**
```python
def bbox_iou(bbox1, bbox2):
    x1 = max(bbox1[0], bbox2[0])
    y1 = max(bbox1[1], bbox2[1])
    x2 = min(bbox1[2], bbox2[2])
    y2 = min(bbox1[3], bbox2[3])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    intersection = (x2 - x1) * (y2 - y1)
    area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
    area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
    union = area1 + area2 - intersection

    return intersection / union
```

---

## Part VII: 150 DPI Screenshot Capture

Context pointers store a high-quality crop of the highlighted region.

```typescript
async function capturePageSnapshot(
  pageNumber: number,
  xNorm: number,
  yNorm: number,
  wNorm: number,
  hNorm: number
): Promise<string> {
  // 150 DPI = 2.08x scale (PDF uses 72 points per inch)
  const DPI_SCALE = 150 / 72;

  // Render full page at high resolution
  const viewport = page.getViewport({ scale: DPI_SCALE });
  const fullCanvas = document.createElement('canvas');
  fullCanvas.width = viewport.width;   // ~1700px for letter
  fullCanvas.height = viewport.height; // ~2200px
  await page.render({ canvasContext: fullCtx, viewport }).promise;

  // Extract region using normalized coordinates
  const x = Math.floor(xNorm * fullCanvas.width);
  const y = Math.floor(yNorm * fullCanvas.height);
  const w = Math.floor(wNorm * fullCanvas.width);
  const h = Math.floor(hNorm * fullCanvas.height);

  // Crop and export as PNG
  tempCtx.drawImage(fullCanvas, x, y, w, h, 0, 0, w, h);
  return tempCanvas.toDataURL('image/png');
}
```

---

## Part VIII: Navigation & Zoom-to-Bounds

When navigating to a context pointer:

```typescript
function navigateToPointer(pageNumber: number, bounds: Bounds) {
  // 1. Calculate zoom to fit bounds with 20% padding
  const paddingFactor = 1.4;
  const zoomX = viewportWidth / (boundsWidth * paddingFactor);
  const zoomY = viewportHeight / (boundsHeight * paddingFactor);
  const newScale = Math.min(Math.max(zoomX, zoomY, 1), 4);  // Clamp 1x-4x

  setScale(newScale);

  // 2. After scale updates, scroll to center bounds in viewport
  requestAnimationFrame(() => {
    const centerX = (bounds.xNorm + bounds.wNorm / 2) * pageWidth;
    const centerY = (bounds.yNorm + bounds.hNorm / 2) * pageHeight;

    scrollContainer.scrollTo({
      left: pageOffsetLeft + centerX - viewportWidth / 2,
      top: pageOffsetTop + centerY - viewportHeight / 2,
      behavior: 'smooth'
    });
  });
}
```

**Pointer Highlighting:**
```typescript
if (pointer.id === highlightedPointerId) {
  // Highlighted: cyan fill + thick border
  ctx.fillStyle = 'rgba(34, 211, 238, 0.15)';
  ctx.fillRect(x, y, w, h);
  ctx.strokeStyle = '#22d3ee';
  ctx.lineWidth = strokeWidth + 2;
} else {
  // Normal: gradient stroke only
  const gradient = ctx.createLinearGradient(x, y, x + w, y + h);
  gradient.addColorStop(0, '#3b82f6');
  gradient.addColorStop(1, '#06b6d4');
  ctx.strokeStyle = gradient;
}
```

---

## Part IX: Commit Workflow

Pointers exist in two states:
- **Draft:** `committedAt = null`
- **Committed:** `committedAt = timestamp`

**Commit Flow:**
1. Preview: Show all pointers with AI analysis
2. Commit: Set `committedAt = now()` on all pointers with AI
3. Query interface reads only committed pointers

**Uncommit (for revisions):**
- Clear `committedAt` → returns to draft state

---

## Part X: Database Schema (Simplified)

```sql
-- Core entities
projects (id, name, status, created_at)
project_files (id, project_id, name, path, file_type, parent_id, is_folder)

-- Context extraction
context_pointers (id, file_id, page_context_id, page_number, bounds_*, style_*, title, description, snapshot_data_url, ai_*, text_content, status, committed_at)
page_contexts (id, file_id, page_number, sheet_number, discipline_code, pass1_output, pass2_output, inbound_references, processing_status, retry_count)
discipline_contexts (id, project_id, code, name, context_description, key_contents, connections, processing_status)
sheet_contexts (id, file_id, added_to_context, generation_status)

-- Auth & queries (Supabase)
users (id, email, role)
user_projects (user_id, project_id)
queries (id, user_id, project_id, text, created_at)
query_results (id, query_id, pointer_id, relevance_score)
```

---

## Part XI: State Machines

### PageContext Processing
```
unprocessed
    ↓ [trigger]
pass1_processing
    ↓ [success] or → unprocessed [error, retry++]
pass1_complete
    ↓ [all pages done, inbound computed]
pass2_processing
    ↓ [success] or → pass1_complete [error, retry++]
pass2_complete
```

### DisciplineContext Processing
```
waiting
    ↓ [all discipline pages → pass2_complete]
ready
    ↓ [trigger Pass 3]
processing
    ↓ [success] or → error
complete
```

### Orphan Detection
After Pass 2, sweep for stuck pages:
- If `retry_count < 3`: reset to `unprocessed`, increment retry
- If `retry_count >= 3`: mark permanently failed

---

## Part XII: Reference Normalization

Sheet references come in many formats. Normalize for matching:

```python
def normalize_sheet_ref(ref: str) -> str:
    """
    "A-101" → "A101"
    "A.101" → "A101"  
    "AS2.1" → "AS21"
    "3/A-501" → "A501"  (extract from detail callout)
    """
```

---

## Part XIII: Key Algorithms Summary

1. **Coordinate Normalization:** `norm = (pixel - offset) / dimension`
2. **IoU Deduplication:** Threshold 0.5 for hybrid text extraction
3. **150 DPI Capture:** `scale = 150 / 72 ≈ 2.08`
4. **Zoom-to-Bounds:** `zoom = viewport / (bounds * 1.4)`, clamped 1x-4x
5. **Reference Inversion:** outbound refs → inbound refs after Pass 1
6. **Orphan Recovery:** retry with exponential backoff, max 3 attempts
