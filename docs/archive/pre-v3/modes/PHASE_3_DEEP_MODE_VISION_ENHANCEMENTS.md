# Phase 3 - Deep Mode (Vision Verification + Evidence Trace)

## Objective

Deliver Deep mode as a verifiable "what does it say exactly?" path by combining:
- deterministic Fast/Med retrieval priors,
- candidate-first zoom/crop vision passes,
- evidence-first outputs with bbox + confidence + verification method.

## Why this revision before implementation

Phase 2 (commit `cb84ae7`) proved a working implementation pattern we should reuse for Phase 3:
- deterministic retrieval and bounded selection before expensive inference,
- reuse of existing frontend page/highlight plumbing,
- explicit mode trace payloads + structured server metrics,
- targeted tests in `services/api/tests/test_smart_fast_mode.py`.

This Phase 3 revision turns Deep mode from a high-level concept into an execution-ready plan with concrete contracts, caps, and test requirements.

## Phase 2 baseline to build on

Already available:
- First-class mode contract (`fast|med|deep`) across API/frontend.
- Deterministic page routing/ranking foundations (Fast V2) and deterministic region priors (Med).
- Bbox-capable highlight pipeline (`resolve_highlights`) and normalized overlay rendering.
- Existing Deep flow:
  - `run_agent_query_deep(...)` in `services/api/app/services/core/agent.py`
  - `explore_concept_with_vision_streaming(...)` in `services/api/app/services/providers/gemini.py`
  - `normalize_vision_findings(...)` for finding normalization.

## Scope

In scope:
- Candidate-first Deep execution from Med/Fast-ranked pages and regions.
- Multi-pass zoom ladder with explicit pass budgets.
- Verified finding schema (source text, bbox/semantic refs, confidence, verification method).
- Deep trace + metrics payloads (parity with Fast/Med observability).
- UI-ready verified overlays from Deep findings.

Out of scope:
- Full drawing reconstruction/CAD graph generation.
- Unlimited project-wide search.
- New persisted DB schema for long-term Deep evidence storage (runtime/trace first).

## Resolved design decisions

- Deep must start from deterministic page and region priors; it does not free-browse first.
- A finding is "verified" only when backed by `source_text` plus `bbox` or `semantic_refs`.
- Deep keeps strict budgets (pages, candidate regions, expansion regions, micro-crops).
- Deep outputs must distinguish confidence tiers (`high|medium|verified_via_zoom`) and never overstate certainty.
- Rollout is feature-gated behind `DEEP_MODE_VISION_V2` (default `False`) with fallback to current Deep behavior.

## Deliverables

### D3.1 Deep verification-plan builder (backend)

Implement a deterministic planning helper in `services/api/app/services/core/agent.py` that produces:
- ordered page list (reusing existing ranking outputs),
- ordered candidate regions per page,
- expected evidence targets (dimensions/tags/symbols/text cues inferred from query),
- explicit budgets:
  - `max_pages` (default 5),
  - `max_candidate_regions` (default 8),
  - `max_expansion_regions` (default 4),
  - `max_micro_crops` (default 12).

### D3.2 Multi-pass vision execution contract

Update Deep vision execution in `services/api/app/services/providers/gemini.py`:
- enforce ladder:
  1) candidate region crop pass,
  2) tighter cluster crop pass,
  3) micro-crop disambiguation pass.
- include domain symbol hints (door/electrical/plumbing/HVAC/callouts) in prompt policy.
- require per-finding verification metadata:
  - `verification_method` (`semantic_ref|region_crop|multi_pass_zoom`)
  - `verification_pass` (`1|2|3` when applicable)
  - `candidate_region_id` when derived from candidate priors.

### D3.3 Evidence normalization + highlight integration

Extend finding normalization/output handling so Deep findings can drive overlays consistently:
- keep `semantic_refs` and normalized `bbox` behavior,
- ensure page-id aliasing remains robust,
- map verified findings into highlight-compatible payloads (or equivalent overlay shape) with confidence-preserving colors.

### D3.4 Deep trace + structured metrics

Add `deep_mode_trace` tool payload and `deep_mode.metrics` log in:
- `services/api/app/services/core/agent.py`
- `services/api/app/routers/queries.py`

Required trace sections:
- `query_plan`
- `page_selection`
- `verification_plan`
- `execution_summary` (passes/crops/expansions used)
- `final_findings` (count + evidence completeness)
- `token_cost`

Required metric fields:
- selected page count,
- candidate/expanded region counts,
- verified finding count,
- low-confidence/gap counts,
- token cost + latency.

### D3.5 Feature flag + fallback policy

Add config/runtime guard:
- `DEEP_MODE_VISION_V2` (default `False`) in `services/api/app/config.py`.

Behavior:
- when disabled: preserve current Deep path.
- when enabled: run Phase 3 verification pipeline.
- on Deep verification failure: degrade to bounded non-verified guidance (never emit false verification claims).

## Implementation Steps (Session Order)

1) Add `DEEP_MODE_VISION_V2` setting and gating in Deep mode dispatch.
2) Factor deterministic Deep verification-plan builder from existing retrieval + candidate region data.
3) Add caps/budget constants and enforce them in Deep pipeline.
4) Update Deep vision prompt + parsing contract for pass-aware verification metadata.
5) Implement/extend finding normalization for new verification fields.
6) Wire Deep findings into overlay-compatible highlight output path.
7) Emit `deep_mode_trace` payload in stream trace.
8) Add `deep_mode.metrics` structured logging in query router.
9) Add tests (unit + integration) for caps, normalization, trace shape, and fallback behavior.
10) Run targeted backend tests and frontend build verification.

## Acceptance Criteria

- Deep mode starts with candidate priors and only expands when needed.
- Each "verified" finding includes evidence (`source_text` + `bbox`/`semantic_refs`) and verification metadata.
- Deep emits `deep_mode_trace` + `deep_mode.metrics` with enough detail for regression debugging.
- Output overlays can consistently render Deep evidence on-page.
- Cost and latency stay bounded by configured budgets.

## Test Plan (minimum)

- Backend unit tests:
  - verification-plan ordering and cap enforcement,
  - finding normalization with bbox/ref fallbacks,
  - verification confidence gating (no evidence -> not verified).
- Backend integration test:
  - Deep stream includes `select_pages`, `explore_concept_with_vision`, `deep_mode_trace`, and `done`.
- Router metrics test:
  - `deep_mode.metrics` includes required counters and token-cost fallbacks.
- Frontend checks:
  - Deep findings render bbox overlays and confidence semantics without regressing Fast/Med highlights.

## Remaining open questions

- Which vision model tier should be default for Deep V2 (quality vs latency)?
- Should Deep auto-retry one additional micro-crop pass when confidence is medium but near-threshold?
- Do we want separate visual styling for "verified" vs "probable" Deep findings in this phase or Phase 4?
