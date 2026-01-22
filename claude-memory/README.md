# Claude Memory System

Universal memory layer for Claude across all interfaces — Claude Code, Cowork, SMS, claude.ai.

## Setup (New Machine)

### Option A: MCP Server (Recommended for Claude Code)

1. Install the MCP server dependencies:
```bash
cd claude-memory/mcp-server
npm install
```

2. The `.mcp.json` in the project root is already configured. Claude Code will automatically load the server.

3. In Claude Code, use the `sync_memory` tool at the start of each session.

### Option B: Shell Scripts (Fallback)

1. Configure environment:
```bash
cp .env.example .env
# Edit .env with your Supabase credentials
```

2. Make scripts executable:
```bash
chmod +x scripts/*.sh
```

3. Sync memory:
```bash
./scripts/sync-memory.sh
```

## Usage

### With MCP Server (Claude Code)

The MCP server provides these tools:

- **sync_memory** - Fetch full context from Supabase (call at session start)
- **write_decision** - Log a decision with domain, decision, and rationale
- **log_session** - Log a session summary at the end of work
- **update_current_edge** - Update what you're working on and next step

### With Shell Scripts

**Start of any Claude Code or Cowork session:**
```bash
./scripts/sync-memory.sh && cat CONTEXT.md
```

**Log a decision:**
```bash
./scripts/write-decision.sh "technical" "Decision here" "Rationale here"
```

**End of session — log what happened:**
```bash
./scripts/log-session.sh '{"interface":"claude_code","project":"PROJECT","summary":"...","what_got_built":"...","problems_solved":"...","key_decisions":"...","open_threads":"...","next_session_hint":"..."}'
```

## Architecture

- **Supabase** — Postgres database, REST API
- **CONTEXT.md** — Generated file, pulled fresh each session
- **Blood & Electricity** — The covenant, stored in DB and synced

## Supabase Credentials

```
SUPABASE_URL=https://eecdkjulosomiuqxgtbq.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVlY2RranVsb3NvbWl1cXhndGJxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njg1MDkwMTMsImV4cCI6MjA4NDA4NTAxM30.J_MME3SkJFSKYn9B9elgbiFxJs_Xd8lm8Ee2b6RKCtU
```

**REST API endpoint pattern:**
```
${SUPABASE_URL}/rest/v1/{table_name}
```

**Key tables:**
- `implementation_plans` — project, phase_number, phase_name, status, content
- `conversations` — session_date, interface, project, summary, next_session_hint
- `current_edge` — project, what_shipping_looks_like, specific_next_step
- `identity`, `operating_principles`, `decisions`, `relationships`, `covenant`, `product_vision`, `projects`

## Signal Phrases

- **"Blood check"** — Pause. Reconnect to values.
- **"Electricity on"** — Speed mode. Execute.
- **"Slow mode"** — More grounding, reversibility, risk clarity.
- **"No steering"** — Neutral framing. Surface options.
- **"Hard truth"** — Direct. No cushioning.
```

---

**.env.example**
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
```

---

**.gitignore**
```
.env
CONTEXT.md
.DS_Store
