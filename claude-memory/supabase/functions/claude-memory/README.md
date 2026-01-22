# Claude Memory Edge Function

Supabase Edge Function that provides authenticated access to Claude's memory tables without requiring client-side auth headers.

## Deployment

```bash
# Install Supabase CLI if needed
npm install -g supabase

# Login to Supabase
supabase login

# Link to your project
supabase link --project-ref eecdkjulosomiuqxgtbq

# Deploy the function
supabase functions deploy claude-memory --no-verify-jwt
```

The `--no-verify-jwt` flag allows the function to be called without authentication (the function uses the service role key internally).

## Endpoints

Base URL: `https://eecdkjulosomiuqxgtbq.supabase.co/functions/v1/claude-memory`

### Sync Memory (GET)
```
GET ?action=sync
```
Returns all memory context as JSON.

### Write Decision (POST)
```
POST ?action=write_decision
Content-Type: application/json

{
  "domain": "technical",
  "decision": "Use Edge Functions for sandbox access",
  "rationale": "WebFetch can call them without custom headers"
}
```

### Log Session (POST)
```
POST ?action=log_session
Content-Type: application/json

{
  "project": "Maestro Super",
  "summary": "Built edge function for memory sync",
  "interface": "claude_code",
  "what_got_built": "Edge function with sync/write endpoints",
  "next_session_hint": "Test the edge function from sandbox"
}
```

### Update Current Edge (POST)
```
POST ?action=update_edge
Content-Type: application/json

{
  "project": "Maestro Super",
  "what_shipping_looks_like": "Working memory sync from any Claude interface",
  "specific_next_step": "Deploy and test edge function",
  "what_feels_like_exposure": "Public endpoint without auth"
}
```

## Security Notes

- Function uses `SUPABASE_SERVICE_ROLE_KEY` internally (set automatically by Supabase)
- Endpoint is public (no JWT verification) - anyone with the URL can read/write
- Consider adding a simple secret token check if this becomes a concern
