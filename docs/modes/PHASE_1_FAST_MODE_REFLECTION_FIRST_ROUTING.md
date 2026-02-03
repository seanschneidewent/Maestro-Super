# Phase 1 - Fast Mode (Reflection-First Routing)

## Objective

Make Fast mode reliably route users to the correct sheets using Brain Mode `sheet_reflection` (markdown) + metadata, while keeping token use low and fallbacks deterministic.

Key outcomes:
- Exact sheet-title queries ("equipment floor plan pages") become near-perfect.
- Broad questions still return the best *pages* quickly (not details).
- The system remains robust when reflections are missing/partial.

## Scope

In scope:
- Using `sheet_reflection` and its derived structure for retrieval/ranking.
- Deterministic ranking with clear fallbacks.
- Minimized LLM prompt sizes.

Out of scope:
- Region/detail highlighting (Med mode).
- Live vision verification (Deep mode).

## Why Reflection-First Works

The reflection markdown is the best semantic "index card" for each sheet:
- It explicitly says what the sheet covers, key regions, and cross-refs.
- It encodes sheet type (plan/schedule/detail/notes) better than raw OCR.
- It can be used for both lexical and vector retrieval.

## Deliverables

### D1.1 "Sheet Card" extraction (processing-time)
Create a derived per-page structure from the reflection markdown and stored metadata.

Suggested fields:
- `reflection_title` (normalized, one line)
- `reflection_summary` (first paragraph, 1-2 sentences)
- `reflection_headings` (list)
- `reflection_keywords` (merged set: reflection + master_index keywords)
- `reflection_entities` (light extraction: room names, equipment tags, systems)
- `page_type`, `sheet_number`, `discipline_name`
- `cross_references` (already)

Storage options:
- `pages.sheet_card` JSONB (fast to ship, flexible)
- or discrete indexed columns for `reflection_title`, `reflection_keywords`, etc.

### D1.2 Lexical retrieval lane (exact-title / phrase-first)
Add a retrieval step that can dominate when it should:
- Exact phrase match on `reflection_title`
- Strong match on `reflection_title + sheet_number + page_type`
- Soft match on headings/keywords

This lane should beat vector similarity for explicit navigation.

### D1.3 Unified scoring + selection (replace merge-then-sort)
Replace:
- "merge ids then sort by sheet order"

With:
- "score candidates then pick primary/supporting"

Minimum scoring signals:
- exact title phrase match (huge)
- page_type match (plan vs schedule vs notes vs detail)
- discipline match (kitchen vs mech vs electrical)
- area/level hints (kitchen, dining, roof, level 1)
- entity/tag match (WIC-1, AHU-2, panel L1)
- vector similarity (moderate)
- penalties for generic sheets unless requested

Selection policy:
- `k_primary` (2-4 typical)
- `k_supporting` (0-2): schedules/notes/details referenced by primary

### D1.4 Prompt minimization strategy
End-state options (pick one):
1) No LLM page selector: deterministic scoring chooses sheets; LLM only writes the 1-sentence response (or templated).
2) Tiny LLM re-ranker: provide only ~8-16 sheet cards (not full markdown) and ask it to pick top 4 + response.

### D1.5 Construction-aware fallbacks
If no strong hits:
- Prefer cover/index/sheet list pages (A0xx/G0xx) over random early sheets.
- Prefer vector top pages over "first pages from project structure".

## Implementation Steps (Suggested Order)

1) Build sheet-card extraction from `sheet_reflection` (processing job).
2) Add DB storage + minimal indexing.
3) Implement lexical "exact title / phrase" retrieval step.
4) Implement scoring function + ranked selection.
5) Gate new ranker behind feature flag:
   - `FAST_RANKER_V2`
6) Reduce selector prompt payloads (sheet cards only).
7) Tune weights using real query logs + eval harness (Phase 4).

## Acceptance Criteria

- For explicit navigation queries, top 1-3 sheets include exact title matches when they exist.
- For broad QA queries, top sheets are relevant and *not* dominated by cover/schedule/admin pages.
- Token usage in fast mode decreases or remains flat compared to current behavior.
- Deterministic fallbacks never return "random early pages" when index/cover exists.

## Risks / Edge Cases

- Some projects do not have consistent sheet titles; rely on headings/keywords and master_index.
- Some pages may have missing reflections; fall back to vector embedding + minimal keyword search.
- Inconsistent discipline naming (Kitchen vs Food Service vs K).

## Open Questions

- Where should "title" come from if reflection title extraction fails?
- How aggressive should cross-reference expansion be in fast mode:
  - likely 0-2 supporting pages max

