# Phase 0 - Contracts & Instrumentation

## Objective

Define clear behavior contracts for Fast / Med / Deep modes and add the instrumentation needed to measure routing quality, cost, and user satisfaction before major retrieval changes.

This phase prevents "we shipped a change but can't tell if it helped".

## Scope

In scope:
- Docs/specs for each mode (what it can/can't claim).
- Trace events and debug payload structure (server + UI).
- Metrics and logging for retrieval quality and cost.

Out of scope:
- Major retrieval/ranking refactors (Phase 1).
- New UI workflows for Med/Deep (Phase 2+).

## Deliverables

### D0.1 Mode contracts (written)
- Define mode names + guarantees:
  - Fast: page-level routing only.
  - Med: detail/region-level navigation using Brain Mode outputs (no live OCR/vision).
  - Deep: verified dimension/text/symbol extraction using live vision + zoom/crop.

### D0.2 API/trace schema additions
Add structured trace entries that let you reconstruct "why these pages" deterministically.

Recommended trace fields:
- `query_plan` (router output):
  - `intent`, `focus`, `must_terms`, `preferred_disciplines`, `preferred_page_types`, `area_or_level`, `strict`, `k`, `model`
- `candidate_sets`:
  - counts + top IDs per source (exact_title_hits, reflection_keyword_hits, vector_hits, region_hits, project_tree_hits)
- `rank_breakdown` (top N pages):
  - per-feature score components (title_match, page_type_match, discipline_match, entity_match, vector_rank, penalties)
- `final_selection`:
  - primary vs supporting sheets, and the reason each was included

### D0.3 Metrics / logging
Minimum viable production metrics:
- `fast_mode.token_cost` (router + selector)
- `fast_mode.pages_selected_count`
- `fast_mode.user_click_first_sheet_id` (if available)
- `fast_mode.user_followup_within_60s` (proxy for dissatisfaction)
- `fast_mode.navigation_retry_rate` (query contains "can you pull up", "those pages", etc.)

### D0.4 Evaluation harness skeleton
Create a tiny framework for replaying queries against a project:
- Input: list of `{query, expected_sheet_numbers (optional), expected_keywords (optional)}`
- Output: precision@k, whether an exact-title sheet was returned, etc.

## Implementation Plan

1) Write mode contracts in docs (short, explicit).
2) Update trace payloads to include:
   - router output
   - candidate sources + counts
   - top ranked list with score breakdown
3) Add server-side logs:
   - one structured log per query (JSON) with the above fields
4) Add UI event capture (if feasible):
   - first sheet clicked after fast routing
   - subsequent query within short window

## Acceptance Criteria

- For any fast-mode query, you can answer:
  - which sources contributed pages
  - why page A outranked page B
  - how many tokens and which models were used
- Traces are stable enough to support automated regression tests in Phase 1.

## Implementation Notes (Current)

- Detailed summary: `docs/modes/PHASE_0_IMPLEMENTATION_SUMMARY.md`.
- Mode contracts are documented in `docs/modes/MODE_CONTRACTS.md`.
- Fast mode now emits a trace `tool_result` with `tool: "fast_mode_trace"` containing:
  - `query_plan`
  - `candidate_sets`
  - `rank_breakdown`
  - `final_selection`
  - `token_cost` (router + selector + total)
- Backend structured logging emits one fast-mode metrics event per query:
  - log prefix: `fast_mode.metrics`
  - includes query identifiers + the trace payload + minimum metrics fields.
- Replay harness skeleton is available at:
  - `services/api/scripts/evaluate_fast_mode.py`
  - sample dataset: `docs/modes/eval/fast_mode_eval_dataset.sample.json`

## Open Questions

- Where should user interaction telemetry live (frontend analytics vs backend events)?
- What is the canonical definition of "success" per query type:
  - navigation success (correct sheet opened)
  - QA success (user does not re-ask / rage)
