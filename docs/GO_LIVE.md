# Go Live Checklist

When you're done developing locally and ready to deploy to production.

---

## Step 1: Set Up Google OAuth

### 1.1 Create Google OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Go to **APIs & Services** → **Credentials**
4. Click **Create Credentials** → **OAuth Client ID**
5. If prompted, configure the OAuth consent screen first:
   - User Type: External
   - App name: Maestro Super
   - User support email: your email
   - Developer contact: your email
   - Save and continue through scopes (no changes needed)
6. Back to Credentials → **Create OAuth Client ID**:
   - Application type: **Web application**
   - Name: Maestro Super
   - Authorized redirect URIs: `https://ybyqobdyvbmsiehdmxwp.supabase.co/auth/v1/callback`
7. Copy the **Client ID** and **Client Secret**

### 1.2 Configure Supabase

1. Go to [Supabase Dashboard](https://supabase.com/dashboard/project/ybyqobdyvbmsiehdmxwp)
2. **Authentication** → **Providers** → **Google**
3. Toggle **Enable Sign in with Google**
4. Paste your Google Client ID and Client Secret
5. Click **Save**

### 1.3 Configure Auth URLs

1. **Authentication** → **URL Configuration**
2. Set **Site URL**: `https://your-app.vercel.app` (update after Vercel deploy)
3. Add to **Redirect URLs**:
   - `http://localhost:3000`
   - `http://localhost:3001`
   - `http://localhost:5173`
   - `https://your-app.vercel.app` (update after Vercel deploy)

---

## Step 2: Deploy Frontend to Vercel

### 2.1 Connect Repository

1. Go to [vercel.com](https://vercel.com) → **Add New Project**
2. **Import** your `Maestro-Super` GitHub repo
3. Set **Root Directory** to `apps/web`
4. Framework Preset should auto-detect as **Vite**

### 2.2 Set Environment Variables

Add these in the Vercel project settings:

| Variable | Value |
|----------|-------|
| `VITE_API_URL` | `https://maestro-super-production.up.railway.app` |
| `VITE_SUPABASE_URL` | `https://ybyqobdyvbmsiehdmxwp.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlieXFvYmR5dmJtc2llaGRteHdwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjcxMTk0OTksImV4cCI6MjA4MjY5NTQ5OX0.8X0uDQapH__wQ3ilH2s627E75DRS15xM8zAiCWi3QW0` |

### 2.3 Deploy

Click **Deploy** and wait for it to complete. Note your Vercel URL.

---

## Step 3: Update Railway CORS

1. Go to [Railway Dashboard](https://railway.app) → your project
2. Click on the API service → **Variables**
3. Add:
   ```
   FRONTEND_URL = https://your-app.vercel.app
   ```
   (Replace with your actual Vercel URL)
4. Railway will auto-redeploy

---

## Step 4: Update Supabase Redirect URLs

1. Go back to Supabase → **Authentication** → **URL Configuration**
2. Update **Site URL** to your Vercel URL
3. Add your Vercel URL to **Redirect URLs**

---

## Step 5: Verify Everything Works

1. Visit your Vercel URL
2. Click "Sign in with Google"
3. Complete OAuth flow
4. Verify you're logged in and can access the app

---

## Quick Reference

| Service | URL |
|---------|-----|
| API | https://maestro-super-production.up.railway.app |
| API Health | https://maestro-super-production.up.railway.app/health |
| API Docs | https://maestro-super-production.up.railway.app/docs |
| Supabase | https://ybyqobdyvbmsiehdmxwp.supabase.co |
| Frontend | (your Vercel URL after deploy) |

---

## Troubleshooting

### CORS Errors
- Make sure `FRONTEND_URL` is set in Railway
- Check the URL doesn't have a trailing slash

### OAuth Redirect Errors
- Verify redirect URL in Google Console matches Supabase exactly
- Check Supabase redirect URLs include your frontend domain

### Auth Not Working
- Check browser console for errors
- Verify Supabase anon key is correct in Vercel env vars
