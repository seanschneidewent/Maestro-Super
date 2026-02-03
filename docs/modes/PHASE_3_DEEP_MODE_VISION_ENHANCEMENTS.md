# Phase 3 - Deep Mode Enhancements (Vision + Verified Facts)

## Objective

Enable verified extraction of text, symbols, and dimensions using live vision + zoom/crop, starting from the best pages/regions found in Fast/Med.

Deep mode should answer: "what does it say exactly?" with bboxes and confidence.

## Scope

In scope:
- Cropping/zooming into candidate regions first (avoid full-sheet passes).
- Symbol/dimension extraction patterns.
- Structured outputs (bboxes, semantic refs when possible).
- "Verification plan" workflow (what to inspect, expected outputs).

Out of scope:
- Full CAD-like reconstruction.
- Unlimited browsing across dozens of pages.

## Strategy

1) Use the Fast/Med ranker to pick best pages (2-6).
2) Use Med mode to pick best candidate regions (3-10).
3) Deep mode inspects candidate regions via crops first:
   - only expand beyond candidates if insufficient

## Enhancements to Add

### D3.1 Multi-pass zoom ladder
- pass 1: region crop (loose)
- pass 2: tighter crop around suspected text/dimensions/symbol clusters
- pass 3: micro-crops for ambiguous reads

### D3.2 Symbol dictionaries + heuristics
Common construction symbol sets to support:
- door tags + handing
- electrical panel/circuit symbols
- plumbing fixtures + valve/cleanout symbols
- HVAC diffusers/grilles + tags
- section/elevation/detail callouts

### D3.3 Evidence-first outputs
Deep mode must return:
- exact text as read
- bbox (normalized or pixel) for each cited element
- confidence + how it was obtained ("verified_via_zoom")

### D3.4 Cost controls
- strict caps on pages and regions inspected
- bail-out when confidence remains low

## Acceptance Criteria

- Deep mode can reliably extract a target dimension/tag/label when it exists in the selected candidate regions.
- Outputs include bboxes sufficient for UI highlighting.
- Deep mode latency and cost remain bounded by strict caps.

## Open Questions

- Model choice for deep vision inference (speed vs accuracy trade).
- How to handle handwriting / scanned low-res prints.

