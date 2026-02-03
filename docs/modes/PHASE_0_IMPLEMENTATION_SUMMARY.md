# Phase 0 Implementation Summary

## Status

Phase 0 is implemented for backend contracts, tracing instrumentation, and offline evaluation scaffolding.

## What Was Delivered

### 1) Mode contracts

- Added explicit mode guarantees and non-goals in `docs/modes/MODE_CONTRACTS.md`.
- Linked contract docs in `docs/modes/README.md`.

### 2) Fast-mode trace schema additions

Fast mode now emits a dedicated trace entry:

- `type: "tool_result"`
- `tool: "fast_mode_trace"`
- `result` includes:
  - `query_plan`
  - `candidate_sets`
  - `rank_breakdown`
  - `final_selection`
  - `token_cost` (router + selector + total)

Implemented in `services/api/app/services/core/agent.py`.

### 3) Production metrics logging (structured)

Added one structured server log per fast-mode query with:

- `fast_mode.token_cost`
- `fast_mode.pages_selected_count`
- `fast_mode.user_click_first_sheet_id` (placeholder: `null` until frontend click telemetry is wired)
- `fast_mode.user_followup_within_60s`
- `fast_mode.navigation_retry_rate`

Implemented in `services/api/app/routers/queries.py` (log prefix: `fast_mode.metrics`).

### 4) Evaluation harness skeleton

Added replay harness and sample dataset:

- Harness: `services/api/scripts/evaluate_fast_mode.py`
- Sample dataset: `docs/modes/eval/fast_mode_eval_dataset.sample.json`
- Usage notes: `docs/modes/eval/README.md`

## Key Behavior Notes

- Fast-mode `done.usage` now reports combined router + selector token usage.
- Candidate/source reasoning is deterministic and inspectable for ranking/debug.
- Existing query stream behavior remains backwards-compatible for frontend consumers.

## Validation Run

- Python compile checks passed for updated backend modules and harness script.
- Smart fast-mode tests were validated manually.
- Full `pytest` run is currently blocked by an existing unrelated import issue in `tests/conftest.py`.

## Known Gaps (Intentional for Phase 0)

- No frontend click telemetry yet for first clicked sheet (`user_click_first_sheet_id` remains `null`).
- No rollout/flag orchestration yet (planned in later phases).
