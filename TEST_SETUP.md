# Quick Test Setup — Article Search + Auth (No vLLM)

This guide shows how to test the full app with article search and authentication **without needing vLLM**.

## Prerequisites

✅ **Required:**
- PostgreSQL + Redis running (Docker Compose)
- NewsData.io API key in `.env`
- Backend dependencies installed (`uv sync`)
- Frontend dependencies installed (`pnpm install`)

❌ **NOT Required:**
- vLLM
- GPU
- Celery workers
- LLM models

---

## Step 1: Start Infrastructure (Postgres + Redis)

```bash
cd /home/vijay/Projects/veetrack-v

# Start Postgres with pgvector + Redis
docker compose -f infra/docker-compose.yml --env-file .env up -d

# Verify they're running
docker ps
# Should show: pgvector/pgvector:pg16 and redis:7-alpine

# Check connection
docker compose -f infra/docker-compose.yml --env-file .env ps
```

---

## Step 2: Run Database Migrations

```bash
cd veetrack-backend

# Run migrations to create all tables
uv run alembic upgrade head

# Verify tables were created
docker exec -it $(docker ps -qf "name=postgres") psql -U veetrack -d veetrack -c "\dt"
# Should show: articles, stories, entities, users, workspaces, etc.
```

---

## Step 3: Create a Test User (Manual Insert)

Since we're testing without full auth flow, create a test user directly:

```bash
docker exec -it $(docker ps -qf "name=postgres") psql -U veetrack -d veetrack <<'SQL'
-- Create a workspace
INSERT INTO workspaces (id, name, created_at, updated_at) 
VALUES ('test-workspace-id', 'Test Workspace', NOW(), NOW());

-- Create a test user
INSERT INTO users (id, email, hashed_password, role, workspace_id, created_at, updated_at)
VALUES (
  'test-user-id',
  'admin@veetrack.io',
  '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5jtRMvKzH8.uS',  -- password: "test123"
  'admin',
  'test-workspace-id',
  NOW(),
  NOW()
);

-- Verify
SELECT email, role FROM users;
SQL
```

**Test credentials:**
- Email: `admin@veetrack.io`
- Password: `test123`
- Workspace ID: `test-workspace-id`

---

## Step 4: Start Backend API

```bash
cd veetrack-backend

# Check .env has required vars
cat .env | grep -E "DATABASE_URL|REDIS_URL|JWT_SECRET|NEWSDATA_API_KEY"

# Start backend
PYTHONPATH=src .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
```

**Test backend is running:**
```bash
# In a new terminal
curl http://localhost:8000/health
# Should return: {"status":"ok"}
```

---

## Step 5: Start Frontend

```bash
cd veetrack-frontend

# Check .env.local exists
cat .env.local
# Should have: NEXT_PUBLIC_API_URL=http://localhost:8000

# Start frontend
pnpm dev
```

**Expected output:**
```
▲ Next.js 15.3.4
- Local:        http://localhost:3000
✓ Ready in 2.5s
```

---

## Step 6: Test Full Flow

### 6.1 Test Login

1. Open browser: http://localhost:3000
2. You'll see the login page with **Vee Technologies logo**
3. Enter credentials:
   - Email: `admin@veetrack.io`
   - Password: `test123`
   - Workspace ID: `test-workspace-id`
4. Click **Sign in**

**✅ Expected:** Redirects to `/feed` with empty search prompt

**❌ If you see "Network error":**
- Check backend is running: `curl http://localhost:8000/health`
- Check browser console (F12) for CORS errors
- Check backend logs for errors
- Verify `.env.local` has `NEXT_PUBLIC_API_URL=http://localhost:8000`

### 6.2 Test Article Search

1. After login, click the **Search button** (center of bottom nav)
2. Type: `Tesla`
3. Press Enter or tap a quick-pick keyword

**✅ Expected:**
- Page shows "Loading..." spinner
- Then displays real Tesla articles with:
  - Headlines
  - Hero images
  - Publisher names (Reuters, Bloomberg, etc.)
  - Published dates
  - Content preview text
  - Source links

**Test other keywords:**
- Apple
- OpenAI
- Meta
- SpaceX

### 6.3 Test Story Pages

Swipe left/right (or use arrow keys on desktop) to see 4 pages:

**Page 1 — Original Article:**
- ✅ Hero image
- ✅ Headline
- ✅ Publisher source pill (top-left)
- ✅ Risk badge
- ✅ Entity tags
- ✅ Article content
- ✅ Like/Comment/Save/Share buttons

**Page 2 — AI Insight:**
- ⚠️ Shows "Analysis pending..." (vLLM not running)
- This is expected without vLLM

**Page 3 — Cluster:**
- ✅ Source pills
- ✅ List of related articles
- ✅ Article count

**Page 4 — Recommendations:**
- ⚠️ Shows "No recommendations generated yet" (vLLM not running)
- This is expected without vLLM

### 6.4 Test Saved Stories

1. On any story, tap the **Bookmark icon** (bottom right)
2. Icon fills with color
3. Go to **Profile** tab (bottom nav)
4. Tap **Saved Stories**
5. See your saved story with trash icon to remove

### 6.5 Test Profile

1. Go to **Profile** tab
2. See your email: `admin@veetrack.io`
3. Toggle theme (Moon/Sun icon)
4. Tap **Sign Out** → redirects to login

---

## Troubleshooting

### "Network error — is the API server running?"

**Check 1: Backend is running**
```bash
curl http://localhost:8000/health
# Should return: {"status":"ok"}
```

**Check 2: Check backend logs**
Look at the terminal where you ran `uvicorn` — any errors?

**Check 3: Test login endpoint directly**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@veetrack.io",
    "password": "test123",
    "workspace_id": "test-workspace-id"
  }'
```

**Expected response:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

**Check 4: CORS issues**
- Open browser DevTools (F12) → Console tab
- Look for CORS errors
- Backend should already allow `localhost:3000`

### No articles showing after search

**Check 1: NewsData.io API key is valid**
```bash
cd veetrack-backend
cat .env | grep NEWSDATA_API_KEY
```

**Check 2: Test NewsData.io directly**
```bash
curl "https://newsdata.io/api/1/latest?apikey=YOUR_KEY&q=Tesla&language=en" | jq .
```

**Check 3: Backend logs**
Look for errors when you search

**Check 4: Redis is running**
```bash
docker ps | grep redis
# Should show redis:7-alpine
```

### Login works but shows "Single source so far"

This means:
- ✅ Login successful
- ✅ Feed loaded
- ⚠️ Only 1 article found (need more data)

**Solution:** Search for multiple keywords to get more articles:
- Tesla
- Apple
- SpaceX

### Pages 2 & 4 say "Analysis pending"

✅ **This is correct!** Without vLLM running:
- Page 2 (AI Insight) shows placeholder
- Page 4 (Recommendations) shows empty state

To get AI features working, see section below.



---

## Quick Commands Reference

**Start everything:**
```bash
# Terminal 1 — Infrastructure
docker compose -f infra/docker-compose.yml --env-file .env up -d

# Terminal 2 — Backend
cd veetrack-backend && PYTHONPATH=src .venv/bin/uvicorn app.main:app --reload --port 8000

# Terminal 3 — Frontend
cd veetrack-frontend && pnpm dev

# Browser
http://localhost:3000
```

**Stop everything:**
```bash
# Stop frontend (Ctrl+C in Terminal 3)
# Stop backend (Ctrl+C in Terminal 2)

# Stop Docker
docker compose -f infra/docker-compose.yml down
```

---

## What Works Without vLLM? ✅

- ✅ Login/Register
- ✅ Article search
- ✅ Real-time article fetching from NewsData.io
- ✅ Article display (Page 1)
- ✅ Source clustering (Page 3)
- ✅ Saved stories
- ✅ Profile
- ✅ Theme toggle
- ✅ Engagement buttons (like/comment/save/share)
- ✅ Discover trending topics
- ✅ All navigation



## Next: Deploy to Vercel + ngrok

Once local testing works, follow `DEPLOYMENT.md` to:
1. Deploy frontend to Vercel
2. Expose backend via ngrok
3. Test on mobile

**Test credentials for mobile:**
- Email: `admin@veetrack.io`
- Password: `test123`
- Workspace ID: `test-workspace-id`
