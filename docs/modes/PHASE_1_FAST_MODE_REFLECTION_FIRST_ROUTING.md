# Phase 1 - Fast Mode (Reflection-First Routing)

## Objective

Make Fast mode reliably route users to the correct sheets using Brain Mode `sheet_reflection` + metadata, while reducing token spend and keeping fallbacks deterministic.

Key outcomes:
- Exact sheet-title queries ("equipment floor plan pages") become near-perfect.
- Broad questions still return the best pages quickly (not detail-level assertions).
- Missing/partial reflections degrade gracefully.

## Phase 0 Baseline (Already Shipped)

From commit `1ac8d53`, Fast mode already includes:
- Router plan + strict mode (`route_fast_query`) and routed query construction.
- Candidate source tracing (`candidate_sets`), score diagnostics (`rank_breakdown`), and `final_selection` reason codes.
- Exact-title and strict keyword helper logic in the current flow.
- Structured metrics logs (`fast_mode.metrics`) and replay harness (`scripts/evaluate_fast_mode.py`).

Phase 1 should build on this baseline without regressing Phase 0 observability contracts.

## Scope

In scope:
- Reflection-first retrieval and ranking with deterministic scoring.
- Sheet-card extraction for small, structured candidate payloads.
- Lower-token selection path (deterministic or tiny reranker).
- Better construction-aware fallback behavior.

Out of scope:
- Region/detail highlights (Phase 2).
- Live vision verification (Phase 3).

## Deliverables

### D1.1 Sheet-card extraction contract

Create a derived `sheet_card` structure from reflection + metadata.

Required fields:
- `reflection_title`
- `reflection_summary`
- `reflection_headings`
- `reflection_keywords` (reflection + master_index)
- `reflection_entities` (light tags: rooms/equipment/systems)
- `sheet_number`, `page_type`, `discipline_name`
- `cross_references`

Storage path:
- Prefer `pages.sheet_card` JSONB for first ship, with optional indexed columns later.

### D1.2 Lexical retrieval lane (title/phrase-first)

Add a retrieval lane that can dominate vector hits for explicit navigation:
- Exact/near-exact phrase match on `reflection_title`.
- Strong match on `reflection_title + sheet_number + page_type`.
- Soft match on headings/keywords/entities.

### D1.3 Deterministic ranker V2 (replace merge-then-sort)

Replace merge-order selection with unified scoring across candidate sources.

Minimum scoring signals:
- exact title phrase match (high weight)
- page_type match
- discipline match
- area/level hints
- entity/tag match
- vector rank contribution (moderate)
- penalty for generic/admin sheets unless explicitly requested

Selection policy:
- `k_primary`: 2-4
- `k_supporting`: 0-2 (cross-referenced schedules/notes/details)

Ship behind feature flag:
- `FAST_RANKER_V2`

### D1.4 Prompt minimization / selector strategy

Use one of these end states:
1) Deterministic ranker selects pages; optional template response (no selector LLM).
2) Tiny reranker on 8-16 `sheet_card` objects only (no full markdown payload).

### D1.5 Construction-aware fallback policy

If strong matches are missing:
- Prefer cover/index/sheet-list pages over random early pages.
- Prefer vector top hits over project-tree "first pages".
- Keep strict-mode fallbacks narrow.

### D1.6 Validation updates

Extend tests + eval to cover:
- exact-title routing
- strict navigation filtering
- generic-page penalty behavior
- token-cost deltas vs baseline

## Implementation Steps (Session Order)

1) Add `sheet_card` builder utility from `sheet_reflection` (+ unit tests).
2) Thread `sheet_card` through fast-mode candidate payloads.
3) Implement lexical retrieval lane and integrate with existing candidate sets.
4) Implement `FAST_RANKER_V2` scoring/selection in `run_agent_query_fast`.
5) Keep/adjust trace payloads so `query_plan`, `candidate_sets`, `rank_breakdown`, `final_selection`, and `token_cost` remain stable.
6) Minimize selector payloads (or bypass selector) behind config flags.
7) Run replay harness + targeted tests; tune weights with logged query samples.

## Acceptance Criteria

- Explicit navigation queries return exact-title sheets in top 1-3 when present.
- Broad QA routing avoids being dominated by cover/notes/admin pages.
- Token usage is flat or lower than current fast-mode baseline.
- Deterministic fallback no longer returns arbitrary first project pages.
- Phase 0 trace + metrics contracts remain intact.

## Risks / Edge Cases

- Inconsistent sheet naming across projects; rely on headings/keywords/entities.
- Missing reflections on some pages; require keyword/vector fallback.
- Discipline alias drift (Kitchen vs Food Service vs K) can weaken discipline scoring.

## Open Questions

- If `reflection_title` extraction fails, what is canonical title priority order?
- Should cross-reference expansion happen before or after primary page cap?
- Do we keep a tiny selector reranker long-term, or move fully deterministic?
