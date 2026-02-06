# Phase 4 - Evaluation & Rollout

## Objective

Ship Fast, Med, and Deep improvements safely with measurable gains in quality, evidence reliability, latency, and token cost.

## Why this revision now

Phase 3 (commit `f7a5ffa`) completed Deep V2 verification planning, evidence gating, bounded fallback behavior, and mode-specific trace/metrics payloads. Phase 4 should now focus on evaluation and rollout of all three modes, not fast-only routing.

## Baseline after Phase 3

Already implemented and available for evaluation:
- Fast observability: `fast_mode_trace` + `fast_mode.metrics`.
- Med observability: `med_mode_trace` + `med_mode.metrics`.
- Deep observability: `deep_mode_trace` + `deep_mode.metrics` with `verification_plan`, `execution_summary`, and `final_findings`.
- Feature flags: `FAST_RANKER_V2`, `FAST_SELECTOR_RERANK`, `MED_MODE_REGIONS`, `DEEP_MODE_VISION_V2`.
- Existing harness: `services/api/scripts/evaluate_fast_mode.py` (Fast only).

## Scope

In scope:
- Versioned offline datasets for Fast/Med/Deep.
- Replay harness coverage for all modes with comparable output format.
- Regression tests and CI checks for trace shape and quality gates.
- Flag-driven staged rollout with explicit rollback triggers.
- Telemetry completion for currently missing/high-value fields.

Out of scope:
- New model architecture work.
- Unlimited full-project Deep scans outside configured budgets.
- Long-term BI/dashboard buildout beyond required structured logs and reports.

## Resolved design decisions

- Use mode trace payloads as the source of truth for offline evaluation.
- Keep rollout reversible through existing feature flags.
- Evaluate Deep verified quality with evidence completeness and fallback rate, not raw answer volume.
- Treat Med and Deep overlay usability (confidence semantics) as rollout criteria, not cosmetic-only work.

## Deliverables

### D4.1 Versioned evaluation datasets

Create datasets under `docs/modes/eval/`:
- `fast_mode_eval_dataset.v1.json`
- `med_mode_eval_dataset.v1.json`
- `deep_mode_eval_dataset.v1.json`

Required row fields:
- `query`
- `mode`
- expected page targets (`expected_page_ids`, `expected_sheet_numbers`, `expected_sheet_titles`)
- expected signal targets by mode:
  - Med: expected region labels/types or expected highlighted page anchors
  - Deep: expected finding categories plus evidence expectations (`source_text` + `bbox` or `semantic_refs`)
- optional difficulty tags (`navigation`, `coordination`, `qa`, `ambiguous`, `low_context`)

### D4.2 Replay harness expansion

Extend offline replay beyond Fast:
- keep `evaluate_fast_mode.py` for backward compatibility
- add mode-aware harness support (single multi-mode script or dedicated Med/Deep scripts)

Required outputs:
- shared summary: case counts, latency, token cost, pass/fail counters
- Fast metrics: precision@k, exact-title hit, sheet-number hit
- Med metrics: page-hit@k, region/highlight coverage, highlighted-page resolution rate
- Deep metrics: verified finding rate, evidence completeness rate, fallback rate, downgraded-verified rate, bounded-findings compliance

### D4.3 Telemetry completion and metric parity

Close known observability gaps:
- wire frontend click telemetry to replace placeholder `fast_mode.user_click_first_sheet_id = null`
- add pass-level Deep telemetry (`pass_1`, `pass_2`, `pass_3`) in `execution_summary` when provider output supports it
- ensure replay reports consume current structured log keys:
  - `fast_mode.metrics`
  - `med_mode.metrics`
  - `deep_mode.metrics`

### D4.4 Regression tests and CI gates

Add/extend tests in `services/api/tests/test_smart_fast_mode.py` and harness tests:
- trace shape contract tests for Fast/Med/Deep payload sections
- metric extractor tests for each mode
- fallback/evidence-gating regression tests for Deep
- replay harness parsing tests for dataset schema and summary output

CI minimum gates:
- targeted backend tests pass
- replay harness smoke run on sample datasets succeeds
- frontend build remains green (`apps/web`)

### D4.5 Rollout playbook

Roll out in controlled stages:
1. Deploy with defaults (all new flags off where applicable).
2. Internal projects: enable `FAST_RANKER_V2`; keep selector rerank optional.
3. Internal projects: enable `MED_MODE_REGIONS`; validate highlight precision.
4. Internal projects: enable `DEEP_MODE_VISION_V2`; monitor fallback/evidence counters.
5. External staged rollout by project cohort: 5% -> 25% -> 50% -> 100%.

Rollback triggers (any stage):
- sustained increase in navigation retry rate
- sustained Med highlight miss regressions
- sustained Deep fallback spikes or evidence-incomplete findings
- unacceptable token/latency regressions

### D4.6 UX calibration from production traces

Use trace + replay outcomes to finalize:
- Deep confidence/fallback phrasing
- optional overlay legend for `verified_via_zoom|high|medium`
- whether Med/Deep need distinct highlight semantics beyond current styling

## Implementation steps (session order)

1. Finalize dataset schemas and add v1 JSON files for Fast/Med/Deep.
2. Implement harness support for Med and Deep replay paths.
3. Add shared result writer (JSON + concise markdown summary).
4. Wire missing click telemetry for Fast first-click sheet metric.
5. Add Deep pass-level execution counters to trace/metrics payloads.
6. Add/extend extractor and contract tests.
7. Run targeted backend tests and replay smoke runs.
8. Run frontend build validation.
9. Execute internal rollout and monitor mode metrics.
10. Tune weights/phrasing from findings before broader rollout.

## Acceptance criteria

- Offline evaluation can compare Fast/Med/Deep behavior with objective metrics.
- Telemetry covers existing Phase 0-3 gaps needed for rollout decisions.
- Feature rollout and rollback are achievable through existing flags only.
- High-value query classes have stable regression coverage.
- Deep verified claims remain evidence-backed under rollout traffic.

## Open questions

- What threshold values define go/no-go for each mode (quality, fallback, latency, token deltas)?
- Should Med and Deep share one combined dataset or remain separately labeled for clearer ownership?
- How should correct-label collection scale: implicit interaction signals only, or explicit reviewer labeling workflow?
