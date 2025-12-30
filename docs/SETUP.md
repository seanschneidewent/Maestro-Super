# Maestro Super API - Complete Setup Guide

## Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend)
- Git
- Supabase account (free tier works)
- Railway account (free tier works)

---

## Part 1: Local Development

### 1.1 Clone and Setup Python Environment

```bash
cd services/api

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 1.2 Configure Environment

```bash
# Copy example env file
cp .env.example .env
```

Your `.env` should contain:
```bash
DATABASE_URL=sqlite:///./local.db
DEV_USER_ID=dev-user-00000000-0000-0000-0000-000000000001
```

### 1.3 Run Database Migrations

```bash
alembic upgrade head
```

This creates `local.db` with all tables.

### 1.4 Verify Setup

```bash
# Run tests (should see 64 passed)
pytest tests/ -v

# Start dev server
uvicorn app.main:app --reload --port 8000
```

Visit:
- http://localhost:8000/health - Should return `{"status": "healthy"}`
- http://localhost:8000/docs - Swagger UI

---

## Part 2: Supabase Setup (Production Database)

### 2.1 Create Supabase Project

1. Go to [supabase.com](https://supabase.com) → New Project
2. Choose a name and region (pick closest to Texas for your users)
3. Set a secure database password (save it!)
4. Wait for project to provision (~2 minutes)

### 2.2 Get Connection Details

From Supabase Dashboard → Settings → Database:

1. **Connection string** (under "Connection string" → URI):
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres
   ```

2. From Settings → API:
   - **Project URL**: `https://[PROJECT-REF].supabase.co`
   - **anon public key**: For frontend
   - **JWT Secret**: For backend auth validation (under "JWT Settings")

### 2.3 Run Migrations on Supabase

```bash
cd services/api
source venv/bin/activate

# Set production database URL
export DATABASE_URL="postgresql://postgres:[PASSWORD]@db.[PROJECT].supabase.co:5432/postgres"

# Run migrations
alembic upgrade head
```

### 2.4 Verify Tables in Supabase

Go to Supabase Dashboard → SQL Editor, run:

```sql
-- Check all tables exist
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;
```

Expected tables:
- `alembic_version`
- `context_pointers`
- `discipline_contexts`
- `page_contexts`
- `project_files`
- `projects`
- `queries`
- `usage_events`

### 2.5 Enable Row Level Security (RLS)

Run in SQL Editor:

```sql
-- Enable RLS on all tables
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE context_pointers ENABLE ROW LEVEL SECURITY;
ALTER TABLE page_contexts ENABLE ROW LEVEL SECURITY;
ALTER TABLE discipline_contexts ENABLE ROW LEVEL SECURITY;
ALTER TABLE queries ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;

-- Create policies for projects (direct user_id access)
CREATE POLICY "Users can view own projects" ON projects
  FOR SELECT USING (auth.uid()::text = user_id);

CREATE POLICY "Users can insert own projects" ON projects
  FOR INSERT WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "Users can update own projects" ON projects
  FOR UPDATE USING (auth.uid()::text = user_id);

CREATE POLICY "Users can delete own projects" ON projects
  FOR DELETE USING (auth.uid()::text = user_id);

-- Create policies for project_files (via project ownership)
CREATE POLICY "Users can access own project files" ON project_files
  FOR ALL USING (
    project_id IN (SELECT id FROM projects WHERE user_id = auth.uid()::text)
  );

-- Create policies for context_pointers (via file → project ownership)
CREATE POLICY "Users can access own pointers" ON context_pointers
  FOR ALL USING (
    file_id IN (
      SELECT pf.id FROM project_files pf
      JOIN projects p ON pf.project_id = p.id
      WHERE p.user_id = auth.uid()::text
    )
  );

-- Create policies for page_contexts (via file → project ownership)
CREATE POLICY "Users can access own page contexts" ON page_contexts
  FOR ALL USING (
    file_id IN (
      SELECT pf.id FROM project_files pf
      JOIN projects p ON pf.project_id = p.id
      WHERE p.user_id = auth.uid()::text
    )
  );

-- Create policies for discipline_contexts (via project ownership)
CREATE POLICY "Users can access own discipline contexts" ON discipline_contexts
  FOR ALL USING (
    project_id IN (SELECT id FROM projects WHERE user_id = auth.uid()::text)
  );

-- Create policies for queries (direct user_id access)
CREATE POLICY "Users can access own queries" ON queries
  FOR ALL USING (auth.uid()::text = user_id);

-- Create policies for usage_events (direct user_id access)
CREATE POLICY "Users can access own usage events" ON usage_events
  FOR ALL USING (auth.uid()::text = user_id);
```

### 2.6 Verify RLS Policies

```sql
-- Check policies exist
SELECT tablename, policyname, cmd
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename;
```

---

## Part 3: Railway Deployment

### 3.1 Connect Repository

1. Go to [railway.app](https://railway.app) → New Project
2. "Deploy from GitHub repo"
3. Select your Maestro-Super repository
4. Set **Root Directory** to `services/api`

### 3.2 Set Environment Variables

In Railway Dashboard → Variables, add:

| Variable | Value |
|----------|-------|
| `DATABASE_URL` | `postgresql://postgres:[PASSWORD]@db.[PROJECT].supabase.co:5432/postgres` |
| `SUPABASE_URL` | `https://[PROJECT].supabase.co` |
| `SUPABASE_JWT_SECRET` | (from Supabase → Settings → API → JWT Secret) |
| `FRONTEND_URL` | `https://your-app.vercel.app` (add after Vercel deploy) |

### 3.3 Deploy

Railway auto-deploys on push to main. Manual deploy:
- Railway Dashboard → Deployments → Deploy

### 3.4 Get Your API URL

After deploy, Railway Dashboard → Settings → Domains:
- Generate domain or add custom domain
- Note the URL (e.g., `https://maestro-api-production.up.railway.app`)

### 3.5 Verify Deployment

```bash
cd services/api
source venv/bin/activate

python scripts/verify_deployment.py https://your-railway-url.up.railway.app
```

Expected output:
```
Verifying deployment at: https://your-railway-url.up.railway.app

✓ Health check passed
✓ Auth required for protected routes
✓ API docs accessible
✓ OpenAPI schema accessible

✅ All checks passed!
```

---

## Part 4: Frontend Setup

### 4.1 Install Dependencies

```bash
cd apps/web
pnpm install
```

### 4.2 Configure Environment

Create `apps/web/.env.local` for local dev:
```bash
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://[PROJECT].supabase.co
VITE_SUPABASE_ANON_KEY=[anon-key-from-supabase]
```

Create `apps/web/.env.production` for production:
```bash
VITE_API_URL=https://your-railway-url.up.railway.app
VITE_SUPABASE_URL=https://[PROJECT].supabase.co
VITE_SUPABASE_ANON_KEY=[anon-key-from-supabase]
```

### 4.3 Run Frontend Locally

```bash
pnpm dev
```

Visit http://localhost:5173

### 4.4 Deploy to Vercel

1. Go to [vercel.com](https://vercel.com) → New Project
2. Import your GitHub repo
3. Set **Root Directory** to `apps/web`
4. Add environment variables:
   - `VITE_API_URL` = your Railway URL
   - `VITE_SUPABASE_URL` = your Supabase project URL
   - `VITE_SUPABASE_ANON_KEY` = your Supabase anon key
5. Deploy

### 4.5 Update Railway CORS

After Vercel deploys, go back to Railway and update:
```
FRONTEND_URL=https://your-app.vercel.app
```

---

## Part 5: Supabase Auth Setup

### 5.1 Enable Google OAuth

1. Supabase Dashboard → Authentication → Providers
2. Enable Google
3. Get OAuth credentials from [Google Cloud Console](https://console.cloud.google.com/):
   - Create OAuth 2.0 Client ID
   - Authorized redirect URI: `https://[PROJECT].supabase.co/auth/v1/callback`
4. Add Client ID and Secret to Supabase

### 5.2 Configure Auth Settings

Supabase Dashboard → Authentication → URL Configuration:
- **Site URL**: `https://your-app.vercel.app`
- **Redirect URLs**: Add `http://localhost:5173` for local dev

---

## Quick Reference

### Environment Variables Summary

**Backend (Railway):**
```bash
DATABASE_URL=postgresql://postgres:xxx@db.xxx.supabase.co:5432/postgres
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_JWT_SECRET=xxx
FRONTEND_URL=https://xxx.vercel.app
```

**Frontend (Vercel):**
```bash
VITE_API_URL=https://xxx.up.railway.app
VITE_SUPABASE_URL=https://xxx.supabase.co
VITE_SUPABASE_ANON_KEY=xxx
```

### Useful Commands

```bash
# Backend
cd services/api
source venv/bin/activate
pytest tests/ -v              # Run tests
uvicorn app.main:app --reload # Dev server
alembic upgrade head          # Run migrations
alembic revision -m "msg"     # Create migration

# Frontend
cd apps/web
pnpm dev                      # Dev server
pnpm build                    # Production build
```

### URLs After Setup

| Service | Local | Production |
|---------|-------|------------|
| API | http://localhost:8000 | https://xxx.up.railway.app |
| API Docs | http://localhost:8000/docs | https://xxx.up.railway.app/docs |
| Frontend | http://localhost:5173 | https://xxx.vercel.app |
| Supabase | - | https://xxx.supabase.co |
