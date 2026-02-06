# Mode Contracts

This document defines what each mode is allowed to claim, what it must return, and what it must never imply.

## Fast Mode Contract

- Purpose: page-level routing ("which sheets should I open first?").
- Required behavior:
  - Return 2-8 candidate sheets with clear ordering.
  - Include traceable routing metadata (`query_plan`, `candidate_sets`, `rank_breakdown`, `final_selection`).
  - Keep token cost low and deterministic fallbacks stable.
- Must not claim:
  - Pixel-verified dimensions, symbol interpretation, or exact on-sheet text unless already pre-indexed and explicitly cited from precomputed metadata.

## Med Mode Contract

- Purpose: region/detail guidance from precomputed Brain Mode outputs ("where on the sheet should I look?").
- Required behavior:
  - Reuse fast-mode page routing.
  - Return bounded highlight regions and/or semantic word bboxes.
  - Describe highlighted areas as likely-relevant, not proven facts.
- Must not claim:
  - Live OCR/vision verification.
  - New dimension/symbol reads from raw pixels.

## Deep Mode Contract

- Purpose: verified extraction ("what does it say/measure/show exactly?").
- Required behavior:
  - Inspect prioritized pages/regions with zoom/crop passes.
  - Return evidence-first outputs (exact read text, bbox, confidence, verification method).
  - Enforce strict page/region/cost caps.
- Must not claim:
  - Global certainty without evidence artifacts.
  - Unlimited full-project inspection.

## Shared Safety Rules

- Distinguish confidence levels in response wording.
- Preserve deterministic fallbacks when model calls fail.
- Emit trace/debug payloads that explain why pages were selected.
- Prefer "I need deeper verification" over overconfident claims.
