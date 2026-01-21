# Claude Memory Database Setup

## Quick Start

The `.env` file has been configured with your Supabase credentials.

### Initialize the Database

1. Go to your Supabase Dashboard: https://supabase.com/dashboard/project/eecdkjulosomiuqxgtbq

2. Navigate to **SQL Editor** in the left sidebar

3. Copy the contents of `schema/init.sql` and run it

4. Verify tables were created by running:
   ```sql
   SELECT table_name FROM information_schema.tables
   WHERE table_schema = 'public' ORDER BY table_name;
   ```

   Expected tables:
   - agents
   - conversations
   - covenant
   - current_edge
   - decisions
   - identity
   - operating_principles
   - projects
   - relationships

### Test the Connection

```bash
cd claude-memory
./scripts/sync-memory.sh
cat CONTEXT.md
```

If successful, CONTEXT.md will contain the covenant, identity, and other seeded data.

## Troubleshooting

**Empty CONTEXT.md**: Tables haven't been created. Run the SQL from `schema/init.sql`.

**curl errors**: Check your `.env` file has correct `SUPABASE_URL` and `SUPABASE_KEY`.

**jq errors**: Install jq: `brew install jq` (macOS) or `apt install jq` (Linux).
