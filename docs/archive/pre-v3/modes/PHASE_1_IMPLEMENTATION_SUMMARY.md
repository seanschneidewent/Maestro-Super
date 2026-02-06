# Phase 1 Implementation Summary

## Status

Phase 1 is implemented for Fast mode reflection-first routing foundations:

- Sheet-card extraction and storage are live.
- Fast deterministic ranking V2 is implemented and feature-gated.
- Selector payloads are minimized around sheet cards.
- Phase 0 trace and metrics contracts remain intact.

Implementation landed in commit `912dbe8` on branch `smart-fast-mode`.

## What Was Delivered

### 1) Sheet-card extraction + storage

Added a reusable sheet-card builder that derives compact retrieval metadata from:

- `sheet_reflection`
- `master_index`
- `cross_references`
- page metadata (`sheet_number`, `page_type`, `discipline_name`)

Generated card fields:

- `reflection_title`
- `reflection_summary`
- `reflection_headings`
- `reflection_keywords`
- `reflection_entities`
- `sheet_number`
- `page_type`
- `discipline_name`
- `cross_references`

Schema/storage changes:

- New column: `pages.sheet_card` (`JSONB`)
- Alembic migration: `services/api/alembic/versions/20260203_090000_add_sheet_card_to_pages.py`
- ORM model update: `services/api/app/models/page.py`

Processing integration:

- Brain Mode processing now builds and persists `sheet_card` during page processing.
- File: `services/api/app/services/core/processing_job.py`

### 2) Retrieval payload integration

Fast-mode page search payloads now include `sheet_card` and normalized `cross_references`.

- File: `services/api/app/services/tools.py`

When a stored `sheet_card` is missing, it is built on read as a fallback so routing can still use the new signals.

### 3) Fast ranker V2 (deterministic scoring path)

Implemented deterministic ranking helpers and a V2 candidate scorer:

- `_compute_rank_score_components(...)`
- `_rank_candidate_page_ids_v2(...)`
- `_select_cover_index_fallback_page_ids(...)`
- `_hydrate_sheet_card(...)`

Primary scoring signals now include:

- title/phrase match
- exact-title source hit
- lexical source hit (strict/reflection lanes)
- page type match
- discipline match
- area/level match
- entity match
- vector rank contribution
- generic-sheet penalties

File: `services/api/app/services/core/agent.py`

### 4) Feature flags + selector strategy

Added new settings:

- `fast_ranker_v2` (default: `False`)
- `fast_selector_rerank` (default: `False`)

Behavior:

- If `fast_ranker_v2=True` and `fast_selector_rerank=False`, Fast mode skips selector LLM and uses deterministic ranking.
- If `fast_selector_rerank=True`, selector can still run after V2 candidate narrowing.

File: `services/api/app/config.py`

### 5) Selector prompt/payload minimization

Smart selector candidate payloads are now sheet-card-first:

- include compact sheet-card fields
- reduce raw content size significantly (short cap)
- keep minimal compatibility fields for existing behavior

File: `services/api/app/services/providers/gemini.py`

### 6) Trace compatibility + added plan metadata

Fast trace payload structure remains:

- `query_plan`
- `candidate_sets`
- `rank_breakdown`
- `final_selection`
- `token_cost`

`query_plan` now additionally includes:

- `ranker` (`v1` or `v2`)
- `selector_rerank` (bool)

Rank breakdown now reports expanded score components used by V2 (while preserving deterministic explainability).

File: `services/api/app/services/core/agent.py`

## Tests and Validation

Added/updated tests:

- Updated existing fast-mode tests for `_order_page_ids(..., sort_by_sheet_number=...)` signature.
- Added sheet-card extraction test.
- Added V2 deterministic routing test (selector skipped path).
- File: `services/api/tests/test_smart_fast_mode.py`

Validation run:

- `py_compile` checks passed for all changed Python modules.
- Manual deterministic smoke run verified V2 ranking behavior and router-only token accounting.
- `pytest` remains blocked by pre-existing unrelated `tests/conftest.py` import issue (`ContextPointer` import), consistent with prior phase notes.

## Notes on Rollout

Recommended enablement sequence:

1. Deploy with defaults (`fast_ranker_v2=False`).
2. Enable `fast_ranker_v2` for internal projects.
3. Optionally enable `fast_selector_rerank` only if additional rerank quality is needed.
4. Monitor existing `fast_mode.metrics` logs and replay harness before broad rollout.

## Known Gaps / Next Steps

- Weight tuning on real query logs and eval datasets (Phase 4 alignment).
- Optional indexing strategy on `sheet_card` subfields if query volume requires it.
- Resolve unrelated test harness import blocker to restore full `pytest` coverage gate.
