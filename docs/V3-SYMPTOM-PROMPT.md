# V3 Symptom Prompt — 2026-02-07

*For Codex/Claude Code. Captures all issues from Feb 6-7 night session.*

---

## Context

Maestro V3 was wired up on Feb 6. Frontend migrated to V3 sessions. Multiple issues surfaced during testing that caused stream failures, silent errors, and build failures.

**Architecture:** `docs/v3/MAESTRO-ARCHITECTURE-V3.md` is the north star.

**Recent commits (newest → oldest):**
```
d01b2bd Fix Gemini tool-call replay stream interruptions
61b1783 Make V3 search_knowledge resilient to hybrid search failures
07811c4 Fix V3 query SSE reliability and surface stream failures
0a1abb7 maestro: always create fresh workspace session on app load
8f81f59 Stabilize V3 tool payloads for Gemini and add search fallback
9366417 Fix Gemini function response payload for list tool outputs
4741696 Merge branch 'old-ui-wire-v3' into main
```

---

## Issue 1: Build Failure — Settings Validation

**Symptom:** Railway build fails with:
```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
maestro_orchestrator
  Extra inputs are not permitted [type=extra_forbidden, input_value='true', input_type=str]
```

**Root cause:** `.env.local` has `MAESTRO_ORCHESTRATOR=true` but `services/api/app/config.py` Settings class doesn't define this field. Pydantic `extra='forbid'` rejects unknown env vars.

**Fix:** Add to Settings class in `config.py`:
```python
maestro_orchestrator: bool = False
```

**Or:** Remove `MAESTRO_ORCHESTRATOR` from `.env.local` since V3 doesn't use the orchestrator pattern anymore (per V3 architecture doc, `big_maestro.py` orchestrator is gone).

---

## Issue 2: Gemini Tool-Call Replay Breaks Stream

**Symptom:** When Gemini makes a tool call, gets the result, and continues reasoning, the stream sometimes dies silently. The frontend shows partial response then stops.

**Root cause:** Gemini's `thought_signature` field must be preserved and replayed when sending tool results back. Without it, Gemini loses track of the conversation state and the stream breaks.

**Fixed in:** `d01b2bd`

**Key changes:**
- `providers.py` — Capture `thought_signature` from `part.thought_signature` in Gemini response
- `providers.py` — Replay `thought_signature` in `types.Part()` when building tool-call history
- `maestro_agent.py` / `learning_agent.py` — Pass `thought_signature` through tool_call events

**Code pattern:**
```python
# Capture from response
"thought_signature": part.thought_signature,

# Replay in history
types.Part(
    function_call=types.FunctionCall(...),
    thought_signature=bytes(thought_signature) if thought_signature else None,
)
```

---

## Issue 3: Hybrid Search Failures Kill Queries

**Symptom:** `search_knowledge` tool fails when vector search returns no results or errors, killing the entire query.

**Root cause:** `search_pointers()` in `utils/search.py` uses hybrid search (vector + keyword). When vector embeddings are missing or search fails, no fallback exists.

**Fixed in:** `8f81f59`, `61b1783`

**Key changes:**
- `tool_executor.py` — Add `_fallback_search_pointers()` that does pure SQL ILIKE search on pointer titles/descriptions
- `maestro_agent.py` — `_search_knowledge_items()` helper handles both `{"results": [...]}` and `[...]` formats
- Graceful degradation: vector search → fallback SQL search → empty results (never throw)

---

## Issue 4: Gemini Rejects List Tool Results

**Symptom:** Gemini throws error when tool result is a raw list `[{...}, {...}]`.

**Root cause:** Gemini's `Part.from_function_response()` expects a dict, not a list.

**Fixed in:** `9366417`, `8f81f59`

**Key change in `providers.py`:**
```python
response_payload = parsed if isinstance(parsed, dict) else {"results": parsed}
types.Part.from_function_response(name=tool_name, response=response_payload)
```

---

## Issue 5: SSE Stream Failures Silent

**Symptom:** Frontend shows "thinking" forever when backend stream dies. No error surfaced.

**Fixed in:** `07811c4`

**Key changes:**
- `v3_sessions.py` — Wrap stream in try/catch, yield `{"type": "error", ...}` on exception
- `useQueryManager.ts` — Handle `error` event type, surface to UI
- Added `test_v3_sessions_stream.py` for regression testing

---

## Issue 6: Stale Session State

**Symptom:** Opening app shows old conversation from previous session instead of fresh workspace.

**Fixed in:** `0a1abb7`

**Key change:** Frontend always creates fresh workspace session on app load instead of resuming last session.

---

## Issue 7: Sample Query Leakage

**Symptom:** Model outputs `walk-in cooler` searches even when user asked about something else. Training data leakage into live queries.

**Fixed in:** `d01b2bd`

**Key change in `maestro_agent.py`:**
```python
def _normalize_search_query(tool_args: Any, user_message: str) -> str:
    # Guard against known sample-query leakage
    if query_tokens in (["walk", "in", "cooler"], ["walk", "cooler"]):
        if "walk" not in user_lower and "cooler" not in user_lower:
            return user_text  # Use actual user message instead
    return raw_query
```

---

## Files Involved

**Backend (`services/api/app/`):**
- `config.py` — Settings class (Issue 1)
- `services/v3/providers.py` — Gemini message building + thought_signature (Issues 2, 4)
- `services/v3/maestro_agent.py` — Tool call handling, query normalization (Issues 2, 3, 7)
- `services/v3/learning_agent.py` — Tool call handling (Issue 2)
- `services/v3/tool_executor.py` — search_knowledge implementation + fallback (Issue 3)
- `routers/v3_sessions.py` — SSE streaming error handling (Issue 5)

**Frontend (`apps/web/src/`):**
- `hooks/useQueryManager.ts` — SSE event handling, error surfacing (Issue 5)
- `components/maestro/MaestroMode.tsx` — Session initialization (Issue 6)

**Tests:**
- `tests/test_v3_sessions_stream.py` — SSE reliability tests
- `tests/test_v3_tool_results.py` — Tool payload format tests

---

## Remaining Work

1. **Add `maestro_orchestrator: bool = False` to Settings** — or remove from .env.local
2. **Verify thought_signature round-trip** — needs integration test with real Gemini call
3. **Test fallback search** — verify SQL fallback triggers when vector search fails
4. **Monitor stream reliability** — log when streams die unexpectedly

---

## How to Test

```bash
cd services/api

# Run specific test files
python -m pytest tests/test_v3_tool_results.py -v
python -m pytest tests/test_v3_sessions_stream.py -v

# Test the full query flow (requires local Postgres + .env.local)
# 1. Start backend: uvicorn app.main:app --reload
# 2. Open frontend: cd apps/web && npm run dev
# 3. Upload a PDF, ask a question, verify stream completes
```

---

*Generated by Ember from Feb 6-7 commit history analysis.*
