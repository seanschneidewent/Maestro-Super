# Phase 6: Heartbeat System

## Context

Read `maestro/MAESTRO-ARCHITECTURE-V3.md` — it is the alignment doc for the entire V3 architecture. This phase implements the proactive flip.

**Look at the Phase 1-5 commits to understand what was built.** Phase 5 delivered:
- Telegram bot integration with webhook
- Telegram Maestro session (long-lived, own Maestro + Learning pair)
- Channel-aware system prompt
- Workspace awareness from Telegram
- Reset/Compact commands

**Current state:** Maestro responds when the super talks to it. This phase makes Maestro initiate.

## Goal

1. **Heartbeat scheduling** — Configurable schedule for Maestro to take its own turn
2. **Runs through Telegram Maestro** — Same conversation, same context window. Not a cold start.
3. **Cross-references Schedule × Knowledge × Experience** — Three data inputs converge
4. **Two modes: Telling and Asking** — Proactive insights + calculated scheduling questions
5. **The Flywheel** — Super's response feeds Learning → better Experience → smarter heartbeats

## What This Phase Delivers

After this phase ships:
- Maestro texts the super unprompted with proactive insights and scheduling questions
- Heartbeats are grounded in Knowledge (the plans), shaped by Experience (what Maestro has learned)
- "Canopy footing pour today — the structural detail shows 6 anchor bolts but the equipment schedule only calls out 4 attachment points."
- "Once the addition footings are poured, are you going right into the slab or do the walls go up first?"
- Every heartbeat response feeds Learning → Experience grows → next heartbeat is smarter
- Schedule: configurable timing (e.g., morning briefing 6:30 AM, midday check-in 12:00 PM)

## Architecture Reference

See the V3 alignment doc sections:
- **"Heartbeat System — The Proactive Flip"** — full design
- **"Three Data Inputs"** — Knowledge × Schedule × Experience
- **"The Schedule Lives in the Super's Head"** — schedule.md in Experience
- **"Two Types of Heartbeat: Telling and Asking"** — with examples
- **"The Heartbeat Data Loop"** — Read → Cross-reference → Generate → Send → Learn

## Detailed Requirements

### R1: Heartbeat Scheduler

**Create `services/api/app/services/v3/heartbeat.py`:**

The heartbeat is NOT a separate agent. It's a Maestro turn where Maestro initiates instead of the super.

`run_heartbeat(session_manager, db)`:
1. Find all active Telegram sessions
2. For each: trigger a heartbeat turn

`trigger_heartbeat_turn(session, db)`:
1. Build a special "heartbeat" user message that tells Maestro to take a proactive turn:
   ```
   [HEARTBEAT TRIGGER - This is your scheduled check-in. You are initiating this conversation.
   Read schedule.md and your Experience. Cross-reference with Knowledge (the plans).
   Choose ONE of two modes:
   - TELL: Share a proactive insight (upcoming activity × plan detail = actionable info)
   - ASK: Ask a calculated scheduling question that fills a gap in your understanding
   Your message goes directly to the superintendent via Telegram. Be concise and valuable.]
   ```
2. Call `run_maestro_turn(session, heartbeat_message, db)` — same function as regular queries
3. Collect response (non-streaming for Telegram)
4. Send via Telegram Bot API
5. The heartbeat message and response become part of the Telegram conversation (full context)
6. Learning processes the heartbeat interaction like any other turn

**The heartbeat IS a conversation turn.** It uses Maestro's tools (search_knowledge, read_experience, etc.) to ground its message. It appears in the Telegram conversation history. The super's response feeds back normally.

### R2: Scheduling

**Approach: APScheduler or simple asyncio timer**

For v1, use a simple approach:
- Server startup: launch `run_heartbeat_scheduler()` as background task
- Configuration: list of `(hour, minute)` pairs for daily heartbeat times
- Each tick: check if current time matches a schedule → trigger heartbeats for all active Telegram sessions
- Respect timezone (use the super's timezone, stored in config)

**Config in `services/api/app/config.py`:**
```python
heartbeat_enabled: bool = False
heartbeat_schedule: str = "06:30,12:00"    # comma-separated HH:MM
heartbeat_timezone: str = "America/Chicago"
```

**Advanced (future):** Per-project schedules, adaptive timing based on super's activity patterns, quiet hours detection.

### R3: Heartbeat System Prompt Enhancement

**Modify `build_maestro_system_prompt()` in `maestro_agent.py`:**

When the trigger is a heartbeat (detected by prefix `[HEARTBEAT TRIGGER`):
- Add heartbeat-specific instructions to the system prompt:
  - "This is your scheduled proactive turn. The superintendent did NOT message you."
  - "Your options: share a proactive insight (TELL) or ask a calculated scheduling question (ASK)"
  - "Ground everything in Knowledge (use search_knowledge tool) and Experience (read schedule.md)"
  - "Be concise. One insight or one question per heartbeat. Not both."
  - "If you have nothing valuable to share, say so briefly: 'All clear on my end. Let me know if anything changes.'"
  - "Never repeat a question you already asked (check your conversation history)"

### R4: Heartbeat Quality Signals

The heartbeat's quality depends on:
1. **Rich Knowledge** — Pass 2 enriched Pointers with cross-references (Phase 1)
2. **Schedule data** — `schedule.md` in Experience (populated by Learning from conversations)
3. **Accumulated Experience** — corrections, routing rules, preferences (built over time by Learning)

If Experience is thin (new project, few conversations), heartbeats should be lighter:
- Ask broad scheduling questions to build up the schedule
- "What phase are you in right now?" → builds initial schedule.md
- "Any active pours or inspections this week?" → concrete data to cross-reference

As Experience grows, heartbeats get more specific and valuable.

### R5: Heartbeat Message Formatting

Heartbeat messages should feel natural in the Telegram conversation — not like automated alerts.

Good:
- "Morning — canopy footing pour today. Quick heads up: the structural detail shows 6 anchor bolts but the equipment schedule only calls out 4 attachment points. Worth a double-check before the pour."
- "Hey — once the addition footings are done, are you going right into the slab or are the walls going up first? Trying to figure out if the conduit stubs need to be in before the next pour."

Bad:
- "HEARTBEAT ALERT: Schedule conflict detected between structural and mechanical details."
- "[Automated check-in] Here are 5 items to review today: ..."

**The heartbeat should read like a text from a knowledgeable colleague, not a notification from software.**

### R6: Heartbeat Learning

Learning processes heartbeat interactions the same way it processes regular interactions:
- Maestro's heartbeat message → what Maestro chose to share (what it thinks matters)
- Super's response → new information (schedule updates, confirmations, corrections)
- If super doesn't respond → that's a signal too (maybe the heartbeat wasn't relevant)
- If super responds with detail → high-value data, Learning should capture it in Experience

No special Learning logic needed — the existing Learning agent handles this. But the InteractionPackage should indicate it was a heartbeat turn (add `is_heartbeat: bool` field) so Learning can learn meta-patterns about which heartbeats generate responses.

### R7: Heartbeat Monitoring

**Logging:**
- Log each heartbeat trigger: timestamp, session_id, project_id
- Log the heartbeat message Maestro generated
- Log whether the super responded (within configurable window, e.g., 4 hours)
- Store in a simple `heartbeat_log` table or just application logs for v1

## Constraints

- **The heartbeat IS a Maestro turn** — not a separate agent, not a separate system. Same `run_maestro_turn()` function.
- **Same conversation, same context** — the heartbeat happens in the ongoing Telegram thread. Maestro has full context.
- **One insight or one question per heartbeat** — not a wall of text. Brief, valuable, actionable.
- **Quiet hours** — don't heartbeat before 6 AM or after 9 PM in the super's timezone (configurable)
- **Simple scheduling for v1** — fixed daily times. Adaptive scheduling is future work.

## File Map

```
NEW FILES:
  services/api/app/services/v3/heartbeat.py

MODIFIED FILES:
  services/api/app/services/v3/maestro_agent.py   (heartbeat system prompt enhancement)
  services/api/app/types/learning.py               (add is_heartbeat to InteractionPackage)
  services/api/app/config.py                       (heartbeat settings)
  services/api/app/main.py                         (launch heartbeat scheduler)
```

## Environment

- **OS:** Windows 10 (dev), Linux (Railway production)
- **Python:** 3.11+
- **Backend:** FastAPI + SQLAlchemy + Supabase
- **Telegram Bot API:** https://core.telegram.org/bots/api
- **Repo:** `C:\Users\Sean Schneidewent\Maestro-Super`
