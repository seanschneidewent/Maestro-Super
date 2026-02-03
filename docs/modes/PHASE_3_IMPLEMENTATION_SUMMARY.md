# Phase 3 Implementation Summary

## Status

Phase 3 is implemented for Deep mode verification planning, evidence-first tracing, and bounded fallback behavior.

- Deep mode now supports a V2 verification pipeline behind a feature flag.
- Deep execution is candidate-first and budgeted (pages, regions, micro-crops).
- Deep now emits dedicated trace + structured metrics payloads for observability.
- Deep execution summaries now include pass-level crop telemetry (`pass_1`, `pass_2`, `pass_3`).
- Deep findings are resolved through existing highlight plumbing for UI overlays.

Implementation landed in commit `f7a5ffa` on branch `smart-fast-mode`.

## What Was Delivered

### 1) Deep V2 feature flag + config wiring

- Added `DEEP_MODE_VISION_V2` setting (default `False`).
- Added runtime config access via `settings.deep_mode_vision_v2`.

File:
- `services/api/app/config.py`

### 2) Deterministic Deep verification planning helpers

Added reusable Deep planning helpers in core agent:

- Query-to-evidence target inference.
- Candidate/expansion region grouping and scoring using deterministic region signals.
- Verification plan construction with explicit budgets:
  - `max_pages`
  - `max_candidate_regions`
  - `max_expansion_regions`
  - `max_micro_crops`
- Deep finding normalization utilities for:
  - evidence gating on `verified_via_zoom`,
  - bounded finding output caps,
  - finding summary counters for trace/metrics.

Also added new Deep constants:
- `DEEP_EXPANSION_REGION_LIMIT`
- `DEEP_MICRO_CROP_LIMIT`
- `DEEP_MAX_FINDINGS`

File:
- `services/api/app/services/core/agent.py`

### 3) Deep mode pipeline upgrades (runtime behavior)

Updated `run_agent_query_deep(...)` to support Phase 3 behavior:

- Gate V2 behavior via `deep_mode_vision_v2`.
- Build and pass a structured Deep `verification_plan` to vision exploration.
- Include both `candidate_regions` and `expansion_regions` in page vision payload.
- Add bounded fallback behavior for V2 when vision execution fails:
  - avoids hard error,
  - returns explicit non-verified gap messaging.
- Resolve Deep findings to highlight overlays using existing `resolve_highlights` path.
- Emit `deep_mode_trace` tool result payload with:
  - `query_plan`
  - `page_selection`
  - `verification_plan`
  - `execution_summary`
  - `final_findings`
  - `token_cost`

File:
- `services/api/app/services/core/agent.py`

### 4) Deep vision prompt + normalization contract extensions

Upgraded Deep provider contracts to carry explicit verification metadata:

- Prompt now explicitly requires:
  - `verification_method` (`semantic_ref|region_crop|multi_pass_zoom`)
  - `verification_pass` (`1|2|3`)
  - `candidate_region_id` (when applicable)
- Prompt now documents `expansion_regions` as fallback regions.
- `explore_concept_with_vision(...)` and streaming variant now accept dict/list verification plans.
- `normalize_vision_findings(...)` now normalizes and preserves:
  - `verification_method`
  - `verification_pass`
  - `candidate_region_id`

File:
- `services/api/app/services/providers/gemini.py`

### 5) Deep observability in query router

Added Deep-mode trace extraction and structured metrics emission:

- New trace extractor: `extract_deep_mode_trace_payload(...)`
- New structured log event: `deep_mode.metrics`
- Logged fields include:
  - token cost,
  - selected page count,
  - candidate/expanded region counts,
  - verified finding count,
  - evidence-incomplete finding count,
  - fallback flag,
  - Deep latency.

File:
- `services/api/app/routers/queries.py`

### 6) Frontend Deep finding visual semantics

- Updated Deep finding bbox overlay styling to reflect confidence levels:
  - `verified_via_zoom` -> stronger verified styling
  - `high` -> distinct high-confidence styling
  - fallback `medium` -> existing amber style
- Tooltip now includes confidence text when available.

File:
- `apps/web/src/components/maestro/FindingBboxOverlay.tsx`

### 7) Phase 3 plan revision document

- Expanded the Phase 3 plan doc into an execution-oriented spec with:
  - concrete deliverables,
  - ordered implementation steps,
  - trace/metrics/test requirements.

File:
- `docs/modes/PHASE_3_DEEP_MODE_VISION_ENHANCEMENTS.md`

### 8) Deep pass-level execution telemetry

Extended Deep telemetry propagation from provider output through trace and structured logs:

- Vision provider prompt now requests `execution_summary` pass counts.
- Provider responses normalize pass counter aliases into canonical fields (`pass_1`, `pass_2`, `pass_3`).
- Core Deep pipeline emits pass counters (and `pass_total`) in `deep_mode_trace.execution_summary`.
- Query router logs pass counters in `deep_mode.metrics`.

Files:
- `services/api/app/services/providers/gemini.py`
- `services/api/app/services/core/agent.py`
- `services/api/app/routers/queries.py`

## Tests and Validation

Added/updated tests:

- Added deep trace extractor test.
- Added vision finding normalization test for verification metadata fields.
- Added Deep V2 integration test asserting:
  - `deep_mode_trace` emission,
  - highlight resolution path (`resolve_highlights`),
  - done usage accounting.
- Added Deep V2 fallback test asserting:
  - no terminal `error` event,
  - fallback recorded in Deep trace,
  - bounded empty findings output.
- Added execution-summary normalization test for pass counter aliasing.
- Extended Deep V2 integration assertions to verify pass-level telemetry in `deep_mode_trace`.

File:
- `services/api/tests/test_smart_fast_mode.py`

Validation runs:

- `python -m py_compile` passed for all changed Python files.
- Targeted tests passed:
  - `DATABASE_URL=sqlite:///./tmp_test.db pytest --noconftest services/api/tests/test_smart_fast_mode.py -q` (`18 passed`)
- Frontend production build passed:
  - `npm -C apps/web run build`

## Rollout Notes

Recommended enablement sequence:

1. Deploy with `DEEP_MODE_VISION_V2=false` (default).
2. Enable for internal projects first.
3. Monitor `deep_mode.metrics` for:
   - fallback rate,
   - verified findings vs evidence-incomplete findings,
   - latency and token cost.
4. Expand rollout after replay/eval validation.

## Known Gaps / Next Steps

- Add replay/eval harness coverage specific to Deep verification quality and evidence completeness.
- Tune Deep confidence and fallback phrasing from production traces.
- Consider optional UI legend for verified/high/medium Deep overlays if user testing indicates ambiguity.
