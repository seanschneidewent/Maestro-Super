# Phase 4 - Evaluation & Rollout

## Objective

Ship improvements safely with measurable impact. Maintain regression tests and an offline evaluation harness so fast-mode routing doesn't drift.

## Scope

In scope:
- Offline evaluation set + replay harness.
- Feature flags and A/B rollout plan.
- Regression tests for high-value query patterns.

## Deliverables

### D4.1 Query evaluation dataset
Create a dataset of common jobsite queries, tagged with expected sheet archetypes:
- equipment floor plan pages
- walk-in cooler location
- panel schedule
- hood details
- demo vs new ceiling scope
- egress/life safety
- coordination ("does duct conflict with beam?")

Store:
- query text
- expected disciplines/page_types (at least)
- expected sheet titles/numbers (when available)

### D4.2 Offline harness
Run the fast ranker against a project and report:
- precision@k (when sheet IDs available)
- "exact title hit present in top k" (for navigation)
- token cost by step

### D4.3 Feature flags
Recommended flags:
- `FAST_RANKER_V2` (reflection-first scoring)
- `FAST_SELECTOR_RERANK` (tiny LLM reranker on sheet cards)
- `MED_MODE_REGIONS`
- `DEEP_MODE_VISION_V2`

### D4.4 Rollout plan
- internal dogfood projects first
- staged rollout: 5% → 25% → 50% → 100%
- monitor rage-query rate and click-through correctness

## Acceptance Criteria

- You can compare current vs new fast mode with objective metrics.
- Rolling back is one flag flip.
- High-value navigation queries have regression tests.

## Open Questions

- How to collect "correct sheet" labels at scale:
  - implicit via clicks/time-on-sheet
  - explicit via thumbs-up + sheet selection

