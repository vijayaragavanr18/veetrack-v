# vLLM Setup Guide for VeeTrack AI Features

This guide shows how to set up vLLM on **port 8080** to power:
- AI chatbot (bottom-right floating button)
- AI Insight summaries (Page 2)
- PR Recommendations (Page 4)

---

## What You'll Get

### 1. AI Chatbot (Article-Specific)
- Floating button in bottom-right corner
- Only answers questions about the **current article**
- Refuses general knowledge questions
- Context: "What's the main issue?", "Who's affected?", "What's the PR risk?"

### 2. AI Insight (Page 2)
- "What Happened" summary
- "Why It Happened" analysis
- Generated via Celery workers

### 3. PR Recommendations (Page 4)
- Audience-specific recommendations
- Risk assessment
- Confidence scores

---

## Prerequisites

### Check Your GPU:
```bash
nvidia-smi
```

**Requirements for Qwen 7B:**
- ✅ 14-16GB VRAM (RTX 3090, 4090, A100, etc.)
- ✅ CUDA installed

**If you don't have GPU:**
- Use smaller model (Qwen 1.5B) — see "CPU Mode" below
- Or skip vLLM (article search still works!)

---

## Step 1: Install vLLM

```bash
cd /home/vijay/Projects/veetrack-v

# Install vLLM in root .venv
.venv/bin/pip install vllm

# Verify installation
.venv/bin/python -c "import vllm; print('✅ vLLM installed')"
```

---

## Step 2: Start vLLM Server (Port 8080)

### Option A: Use the Start Script (Recommended)
```bash
./start-vllm.sh
```

The script:
- Checks for GPU
- Starts vLLM on port 8080
- Uses Qwen/Qwen2.5-7B-Instruct
- Optimizes GPU memory usage

### Option B: Manual Start
```bash
.venv/bin/python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-7B-Instruct \
  --port 8080 \
  --host 127.0.0.1 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.90
```

**Expected output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8080 (Press CTRL+C to quit)
INFO:     Started server process
INFO:     Application startup complete.
```

**Leave this terminal running!**

---

## Step 3: Test vLLM

In a **new terminal**:

```bash
curl http://localhost:8080/v1/models | jq .
```

**Expected:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "Qwen/Qwen2.5-7B-Instruct",
      "object": "model",
      "created": 1234567890,
      "owned_by": "vllm"
    }
  ]
}
```

### Test Chat Completion:
```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 50
  }' | jq '.choices[0].message.content'
```

Should return a greeting response.

---

## Step 4: Restart Backend (Pick Up vLLM Config)

Backend needs to be restarted to use the new `VLLM_BASE_URL`:

```bash
# Stop existing backend (Ctrl+C in backend terminal)

cd veetrack-backend
PYTHONPATH=src .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Verify .env has:
```bash
cat .env | grep VLLM
# Should show:
# VLLM_BASE_URL=http://localhost:8080/v1
# VLLM_MODEL=Qwen/Qwen2.5-7B-Instruct
```

---

## Step 5: Test the AI Chatbot

1. Open frontend: http://localhost:3000
2. Login and search for an article (e.g., "Tesla")
3. See the **floating chat button** in bottom-right corner
4. Click it and ask: "What's this article about?"
5. Bot should summarize the article!

### Test Questions:
- ✅ "What's the main issue?"
- ✅ "Who's involved?"
- ✅ "What's the PR risk?"
- ✅ "Summarize this article"
- ❌ "What's the weather?" → Should refuse (not about article)

---

## Step 6: Enable Full AI Pipeline (Optional)

To get AI Insight (Page 2) and Recommendations (Page 4), start Celery workers:

```bash
cd veetrack-backend

# Start workers (separate terminal)
PYTHONPATH=src .venv/bin/celery -A workers.celery_app worker \
  --loglevel=info \
  -Q ingestion,nlp,llm,alerts \
  -c 2

# Optional: Start beat scheduler for periodic tasks
PYTHONPATH=src .venv/bin/celery -A workers.celery_app beat --loglevel=info
```

Now when you search, workers will:
1. Fetch articles
2. Generate AI summaries (Page 2)
3. Generate PR recommendations (Page 4)

---

## CPU Mode (No GPU)

If you don't have a GPU, use a smaller model on CPU:

### Option 1: Qwen 1.5B (Faster on CPU)
```bash
.venv/bin/python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --port 8080 \
  --device cpu \
  --dtype float32
```

Update .env:
```bash
echo "VLLM_MODEL=Qwen/Qwen2.5-1.5B-Instruct" >> veetrack-backend/.env
```

⚠️ CPU mode is 10-50x slower than GPU.

---

## Troubleshooting

### Chatbot button doesn't appear

**Check 1: Frontend has ArticleChatbot**
```bash
grep -r "ArticleChatbot" veetrack-frontend/src/components/flip/
# Should find import in FlipStoryViewer.tsx
```

### Chatbot says "Network error"

**Check 1: vLLM is running**
```bash
curl http://localhost:8080/v1/models
```

**Check 2: Backend can reach vLLM**
```bash
cd veetrack-backend
curl http://localhost:8080/v1/models
```

**Check 3: Backend endpoint exists**
```bash
curl -X POST http://localhost:8000/api/v1/chat/article \
  -H "Content-Type: application/json" \
  -d '{
    "story_id": "test",
    "question": "test",
    "article_headline": "test",
    "article_content": "test",
    "article_publisher": "test"
  }'
```

Should return a response (not 404).

### vLLM crashes with "Out of memory"

**Reduce GPU memory usage:**
```bash
.venv/bin/python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-7B-Instruct \
  --port 8080 \
  --gpu-memory-utilization 0.70  # Lower from 0.90
  --max-model-len 2048  # Reduce context window
```

Or use 1.5B model (needs less VRAM).

### Chatbot answers are wrong/off-topic

The prompt restricts it to article-only responses. Check backend logs:
```bash
tail -f /tmp/backend.log | grep chat
```

If vLLM is ignoring the prompt, try:
- Lower temperature (currently 0.3, try 0.1)
- Stronger system prompt
- Smaller model (sometimes more obedient)

---

## What Works Without vLLM? ✅

If you skip vLLM setup:
- ✅ Article search
- ✅ Page 1 (Original Article)
- ✅ Page 3 (Cluster)
- ✅ Saved stories
- ✅ Profile & auth
- ❌ AI Chatbot (button won't work)
- ❌ Page 2 AI Insight (shows "Analysis pending...")
- ❌ Page 4 Recommendations (shows empty)

---

## All Terminals Summary

For full AI features, you need 4 terminals:

```bash
# Terminal 1 — vLLM
./start-vllm.sh

# Terminal 2 — Backend API
cd veetrack-backend
PYTHONPATH=src .venv/bin/uvicorn app.main:app --reload --port 8000

# Terminal 3 — Celery Workers (optional)
cd veetrack-backend
PYTHONPATH=src .venv/bin/celery -A workers.celery_app worker -Q ingestion,nlp,llm

# Terminal 4 — Frontend
cd veetrack-frontend
pnpm dev
```

---

## Quick Test Commands

**Test vLLM:**
```bash
curl http://localhost:8080/v1/models | jq '.data[0].id'
```

**Test Backend:**
```bash
curl http://localhost:8000/api/v1/health
```

**Test Frontend:**
```bash
curl http://localhost:3000
```

**Test Chatbot Endpoint:**
```bash
curl -X POST http://localhost:8000/api/v1/chat/article \
  -H "Content-Type: application/json" \
  -d '{
    "story_id": "test-123",
    "question": "What is this article about?",
    "article_headline": "Tesla Recalls 2 Million Vehicles",
    "article_content": "Tesla is recalling 2 million vehicles due to autopilot safety concerns...",
    "article_publisher": "Reuters"
  }' | jq '.answer'
```

---

## Deployment Notes

### For ngrok + Vercel:

**DO NOT expose vLLM via ngrok!**
- vLLM runs locally only (localhost:8080)
- Backend calls vLLM internally
- Only backend API is exposed via ngrok

```
┌─────────────────────┐
│  Mobile (Vercel)    │
│  Frontend           │
└──────┬──────────────┘
       │ HTTPS (ngrok)
┌──────▼──────────────┐
│  Your Machine       │
│  Backend :8000 ◄────┼─── vLLM :8080 (localhost only)
│  (exposed)          │
└─────────────────────┘
```

vLLM is never exposed to the internet — only the backend chatbot endpoint is public.

---

## Next Steps

1. ✅ vLLM running on port 8080
2. ✅ Backend restarted with vLLM config
3. ✅ Test chatbot in browser
4. Deploy to ngrok + Vercel (see DEPLOYMENT.md)

**Ready for PR teams!** 🎉
