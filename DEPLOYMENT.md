# VeeTrack Deployment Guide

This guide covers deploying the VeeTrack frontend to Vercel and backend via ngrok for mobile testing.

## Prerequisites

- GitHub repository pushed (✓ done)
- Vercel account
- ngrok account (for backend tunnel)
- PostgreSQL + Redis running locally or on a cloud provider

---

## 1. Deploy Frontend to Vercel

### Option A: Via Vercel Dashboard (Recommended)

1. Go to [vercel.com](https://vercel.com) and sign in
2. Click **"Add New Project"**
3. Import your GitHub repository: `vijayaragavanr18/veetrack-v`
4. **Configure Project:**
   - **Framework Preset:** Next.js
   - **Root Directory:** `veetrack-frontend`
   - **Build Command:** `pnpm build` (auto-detected)
   - **Output Directory:** `.next` (auto-detected)
   - **Install Command:** `pnpm install`

5. **Environment Variables** (click "Environment Variables"):
   ```
   NEXT_PUBLIC_API_URL=https://YOUR-NGROK-SUBDOMAIN.ngrok-free.app
   ```
   ⚠️ Leave this blank for now — you'll set it after starting ngrok in step 2.

6. Click **Deploy**

7. Once deployed, Vercel gives you a URL like:
   ```
   https://veetrack-v-YOUR-USERNAME.vercel.app
   ```

### Option B: Via Vercel CLI

```bash
cd veetrack-frontend
npm i -g vercel   # if not installed
vercel login
vercel --prod
# Follow prompts, set NEXT_PUBLIC_API_URL when asked
```

---

## 2. Run Backend via ngrok

### 2.1 Start Local Backend

```bash
cd /home/vijay/Projects/veetrack-v/veetrack-backend

# Ensure .env exists with required vars:
cat .env
# DATABASE_URL=postgresql+asyncpg://...
# REDIS_URL=redis://localhost:6379/0
# JWT_SECRET=your-long-random-secret
# NEWSDATA_API_KEY=...
# APIDIRECT_API_KEY=...

# Start Postgres + Redis (if not running)
docker compose -f ../infra/docker-compose.yml --env-file ../.env up -d

# Start backend API
PYTHONPATH=src .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Backend should be running at `http://localhost:8000`

Test:
```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

### 2.2 Expose via ngrok

In a **separate terminal**:

```bash
ngrok http 8000
```

ngrok will output:
```
Forwarding   https://abc123xyz.ngrok-free.app -> http://localhost:8000
```

Copy that `https://...ngrok-free.app` URL.

### 2.3 Update Vercel Environment Variable

1. Go to your Vercel project → **Settings** → **Environment Variables**
2. Add or edit `NEXT_PUBLIC_API_URL`:
   ```
   NEXT_PUBLIC_API_URL=https://abc123xyz.ngrok-free.app
   ```
3. Click **Save**
4. Go to **Deployments** tab → click **⋯** on latest deployment → **Redeploy**

---

## 3. Test on Mobile

1. Open your Vercel URL on your phone:
   ```
   https://veetrack-v-YOUR-USERNAME.vercel.app
   ```

2. You should see the **login page** with the Vee Technologies logo

3. **Create an account** or **sign in** (backend must be running + ngrok active)

4. After login, you'll be redirected to `/feed` — tap the search button and enter a keyword like "Tesla" to see live stories

---

## 4. Backend Workers (Optional — for full pipeline)

If you want NLP/LLM processing (sentiment, entities, summaries, recommendations):

```bash
cd veetrack-backend

# Start Celery workers (4 queues)
PYTHONPATH=src .venv/bin/celery -A workers.celery_app worker \
  --loglevel=info \
  -Q ingestion,nlp,llm,alerts \
  -c 2

# Start Celery beat (scheduled tasks)
PYTHONPATH=src .venv/bin/celery -A workers.celery_app beat --loglevel=info
```

---

## 5. Production Deployment (Future)

For production, replace ngrok with a real cloud deployment:

- **Backend:** Railway, Render, Fly.io, AWS ECS, or GCP Cloud Run
- **Database:** Neon, Supabase, or AWS RDS (PostgreSQL with pgvector)
- **Redis:** Upstash, Redis Cloud, or AWS ElastiCache
- **Workers:** Same host as backend, or separate container

Update `NEXT_PUBLIC_API_URL` in Vercel to point to your production backend URL.

---

## Troubleshooting

### Frontend shows "Network error — is the API server running?"

- Check ngrok is active: `curl https://YOUR-NGROK-URL.ngrok-free.app/health`
- Check `NEXT_PUBLIC_API_URL` is set in Vercel and deployment was redeployed after setting it
- Check browser console for CORS errors (backend should allow `*.vercel.app` origins)

### Backend CORS error

Backend `main.py` already has:
```python
allow_origin_regex=r"https://(.*\.vercel\.app|.*\.ngrok-free\.app|.*\.ngrok\.io)"
```

If you see CORS errors, verify the regex matches your Vercel domain.

### "Story not found" or empty feed

- Backend needs data: run ingestion tasks or use the live NewsData.io fallback (it fetches directly when DB is empty)
- Check `NEWSDATA_API_KEY` is set in backend `.env`

### ngrok "Too Many Connections" (free tier limit)

ngrok free tier limits concurrent connections. Upgrade to a paid plan or use a production deployment.

---

## Quick Start Commands

**Terminal 1 — Backend:**
```bash
cd /home/vijay/Projects/veetrack-v/veetrack-backend
PYTHONPATH=src .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — ngrok:**
```bash
ngrok http 8000
# Copy the https URL, update Vercel env var, redeploy
```

**Browser — Mobile:**
```
https://your-vercel-app.vercel.app
```

---

## Environment Variables Reference

### Frontend (Vercel)
| Variable | Example | Notes |
|----------|---------|-------|
| `NEXT_PUBLIC_API_URL` | `https://abc.ngrok-free.app` | Backend API base URL (no trailing slash) |

### Backend (local/.env)
| Variable | Example | Required |
|----------|---------|----------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/db` | ✅ |
| `REDIS_URL` | `redis://localhost:6379/0` | ✅ |
| `JWT_SECRET` | `long-random-string-never-commit-this` | ✅ |
| `NEWSDATA_API_KEY` | `pub_xxxxx` | ⚠️ For live fallback |
| `APIDIRECT_API_KEY` | `ak_live_xxxxx` | ⚠️ For Twitter/YouTube |

---

## Next Steps

1. Push this `DEPLOYMENT.md` to GitHub:
   ```bash
   git add DEPLOYMENT.md
   git commit -m "docs: add deployment guide for Vercel + ngrok"
   git push origin restructure/frontend-backend-split
   ```

2. Deploy frontend to Vercel (step 1 above)

3. Start backend + ngrok (step 2 above)

4. Test on mobile! 📱
