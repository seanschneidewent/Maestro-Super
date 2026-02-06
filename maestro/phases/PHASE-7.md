# Phase 7: The Benchmark

## Context

Read `maestro/MAESTRO-ARCHITECTURE-V3.md` — it is the alignment doc for the entire V3 architecture. This phase builds the measurement and optimization layer.

**Look at the Phase 1-6 commits to understand what was built.** Phase 6 delivered:
- Heartbeat system with proactive insights and calculated scheduling questions
- Heartbeats run through Telegram Maestro (same conversation, same context)
- Schedule × Knowledge × Experience cross-referencing
- The flywheel: super's responses feed Learning → smarter heartbeats

**Current state:** The full V3 system is running. Maestro has persistent conversations, Learning writes Experience, heartbeats drive proactive engagement. Now we need to measure whether it's actually getting better.

## Goal

1. **Benchmark logging** — Capture structured data from every interaction for evaluation
2. **Emergent scoring** — Learning's observations generate scoring dimensions (not predefined rubrics)
3. **Model comparison** — Replay queries across different model providers, compare quality
4. **Evolution tracking** — Is Maestro getting better over time? Quantifiable answer.
5. **User-facing confidence** — Subtle signals to the super about Maestro's confidence level

## What This Phase Delivers

After this phase ships:
- Every interaction is logged with structured benchmark data
- Learning generates scoring criteria from its observations (emergent, not hardcoded)
- Can swap MAESTRO_MODEL to a different provider, replay recent queries, compare results
- Dashboard or report showing Maestro quality trends over time
- Super sees subtle confidence indicators in Maestro's responses

## Architecture Reference

See the V3 alignment doc sections:
- **"Maestro Learning — The Benchmark Engine"** — Learning IS the benchmark
- **"The benchmark is emergent"** (Key Decision #3)
- **"Experience IS the test suite"** (Key Decision #4)
- **"The shell matters more than the model"** (Key Decision #7)
- **Implementation Path: Phase 7** — checklist

## Detailed Requirements

### R1: Benchmark Logging Table

**Create Alembic migration for `benchmark_logs` table:**

```sql
CREATE TABLE benchmark_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES sessions(id),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    turn_number     INTEGER NOT NULL,
    is_heartbeat    BOOLEAN DEFAULT FALSE,

    -- Input
    user_query      TEXT NOT NULL,
    experience_paths_read   TEXT[],        -- which Experience files were used
    pointers_retrieved      JSONB,         -- [{pointer_id, title, relevance_score}]
    workspace_actions       JSONB,         -- [{action, targets}]

    -- Output
    maestro_response        TEXT NOT NULL,
    response_model          TEXT NOT NULL,  -- which model generated this
    response_latency_ms     INTEGER,
    token_count_input       INTEGER,
    token_count_output      INTEGER,

    -- Learning evaluation (filled async by Learning agent)
    learning_assessment     JSONB,         -- free-form evaluation from Learning
    scoring_dimensions      JSONB,         -- emergent scores: {dimension: score}
    experience_updates      JSONB,         -- what Learning wrote as a result
    knowledge_edits         JSONB,         -- what Learning edited in Knowledge

    -- User signals (filled from subsequent interaction)
    user_followed_up        BOOLEAN,       -- did user continue on same topic?
    user_corrected          BOOLEAN,       -- did user correct Maestro?
    user_rephrased          BOOLEAN,       -- did user rephrase (missed the mark)?
    user_moved_on           BOOLEAN,       -- did user change topic (sufficient)?

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_benchmark_project ON benchmark_logs(project_id);
CREATE INDEX idx_benchmark_session ON benchmark_logs(session_id);
CREATE INDEX idx_benchmark_model ON benchmark_logs(response_model);
```

### R2: Benchmark Logger

**Create `services/api/app/services/v3/benchmark.py`:**

`log_benchmark(session, interaction, maestro_response, model, latency_ms, tokens, db)`:
- Creates a `benchmark_logs` row with the input/output data
- Returns the `benchmark_id` for later Learning updates

`update_benchmark_learning(benchmark_id, assessment, scores, experience_updates, knowledge_edits, db)`:
- Called by Learning after it processes the interaction
- Updates the `learning_assessment`, `scoring_dimensions`, `experience_updates`, `knowledge_edits` fields

`update_benchmark_user_signals(benchmark_id, signals, db)`:
- Called during the NEXT Maestro turn — looks at the user's follow-up message
- Detects: correction, rephrasing, follow-up, or topic change
- Updates the user signal fields

### R3: Emergent Scoring

**Modify Learning system prompt in `learning_agent.py`:**

Add benchmark evaluation instructions:
- "After evaluating each interaction, provide a structured assessment"
- "Generate scoring dimensions that EMERGE from what you observe — don't use a fixed rubric"
- "Common dimensions might include: retrieval_relevance, response_accuracy, gap_identification, workspace_assembly_quality, experience_application — but let the interaction tell you what matters"
- "Score each dimension 0-1 with a brief justification"

**Learning's assessment gets stored in `benchmark_logs.learning_assessment`** as free-form JSONB.

**Scoring dimensions** are not predefined — they emerge from Learning's observations. Over time, patterns appear: which dimensions does Learning consistently evaluate? Those become the benchmark.

### R4: Model Comparison Harness

**Create `services/api/app/services/v3/model_compare.py`:**

`run_model_comparison(project_id, model_a, model_b, query_ids, db)`:
1. For each query in `query_ids` (pulled from `benchmark_logs`):
   - Reconstruct the input: user_query + Experience context + Knowledge context
   - Run through Model A → capture response
   - Run through Model B → capture response
2. For each pair: run Learning evaluation on both responses
3. Return comparison report: `[{query, response_a, response_b, scores_a, scores_b}]`

**Usage:**
- Change `MAESTRO_MODEL` from `gemini-3-flash-preview` to `claude-opus-4-5`
- Run comparison on last 20 queries
- See which model scores better on which dimensions

**This is an admin/developer tool** — not user-facing in v1. Can be a CLI script or admin API endpoint.

### R5: Evolution Tracking

**Create `services/api/app/services/v3/benchmark_report.py`:**

`generate_evolution_report(project_id, time_range, db)` → `dict`:
- Pull all `benchmark_logs` for the project in the time range
- Aggregate scoring dimensions over time (rolling average)
- Track: average scores per dimension, user correction rate, user follow-up rate
- Return: `{dimensions: [{name, scores_over_time}], correction_rate_over_time, insights}`

**Key metrics:**
- **Retrieval hit rate** — did Maestro find the right Pointers? (proxy: user didn't rephrase)
- **Experience application** — did routing rules improve retrieval? (proxy: compare queries before/after routing rule was written)
- **User correction rate** — going down over time = getting better
- **Heartbeat response rate** — are heartbeats generating responses? (proxy for relevance)
- **Experience file growth** — how much is Learning writing? (proxy for active learning)

### R6: User-Facing Confidence

**Modify Maestro's system prompt:**

Add gap awareness confidence instructions:
- "When you're highly confident in your answer (verified by multiple Pointers, clear cross-references), say so naturally"
- "When you're uncertain (single source, Pointer not fully enriched, no cross-reference), flag it"
- "Use natural language, not scores: 'I'm confident about this — three details confirm it' vs 'I found one reference but you should double-check against the specs'"

**Frontend indicator:**
- Subtle confidence indicator on Maestro's response (e.g., green/yellow/orange dot)
- Based on: number of Pointers cited, enrichment_status of those Pointers, whether Maestro flagged gaps
- Not a precise score — a vibe indicator

### R7: Benchmark Dashboard (Minimal)

**Create admin endpoint:**

`GET /v3/admin/benchmark?project_id=...&days=30` → returns evolution report

For v1, this is consumed by:
- Developer looking at JSON
- Or a simple HTML page rendered by the backend

Full dashboard UI is future work. The data and API are what matter now.

## Constraints

- **Benchmark logging is write-only during normal flow** — never block Maestro or Learning to log benchmarks
- **Learning evaluation is still async** — Learning fills in benchmark scores at its own pace
- **Model comparison is offline** — not real-time. Run it manually when evaluating a model switch.
- **Emergent scoring means no hardcoded rubric** — trust Learning to discover what matters
- **User signals are inferred, not asked** — don't prompt the super "was this helpful?" Infer from their next message.

## File Map

```
NEW FILES:
  services/api/app/services/v3/benchmark.py
  services/api/app/services/v3/model_compare.py
  services/api/app/services/v3/benchmark_report.py
  services/api/alembic/versions/YYYYMMDD_benchmark_logs.py

MODIFIED FILES:
  services/api/app/services/v3/maestro_agent.py    (log benchmark after each turn)
  services/api/app/services/v3/learning_agent.py   (write scores to benchmark, emergent scoring prompt)
  services/api/app/types/learning.py               (add benchmark_id to InteractionPackage)
  services/api/app/routers/v3_sessions.py          (admin benchmark endpoint)
  services/api/app/config.py                       (benchmark_enabled setting)
```

## Environment

- **OS:** Windows 10 (dev), Linux (Railway production)
- **Python:** 3.11+
- **Backend:** FastAPI + SQLAlchemy + Supabase
- **Repo:** `C:\Users\Sean Schneidewent\Maestro-Super`
