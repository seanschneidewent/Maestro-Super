# Claude Memory System

Universal memory layer for Claude across all interfaces — Claude Code, Cowork, SMS, claude.ai.

## Database Credentials

```
SUPABASE_URL=https://eecdkjulosomiuqxgtbq.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVlY2RranVsb3NvbWl1cXhndGJxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njg1MDkwMTMsImV4cCI6MjA4NDA4NTAxM30.J_MME3SkJFSKYn9B9elgbiFxJs_Xd8lm8Ee2b6RKCtU
```

## Setup (New Machine)

1. Clone the repo:
```bash
git clone https://github.com/YOUR_USERNAME/claude-memory.git
cd claude-memory
```

2. Configure environment:
```bash
cp .env.example .env
# Edit .env with your Supabase credentials
```

3. Make scripts executable:
```bash
chmod +x scripts/*.sh
```

4. Sync memory:
```bash
./scripts/sync-memory.sh
```

## Usage

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
