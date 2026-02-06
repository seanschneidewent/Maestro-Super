# Phase 2 - Med Mode (Detail-Level From Brain Mode Outputs, No Vision)

## Objective

Provide detail-level guidance (regions, detail callouts, schedule blocks) using precomputed Brain Mode outputs without live vision. Med mode should answer: "where on the sheet should I look?" and quickly highlight likely-relevant areas.

## Why this revision before implementation

Phase 1 shipped deterministic sheet routing, but the original Phase 2 plan was still too high-level for execution. This revision adds:
- Explicit backend and frontend mode-contract changes (`fast|med|deep`).
- A concrete deterministic region ranking strategy and fallback policy.
- Reuse of the existing highlight plumbing (`select_pages` + `resolve_highlights`) to avoid unnecessary UI rewrites.
- Trace/metrics requirements so Med mode remains debuggable like Fast mode.

## Phase 1 baseline to build on

Already available:
- Deterministic page routing signals and rank breakdowns in Fast mode.
- `sheet_card` persisted on pages.
- Page-level Brain Mode structures (`regions`, `master_index`, `cross_references`, `sheet_reflection`).
- Frontend highlight rendering pipeline via `resolve_highlights` output.

## Scope

In scope:
- Add Med mode as a first-class query mode.
- Reuse Fast-mode page routing to select the best pages.
- Deterministically rank/select regions within selected pages.
- Produce highlight specs from precomputed data only:
  - region bounding boxes
  - semantic OCR words (when available)
- Emit Med trace and metrics payloads for observability.

Out of scope:
- Any live OCR/vision pass.
- Pixel-verified claims for new dimensions/symbols/text.
- New persistent DB schema for Med highlights (trace/runtime only in Phase 2).

## Inputs available from Brain Mode

Per page:
- `sheet_reflection`
- `page_type`
- `regions[]` with `bbox`, `type`, `label`, optional `detail_number`, optional region embedding
- `master_index` (keywords/items/materials)
- `questions_answered`
- `cross_references`
- `semantic_index.words[]` with bbox/role/region_type (when available)

## Resolved design decisions

- Med mode returns multiple pages by default (target 2-4), not a single-page lock unless only one strong candidate exists.
- Med highlights are emitted through existing highlight tool-result semantics (`resolve_highlights`) for immediate frontend compatibility.
- If semantic words are missing, Med still highlights region bboxes when page dimensions are available.
- If neither semantic words nor usable bbox dimensions are available, Med still returns pages and explicitly says highlights are limited.
- Med mode remains non-assertive: wording is "likely area to check", never "verified fact".

## Deliverables

### D2.1 Mode contract + API wiring

- Extend request mode enum from `fast|deep` to `fast|med|deep`.
- Add backend dispatch path `run_agent_query_med(...)`.
- Add frontend mode union updates (query manager, badges, toggles, persisted query metadata).
- Add config flag:
  - `MED_MODE_REGIONS` (default `False`) for safe rollout.

### D2.2 Deterministic region ranking

Given selected pages, pick ~3-8 highlights total with per-page caps.

Minimum scoring signals:
- Region relevance from embedding similarity (`_similarity` if present, else region embedding cosine).
- Region type intent match (schedule/detail/notes/plan/title_block).
- Region label and region-index keyword/entity match.
- Query-anchor boosts (equipment tags, room names, sheet-type hints).
- Generic fallback penalty/boost rules (e.g., title block only as last resort).

### D2.3 Highlight schema and resolution

Define an internal Med highlight candidate shape:
- `page_id`
- `region_id`
- `label`
- `reason`
- `score`
- `bbox` (normalized `[x0,y0,x1,y1]`) when region-level
- `semantic_refs` when word-level evidence exists

Then resolve for frontend using existing resolver output shape:
- `[{ page_id, words: [{id,text,bbox,role,region_type,source,confidence}] }]`

### D2.4 Med trace + metrics

Add trace payload (`tool_result`) for Med:
- `tool: "med_mode_trace"`
- payload sections:
  - `query_plan` (router + routing intent summary)
  - `page_selection` (ordered pages + reason lane)
  - `region_candidates` (top scored regions per page)
  - `final_highlights` (what was emitted and why)
  - `token_cost` (router/selector totals used in Med path)

Add structured server metric log:
- `med_mode.metrics` with selected-page count, highlighted-region count, and coverage/fallback indicators.

### D2.5 UX behavior

Med response pattern:
- "I pulled the best sheets and highlighted the areas to check first."
- List 2-4 sheets with short notes on highlighted regions.
- Include confidence framing ("likely relevant", "check this area first").

## Implementation Steps (Session Order)

1) Add `med` to API schema enums and frontend query-mode unions.
2) Add `med_mode_regions` setting + feature-gated route in `run_agent_query`.
3) Factor/reuse Fast page-routing step so Med can consume ordered page IDs deterministically.
4) Implement `run_agent_query_med(...)` in backend core agent.
5) Implement deterministic region scoring helpers and per-page/global caps.
6) Emit `select_pages` and `resolve_highlights` tool events for UI compatibility.
7) Emit `med_mode_trace` payload and `med_mode.metrics` structured logs.
8) Update mode badges/toggle UX to include Med.
9) Add tests (unit + integration) for ranking, fallbacks, and trace shape.
10) Run targeted validation and verify no regressions to Fast/Deep contracts.

## Acceptance Criteria

- Med mode can be selected end-to-end (API + UI) without breaking Fast/Deep flows.
- For "where is X" queries, Med usually highlights a matching plan/schedule/detail region when Brain Mode captured it.
- For detail queries (e.g., "hood detail", "curb detail"), Med highlights the relevant detail region when present.
- Highlight output is bounded and stable:
  - max highlights per page enforced
  - max total highlights enforced
  - all emitted bboxes are valid/in-bounds
- Med never claims pixel-verified reads or symbol/dimension certainty without Deep mode.
- Med emits trace and metrics payloads sufficient for regression debugging.

## Test Plan (minimum)

- Backend unit tests:
  - region score component behavior (type/label/similarity/fallback)
  - highlight cap enforcement and deterministic ordering
  - empty/missing semantic-index fallback handling
- Backend integration test:
  - `run_agent_query_med` stream contains `select_pages`, `resolve_highlights`, `med_mode_trace`, and final `done`.
- Frontend checks:
  - mode toggle supports `fast|med|deep`
  - Med highlights render on selected pages using existing overlay path

## Remaining open questions

- Should Med always include one supporting cross-referenced sheet when confidence is high, or keep strict top-k only?
- Do we want separate Med highlight colors from Deep-verified highlights in this phase, or keep shared coloring until Phase 3?
