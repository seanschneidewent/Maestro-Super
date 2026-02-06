# V3 Frontend Wiring Proposal

*For Sean to review when he wakes up. NO code changes until discussed.*

---

## Current State

| Layer | Status | Details |
|-------|--------|---------|
| **Frontend** | Old UI restored | Brain/Maestro toggle, familiar layout, calls `/query` |
| **Backend** | V3 active | Sessions, Learning, Experience, but `/query` endpoint deleted |
| **Result** | UI loads, queries fail | Need to wire old frontend → V3 backend |

---

## The Core Question

The old frontend calls:
```
POST /api/projects/{id}/query
```

V3 backend expects:
```
POST /api/v3/sessions/{session_id}/query
```

**The difference:** V3 needs a session. The old frontend doesn't know about sessions.

---

## Option A: Thin Adapter (Recommended)

**Add back the `/query` endpoint as a wrapper around V3 sessions.**

```python
# In routers/queries.py (restore this file)

@router.post("/projects/{project_id}/query")
async def query_adapter(project_id: str, request: QueryRequest):
    """
    Adapter: old frontend → V3 backend.
    
    1. Get or create a default session for this project/user
    2. Forward the query to V3 session endpoint
    3. Return response in old format
    """
    session = await session_manager.get_or_create_default_session(
        project_id=project_id,
        user_id=current_user.id,
        session_type="workspace"
    )
    
    # Forward to V3
    return await run_maestro_turn(session, request.query)
```

**Pros:**
- Zero frontend changes
- Old UI works immediately
- V3 backend benefits (Learning, Experience) happen invisibly
- Can add V3 UI features incrementally later

**Cons:**
- Hides sessions from user (they exist but user doesn't see them)
- No workspace switching (just one default session per project)

**Effort:** ~30 min

---

## Option B: Minimal Frontend Changes

**Keep old UI, add session awareness to useQueryManager.**

1. On app load: create/resume a session via `/v3/sessions`
2. Store `sessionId` in state
3. Change query calls from `/query` to `/v3/sessions/{id}/query`
4. Everything else stays the same

**Pros:**
- Sessions are real and visible (in console/network tab at least)
- Clean architecture (no adapter layer)
- Foundation for adding Workspaces panel later

**Cons:**
- Requires frontend changes (~100 lines in useQueryManager)
- Need to handle session lifecycle (what if session expires?)

**Effort:** ~2 hours

---

## Option C: Selective V3 Features

**Keep old UI, cherry-pick specific V3 features.**

After Option A or B is working:

1. **ThinkingSection panels** — Add Learning (yellow) and Knowledge Update (purple) panels. SSE events already have `panel` field. ~1 hour.

2. **Experience visibility** — Show what Learning is writing. New component, reads from Experience API. ~2 hours.

3. **Workspaces panel** — Add as collapsible sidebar, not replacement. User can ignore it or use it. ~3 hours.

4. **Pass 2 status** — Show enrichment progress in Brain Mode. Pointers show "enriching..." badge until complete. ~1 hour.

---

## My Recommendation

1. **Start with Option A** — Get queries working again with zero frontend changes. 30 min.

2. **Then discuss** which V3 features you actually want visible in the UI.

3. **Add features one at a time** — Each as a separate small PR. You review each before it lands.

This way:
- You have a working app immediately
- V3 backend benefits are active (Learning happens on every query)
- UI changes are incremental and reversible
- You control what gets added

---

## What V3 Backend Is Already Doing (Even With Old UI)

Once we wire queries through V3 sessions:

| Feature | What Happens | Visible to User? |
|---------|--------------|------------------|
| **Sessions** | Conversation persists across queries | No (hidden) |
| **Learning** | Every interaction analyzed, Experience updated | No (backend only) |
| **Experience** | Routing rules, corrections, preferences accumulated | No (shapes future responses) |
| **Pass 2** | Pointers enriched in background after upload | No (richer search results) |
| **Benchmark** | Every query logged with quality metrics | No (admin only) |

The intelligence layer is working. The UI just doesn't show it yet.

---

## Questions for Sean

1. **Option A (adapter) or Option B (frontend changes)?**

2. **Which V3 features do you want visible in the UI?**
   - [ ] Three-panel ThinkingSection (Learning + Knowledge Update)
   - [ ] Experience viewer (see what Maestro learned)
   - [ ] Workspaces panel (multiple named sessions)
   - [ ] Pass 2 enrichment status in Brain Mode
   - [ ] None yet — just make queries work

3. **Telegram bot — still want it?** Backend is ready, just needs BotFather registration.

4. **Heartbeat — still want it?** Backend is ready, just needs Telegram bot first.

---

*Written 2026-02-06 ~00:35 CST while Sean sleeps. Ready to discuss whenever.*
