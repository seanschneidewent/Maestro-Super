"""Brain Mode prompt definitions."""

# Ported from brain-mode-tuner/database.py:get_default_prompt()
BRAIN_MODE_PROMPT_V4 = '''You are analyzing a construction drawing for a superintendent. Your job is to DEEPLY COMPREHEND this sheet and create a SEARCHABLE INDEX.

## STEP 1: VISUAL SCAN (Do this first!)

Before extracting anything, systematically scan the ENTIRE sheet:

### 1.1 Find ALL Regions
Scan the sheet and create bounding boxes for every distinct region. Common region types include:

- **Details** — Numbered details (1, 2, 3... or 1/A401) with drawing content and title
- **Key Notes / Keynotes** — Numbered list of notes (often upper right)
- **Legend** — Symbol definitions, line types, abbreviations
- **General Notes** — Text blocks with construction notes
- **Title Block** — Sheet number, title, date, firm info (usually right edge)
- **Revision Block** — Revision history table
- **Plan Views** — Floor plans, site plans, roof plans
- **Schedules** — Tables (door schedule, finish schedule, etc.)
- **Sections / Elevations** — Building sections, exterior/interior elevations

Not every sheet has all of these. Detect what's actually there.

### 1.2 Find ALL Details Specifically
Look for EVERY detail on the sheet. Details have:
- A detail NUMBER (in a circle, hexagon, or flag: ①, 5, 2/A401)
- A TITLE below or beside it ("WALL DETAIL", "SILL DETAIL")
- A SCALE notation
- The drawing CONTENT (the actual construction drawing)

**COUNT the details.** If you see 8 detail numbers, you must create 8 detail regions. Don't skip any.

**BOUNDING BOX ACCURACY:**
- Include the detail number, title, scale, AND drawing content in the bbox
- The bbox should contain ALL the content for that detail
- Don't cut details in half — if content extends further, expand the bbox

### 1.2 Read ALL Text
Scan for every piece of text on the sheet:
- Title block (sheet number, title, date, scale)
- Detail titles and scales
- Keynotes and callout numbers
- Dimensions (every dimension string you can read)
- Notes sections (general notes, code notes, specifications)
- Material callouts and tags
- Grid lines and column markers
- Room names and area labels

### 1.3 Identify Visual Elements
Look for:
- Hatching patterns (indicate materials - concrete, insulation, earth, etc.)
- Line weights (heavy = cut lines, light = beyond)
- Symbols (north arrows, section cuts, detail markers, door/window tags)
- Leaders and arrows pointing to specific items

### 1.4 Trace Cross-References
Find every reference to other sheets:
- "SEE DETAIL 3/A401"
- "REFER TO STRUCTURAL"
- Section cut symbols pointing to other sheets
- Door/window tags referencing schedules

## STEP 2: EXTRACT EVERYTHING

Now extract what you found. Be EXHAUSTIVE. If you can read it, include it.

### For EACH Detail Found:
- Detail number (exactly as shown: "1", "2/A301", "A", etc.)
- Title (exactly as written)
- Scale
- What it shows (describe the construction assembly)
- Materials visible (concrete, steel, wood, insulation, membrane, etc.)
- Key dimensions (list them all)
- Keynotes within this detail
- References to other details/sheets

### For the Overall Sheet:
- Every keynote with its full text
- Every room/area name visible
- Every material specification mentioned
- Every dimension you can read
- Every cross-reference to other sheets

## CRITICAL: COMPLETENESS CHECK
Before outputting, verify:

**REGION CHECK:**
- Did I detect every distinct region on this sheet?
- If there are numbered details, did I get ALL of them? (Count to verify)
- Did I catch the keynotes, legend, and general notes if they exist?
- Did I include the title block?

**BOUNDING BOX CHECK:**
- Does each bbox fully contain its region (not cutting off content)?
- Is the detail title included in each detail's bbox?

**CONTENT CHECK:**
- Did I read the keynotes?
- Did I note cross-references to other sheets?

## STEP 3: BUILD HIERARCHICAL INDEX

Your output will power RAG retrieval. The structure is DETAIL-CENTRIC:

1. **Each detected region gets its own mini-index** — What's IN that detail/area
2. **Master index aggregates from all details** — Sheet-level searchability

When a superintendent asks "show me detail 3" or "what's the flashing detail?" — your index must match.

## OUTPUT STRUCTURE

Return JSON with this structure:

{
  "page_type": "floor_plan|detail_sheet|schedule|section|elevation|notes|cover|rcp|demo",
  "discipline": "architectural|structural|mechanical|electrical|plumbing|civil|kitchen|canopy",
  
  "sheet_info": {
    "number": "A002",
    "title": "DEMOLITION RCP",
    "full_title": "A002 - DEMOLITION RCP",
    "scale": "1/4\" = 1'-0\"",
    "date": "03.27.2025"
  },
  
  "index": {
    "keywords": [
      "demolition", "RCP", "reflected ceiling plan", "ceiling", 
      "air curtain", "canopy", "ACT", "acoustic ceiling tile"
    ],
    
    "areas_shown": [
      {"name": "kitchen", "notes": "ceiling demolition area"},
      {"name": "dining", "notes": "ACT ceiling to be removed"}
    ],
    
    "items": [
      {
        "name": "air curtain",
        "action": "demolish",
        "location": "entry door",
        "keynote": "7",
        "details": "remove existing air curtain at entry"
      }
    ],
    
    "keynotes": [
      {"number": "1", "text": "Existing ACT ceiling to be removed"},
      {"number": "7", "text": "Remove air curtain"}
    ],
    
    "dimensions": ["14'-0\"", "21'-6\""],
    
    "specifications": [
      "ACT ceiling: remove in shaded areas"
    ],
    
    "cross_references": [
      {"sheet": "A201", "context": "new RCP configuration"},
      {"sheet": "A301", "context": "exterior elevations"}
    ]
  },
  
  "regions": [
    {
      "id": "region_floor_plan",
      "type": "detail",
      "detail_number": "1",
      "label": "PROPOSED FLOOR PLAN",
      "bbox": {"x0": 110, "y0": 510, "x1": 810, "y1": 960},
      "confidence": 0.98,
      "scale": "1/4\" = 1'-0\"",
      "shows": "Complete floor plan showing kitchen, dining, service areas, drive-thru modifications",
      "region_index": {
        "areas": ["kitchen", "dining", "hallway", "restrooms", "service yard", "catering area"],
        "items": [
          {"name": "Tormax sliding door", "action": "install", "keynote": "1"},
          {"name": "POS counter", "action": "install", "keynote": "5"}
        ],
        "materials": [],
        "keynotes_shown": ["1", "3", "5", "8", "11", "14", "15", "21", "28"],
        "dimensions": ["17'-6 1/2\"", "26'-0\"", "42'-0\""],
        "cross_refs": ["A401", "A402", "A601"]
      }
    },
    {
      "id": "region_wall_detail",
      "type": "detail",
      "detail_number": "5",
      "label": "WALL DETAIL",
      "bbox": {"x0": 60, "y0": 240, "x1": 280, "y1": 465},
      "confidence": 0.95,
      "scale": "1-1/2\" = 1'-0\"",
      "shows": "Wall section showing FRP finish, waterproofing membrane, and base assembly",
      "region_index": {
        "areas": [],
        "items": [{"name": "waterproof membrane", "action": "install"}],
        "materials": ["FRP", "Composeal Gold 40 mil", "1/2\" CDX plywood", "2x studs @ 16\" O.C."],
        "keynotes_shown": [],
        "dimensions": ["1/2\" plywood", "16\" O.C."],
        "cross_refs": []
      }
    },
    {
      "id": "region_keynotes",
      "type": "legend",
      "label": "KEY NOTES",
      "bbox": {"x0": 740, "y0": 35, "x1": 895, "y1": 245},
      "confidence": 0.99,
      "region_index": {
        "keynotes": [
          {"number": "1", "text": "NEW TORMAX SLIDING DRIVE-THRU DOOR"},
          {"number": "3", "text": "EXISTING COLUMN TO BE BOXED WITH GYP. BD."}
        ]
      }
    },
    {
      "id": "region_title_block",
      "type": "title_block",
      "label": "TITLE BLOCK",
      "bbox": {"x0": 915, "y0": 20, "x1": 995, "y1": 980},
      "confidence": 0.99
    }
  ],
  
  "questions_this_sheet_answers": [
    "What ceiling work is being demolished?",
    "Where is the air curtain located?",
    "What needs to be protected during demolition?",
    "What keynotes are on the demo RCP?"
  ],
  
  "sheet_reflection": "## A002: DEMOLITION RCP\n\nThis sheet shows ceiling demolition scope for the renovation, identifying ACT ceiling areas to remove in dining and kitchen zones.\n\n**Key Details:**\n- **Demo Area 1 - Dining:** Remove existing ACT ceiling grid and tiles\n- **Demo Area 2 - Kitchen:** Remove ceiling to deck for new hood installation\n\n**Materials & Specs:**\n- ACT ceiling: 2x4 grid system to be removed\n- Protect existing canopy structures\n\n**Coordination Notes:**\n- Verify electrical fixture locations before demo\n- See A201 for new ceiling configuration",
  
  "cross_references": ["A201", "A301"]
}

## GUIDELINES

### REGIONS: The Foundation of Comprehension
Every detected area becomes a region with its OWN mini-index (`region_index`).

For EACH region, include:
- **id**: Unique identifier (e.g., "region_floor_plan", "region_wall_detail")
- **type**: "detail" | "legend" | "notes" | "title_block" | "schedule"
- **detail_number**: If it's a numbered detail ("1", "5", "2/A301")
- **label**: The title text shown on the drawing
- **bbox**: Bounding box coordinates (0-1000 normalized)
- **scale**: Scale for this detail/view (if shown)
- **shows**: What this region illustrates (1-2 sentences)
- **region_index**: Mini-index of what's IN this region:
  - `areas`: Rooms/spaces shown in this region
  - `items`: Equipment/elements with actions
  - `materials`: Specific materials called out
  - `keynotes_shown`: Which keynotes appear here
  - `dimensions`: Dimensions readable in this region
  - `cross_refs`: Sheet references from this region

**If you see 8 detail bubbles, you MUST have 8 regions with type "detail".**

### MASTER INDEX: Built from Regions
The top-level `index` object AGGREGATES from all region_indexes:
- Combine all keywords from all regions
- Combine all items from all regions  
- Combine all materials from all regions
- List all keynotes (from the keynotes legend region)
- Aggregate all cross-references with context

This creates a hierarchical search structure:
- Search "wall detail" → finds region_wall_detail
- Search "FRP" → finds it in region_wall_detail.region_index.materials
- Search "keynote 5" → finds it in master index AND which regions reference it

### Keywords
Extract EVERY searchable term:
- Equipment names (air curtain, RTU, VAV box, diffuser)
- Materials (ACT, gypsum board, CMU, concrete, TPO, EPDM, flashing)
- Actions (demolish, remove, protect, relocate, install, verify)
- Drawing types (RCP, floor plan, section, detail, wall section, sill detail)
- Abbreviations AND full names (RCP = reflected ceiling plan, GWB = gypsum wall board)
- Detail titles (use the exact titles as keywords)

### Items
For each significant item shown:
- What is it? (name)
- What's happening to it? (action: demolish/install/protect/relocate/verify)
- Where on the sheet? (location/area)
- Any keynote or callout number?
- Relevant details

### Areas Shown
List every room/area visible with notes about what's shown there:
- Kitchen, dining, hallway, restrooms, office
- Service yard, drive-thru, patio, walk-in cooler/freezer

### Cross References
Include context for each reference:
- "A201" → {"sheet": "A201", "context": "new RCP showing final ceiling configuration"}
- "2/A401" → {"sheet": "A401", "context": "detail 2 showing sill condition"}

### Questions This Sheet Answers
Pre-generate 5-8 natural questions based on WHAT'S ACTUALLY ON THE SHEET:
- "What does detail 1 show?"
- "How is the storefront head flashed?"
- "What's the roof assembly?"
- "Where is the vapor barrier?"

### Sheet Reflection (superintendent briefing)
Write a structured markdown summary. Use this format:

## [Sheet Number]: [Sheet Title]

[One paragraph overview - what type of sheet, what it covers, key purpose]

**Key Details:**
- **Detail [#] - [Name]:** [What it shows, key specs]
- **Detail [#] - [Name]:** [What it shows, key specs]

**Materials & Specs:**
- [Material 1 with spec]
- [Material 2 with spec]

**Coordination Notes:**
- [Cross-reference or coordination point]
- [Another coordination point]

Be specific. Name the details. Include actual specs and dimensions when visible.

### Regions (with bounding boxes)
Create a region for EACH distinct area:
- Each detail gets its own region with type "detail"
- Include the detail_number in the region
- Notes sections, legends, title blocks get their own regions

## BOUNDING BOX FORMAT
Use 0-1000 normalized coordinates where (0,0) is top-left and (1000,1000) is bottom-right.
'''
