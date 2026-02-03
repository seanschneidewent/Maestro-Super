# Phase 2 - Med Mode (Detail-Level From Brain Mode Outputs, No Vision)

## Objective

Provide detail-level guidance (regions, details, schedules blocks) using Brain Mode outputs *without* live vision. Med mode should answer: "where on the sheet should I look?" and highlight the right areas quickly.

## Scope

In scope:
- Selecting the best pages (reuse Fast mode ranker).
- Selecting relevant Brain Mode regions/details within those pages.
- Producing highlight bboxes from precomputed data:
  - region bboxes
  - semantic OCR word bboxes (if available)

Out of scope:
- Reading unknown dimensions or symbols from pixels.
- Pixel-verified answers ("the duct is 12x8") unless already in the semantic index.

## Inputs Available (from Brain Mode)

Per page:
- `sheet_reflection` markdown
- `page_type`
- `regions` with bboxes/types/labels (and embedded region vectors)
- `master_index` (items + keywords)
- `questions_answered`
- `cross_references`
- `semantic_index.words[]` with bboxes/roles (when available)

## Deliverables

### D2.1 Med mode "region selection" step
Given the selected pages, choose 3-8 regions to highlight:
- prefer regions that match query entities/keywords
- prefer schedule/note/detail regions when the query implies it
- fall back to title block / legend regions if needed

### D2.2 Highlight output format
Return highlights in a consistent schema (page_id + bbox + label + optional semantic_refs):
- region-level highlight: use region bbox
- word-level highlight: use semantic word ids and their bboxes

### D2.3 UX behavior
Med mode response pattern:
- "I pulled the best sheets and highlighted the relevant areas to check first."
- list 2-4 sheets + short per-sheet note on what is highlighted (not what is proven)

## Implementation Steps

1) Reuse Phase 1 scoring to pick pages.
2) Implement a deterministic region scoring function:
   - region type match (schedule vs plan vs notes vs detail)
   - label keyword match (equipment, WIC, RTU, panel, etc.)
   - embedding similarity (region embedding vs query embedding)
3) Integrate with frontend:
   - display highlighted bboxes on selected pages
4) Add guardrails:
   - cap highlights per page
   - ensure highlighted regions exist in page bounds

## Acceptance Criteria

- For "where is X" queries, Med mode highlights the correct plan region or schedule block most of the time.
- For detail queries ("hood detail", "curb detail"), Med mode highlights the relevant detail region when Brain Mode captured it.
- Med mode never claims pixel-verified dimensions/symbol interpretations.

## Open Questions

- Should Med mode ever auto-open a single sheet vs multiple?
- How should Med mode handle pages without semantic_index words:
  - always region highlight, or show "no highlight available"?

