# Phase 5: Telegram Mode

## Context

Read `maestro/MAESTRO-ARCHITECTURE-V3.md` — it is the alignment doc for the entire V3 architecture. This phase adds the mobile Telegram interface.

**Look at the Phase 1-4 commits to understand what was built.** Phase 4 delivered:
- Multi-workspace UX with Workspaces panel
- Workspace creation, switching, resumption
- Shared Experience across workspaces
- Full scrollable history with collapsed turns

**Current state:** Maestro works in the web app via workspace sessions. This phase adds a second channel: Telegram.

## Goal

1. **Telegram bot** — Maestro responds to Telegram messages as a conversational partner
2. **Telegram session** — Long-lived session with its own Maestro + Learning pair, same Knowledge + Experience
3. **Channel-aware system prompt** — Maestro knows it's on Telegram and adjusts its communication style
4. **Workspace awareness** — Telegram Maestro can see which workspaces exist and take actions in them
5. **Reset/Compact** — Superintendent controls their conversation via bot menu commands

## What This Phase Delivers

After this phase ships:
- Super texts Maestro on Telegram → gets intelligent, mobile-friendly responses
- Maestro knows it's on Telegram: short, direct responses suited for phone screens
- Super can ask about the plans, share schedule updates, make corrections — all via text
- Maestro can target workspaces remotely: "Go into my electrical workspace and pull up the panel details"
- Every Telegram interaction feeds Learning → Experience grows from the jobsite
- /reset gives a fresh conversation, /compact compresses older turns
- Same Maestro, same Knowledge, same Experience — just a different interface

## Detailed Requirements

### R1: Telegram Bot Setup

**Create `services/api/app/services/v3/telegram_bot.py`:**

Integration approach: Telegram Bot API webhook mode

1. Create a Telegram bot via BotFather (manual step, document instructions)
2. Set up webhook endpoint: `POST /v3/telegram/webhook`
3. Bot token stored in config: `TELEGRAM_BOT_TOKEN` env var
4. Webhook URL configured on deployment

**Bot commands (registered via BotFather):**
- `/reset` — fresh conversation, same brain
- `/compact` — compress older turns, keep the thread

### R2: Telegram Webhook Handler

**Create `services/api/app/routers/v3_telegram.py`:**

`POST /v3/telegram/webhook` — receives Telegram updates:

1. Parse the incoming message (text, chat_id, user info)
2. Identify the user (map Telegram user_id to Maestro user_id — needs a mapping table or convention)
3. Identify the project (for v1: each Telegram user is associated with one project, configurable)
4. Get or create the Telegram session: `session_manager.get_or_create_telegram_session(project_id, user_id, db)`
5. Handle commands:
   - `/reset` → `session_manager.reset_session(session_id, db)` → reply "Fresh start. What's on your mind?"
   - `/compact` → `session_manager.compact_session(session, db)` → reply "Conversation compacted. Ready."
6. Handle regular messages:
   - Call `run_maestro_turn(session, message_text, db)`
   - Collect the full response (don't stream — Telegram sends one message)
   - Send response back via Telegram Bot API: `POST https://api.telegram.org/bot{token}/sendMessage`

### R3: User/Project Mapping

**Create `services/api/app/models/telegram_user.py`:**

Simple mapping table:
```sql
CREATE TABLE telegram_users (
    telegram_user_id  BIGINT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    project_id        UUID REFERENCES projects(id),
    created_at        TIMESTAMPTZ DEFAULT now()
);
```

For v1: manually insert mappings. Future: self-service linking via the web app.

**Migration:** Add this table via Alembic migration.

### R4: Channel-Aware System Prompt

**Modify `services/api/app/services/v3/maestro_agent.py`:**

`build_maestro_system_prompt()` already accepts `session_type`. Implement the Telegram variant:

Telegram system prompt additions:
- "You're on Telegram. The superintendent is on the jobsite, phone in pocket."
- "Keep responses mobile-friendly: short paragraphs, no markdown tables, concise."
- "You have access to workspaces: [list from DB]. You can take actions in them remotely."
- "When the super shares schedule info, corrections, or field conditions — Learning handles it, but acknowledge what they told you."
- "Don't tell them to 'open the workspace' unless they need to see plans. Answer from Knowledge when you can."

### R5: Telegram Maestro Tools

Telegram Maestro gets a different tool set than workspace Maestro (already defined in Phase 2 alignment):

- `search_knowledge`, `read_pointer`, `read_experience`, `list_experience` — same as workspace
- `list_workspaces()` — `SELECT session_id, workspace_name, last_active_at FROM sessions WHERE project_id = ? AND session_type = 'workspace' AND status IN ('active', 'idle')`
- `workspace_action(workspace_id, action)` — takes an action in a specific workspace:
  - "add_pages" → add pages to that workspace
  - "highlight_pointers" → highlight Pointers in that workspace
  - The workspace session must be loaded/rehydrated to modify its state

When Maestro takes a workspace action, it should respond with something like: *"Done. I've pulled up the panel details in your Electrical workspace. Come into the workspace when you want to see them."*

### R6: Response Formatting

Telegram has different formatting constraints than the web workspace:
- Max message length: 4096 characters (split if longer)
- Markdown support: Telegram's MarkdownV2 (different from standard markdown)
- No tables — use bullet lists
- No code blocks for general content
- Bold, italic, links work

**Create `services/api/app/services/v3/telegram_formatter.py`:**

`format_for_telegram(response_text)` → `str`
- Convert standard markdown to Telegram MarkdownV2
- Replace tables with bullet lists
- Split into multiple messages if > 4000 chars
- Escape special characters per Telegram spec

### R7: Config

**Add to `services/api/app/config.py`:**
- `telegram_bot_token: str | None = None`
- `telegram_webhook_secret: str | None = None` (for webhook verification)
- `telegram_default_project_id: str | None = None` (v1 shortcut for single-project)

**Mount webhook router:**
- Add to `main.py`: mount `v3_telegram` router
- Only if `telegram_bot_token` is configured (skip if None)

### R8: Heartbeat Preparation

This phase sets up the Telegram session infrastructure that Phase 6 (Heartbeat) will use. The heartbeat will fire through the Telegram Maestro session — same conversation, same context window.

No heartbeat implementation in this phase — just ensure:
- The Telegram session is long-lived and persistent
- The SessionManager can retrieve the Telegram session for a user/project without an incoming message (for scheduled triggers)
- The `run_maestro_turn()` function can be called without a user message (Maestro initiates)

## Constraints

- **Do NOT modify workspace Maestro behavior** — Telegram is a parallel channel, not a replacement
- **Learning works the same way** — Telegram interactions feed Learning just like workspace interactions
- **Telegram session is one per user per project** — `get_or_create_telegram_session()` enforces this
- **v1 is simple** — manual user/project mapping, single project per Telegram user, no group chat support
- **No inline keyboards or complex Telegram UX** — just text messages and bot commands

## File Map

```
NEW FILES:
  services/api/app/routers/v3_telegram.py
  services/api/app/services/v3/telegram_bot.py
  services/api/app/services/v3/telegram_formatter.py
  services/api/app/models/telegram_user.py
  services/api/alembic/versions/YYYYMMDD_telegram_users.py

MODIFIED FILES:
  services/api/app/services/v3/maestro_agent.py    (Telegram system prompt + tool set)
  services/api/app/config.py                       (Telegram settings)
  services/api/app/main.py                         (mount Telegram router)
  services/api/app/models/__init__.py              (register TelegramUser model)
```

## Environment

- **OS:** Windows 10 (dev), Linux (Railway production)
- **Python:** 3.11+
- **Backend:** FastAPI + SQLAlchemy + Supabase
- **Telegram Bot API:** https://core.telegram.org/bots/api
- **Repo:** `C:\Users\Sean Schneidewent\Maestro-Super`
