# Phase 4 Implementation Summary

## Status

Phase 4 is in progress for evaluation and rollout hardening across Fast, Med, and Deep modes.

- Phase 4 scope is now explicitly multi-mode (not Fast-only).
- Evaluation and rollout requirements are codified in an execution-ready plan.
- Deep pass-level telemetry (`pass_1`, `pass_2`, `pass_3`) is now available as a prerequisite signal for Phase 4 quality/cost analysis.

## What Was Delivered

### 1) Phase 4 scope revision to full Fast/Med/Deep coverage

Revised the Phase 4 plan from a narrow Fast routing focus to a full mode-evaluation and staged-rollout plan.

Highlights:
- versioned eval datasets per mode
- mode-aware replay harness expansion requirements
- regression and CI gating expectations
- explicit rollout + rollback triggers by metric

File:
- `docs/modes/PHASE_4_EVALUATION_AND_ROLLOUT.md`

### 2) Evaluation baseline inventory and instrumentation alignment

Documented and aligned Phase 4 against already-implemented mode traces/metrics:
- `fast_mode_trace` / `fast_mode.metrics`
- `med_mode_trace` / `med_mode.metrics`
- `deep_mode_trace` / `deep_mode.metrics`

This ensures offline harness design can consume existing trace sections and structured logs directly.

Files:
- `docs/modes/PHASE_4_EVALUATION_AND_ROLLOUT.md`
- `services/api/app/routers/queries.py`
- `services/api/app/services/core/agent.py`

### 3) Deep pass-level telemetry prerequisite completed

Implemented pass-level crop telemetry needed by Phase 4 Deep evaluation quality gates:
- provider contract now supports normalized `execution_summary` pass counters
- deep trace execution summary now includes `pass_1`, `pass_2`, `pass_3`, `pass_total`
- structured `deep_mode.metrics` now logs pass-level counters

Files:
- `services/api/app/services/providers/gemini.py`
- `services/api/app/services/core/agent.py`
- `services/api/app/routers/queries.py`
- `services/api/tests/test_smart_fast_mode.py`

### 4) Updated Deep summary documentation

Updated the Phase 3 summary to reflect completion of the pass-level telemetry gap so Phase 4 no longer treats it as pending.

File:
- `docs/modes/PHASE_3_IMPLEMENTATION_SUMMARY.md`

## Tests and Validation

Validated the telemetry prerequisite and regression coverage with targeted backend checks:

- `DATABASE_URL=sqlite:///./tmp_test.db pytest --noconftest services/api/tests/test_smart_fast_mode.py -q` (`18 passed`)
- `python -m py_compile services/api/app/services/providers/gemini.py services/api/app/services/core/agent.py services/api/app/routers/queries.py services/api/tests/test_smart_fast_mode.py`

## Rollout Readiness (Current)

Ready now:
- flag-based rollback path remains intact (`FAST_RANKER_V2`, `FAST_SELECTOR_RERANK`, `MED_MODE_REGIONS`, `DEEP_MODE_VISION_V2`)
- pass-level Deep telemetry is available for internal dogfood monitoring
- mode-specific trace payloads are available for offline replay scoring

Not yet complete:
- Med/Deep offline replay harness extensions
- versioned Med/Deep eval datasets
- frontend first-click sheet telemetry (`fast_mode.user_click_first_sheet_id`)

## Known Gaps / Next Steps

1. Implement mode-aware replay harness support for Med and Deep.
2. Add `fast_mode_eval_dataset.v1.json`, `med_mode_eval_dataset.v1.json`, and `deep_mode_eval_dataset.v1.json`.
3. Wire frontend click telemetry to backfill `fast_mode.user_click_first_sheet_id`.
4. Add contract tests for trace-shape and metric extraction across all modes.
5. Execute staged internal rollout and tune thresholds for go/no-go decisions.
