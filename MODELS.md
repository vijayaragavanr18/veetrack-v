# Models in VeeTrack

This document lists all AI models used in VeeTrack and their purposes.

---

## 🤖 vLLM Models (Text Generation)

### Current Model: Qwen/Qwen2.5-3B-Instruct ✅

**Already Downloaded:** Yes (6.5 GB)  
**Location:** `~/.cache/huggingface/hub/models--Qwen--Qwen2.5-3B-Instruct`

**Specifications:**
- Parameters: 3 billion
- VRAM Required: 6-8 GB
- Context Length: 4096 tokens
- Speed: Fast (3B is much faster than 7B)
- Quality: Excellent for chatbot and summaries

**Used For:**
1. ✅ **AI Chatbot** (floating button) — Answers questions about articles
2. ✅ **AI Insight** (Page 2) — "What Happened" / "Why It Happened" summaries
3. ✅ **PR Recommendations** (Page 4) — Strategic recommendations for PR teams

**Why 3B instead of 7B?**
- Your RTX 5050 has 8GB VRAM — perfect for 3B
- 3B is 2-3x faster than 7B
- Quality is still excellent for PR/news summaries
- 7B would need 14-16GB VRAM

### Alternative: Qwen/Qwen2.5-3B-Instruct-AWQ ⚡

**Already Downloaded:** Yes (quantized, 4-bit)  
**Size:** ~2GB (75% smaller)  
**Speed:** 30-50% faster than regular 3B  
**Quality:** 95% of original quality

**When to use:** If regular 3B is slow or you want more VRAM for other tasks

To switch to AWQ:
```bash
# Edit .env
VLLM_MODEL=Qwen/Qwen2.5-3B-Instruct-AWQ

# Edit start-vllm.sh
--model Qwen/Qwen2.5-3B-Instruct-AWQ \
--quantization awq
```

---

## 🧠 NLP Pipeline Models

These run in Celery workers for background processing:

### 1. BAAI/bge-large-en-v1.5 (Embeddings)
**Purpose:** Convert articles to 1024-dimensional vectors for similarity search  
**Size:** ~1.3 GB  
**Used For:**
- Article clustering (Page 3)
- Finding related articles
- Semantic search
- Story grouping

**Tech:** Stored in pgvector (PostgreSQL extension)

---

### 2. urchade/gliner_small-v2.1 (Entity Extraction)
**Purpose:** Extract companies, people, locations from articles  
**Size:** ~200 MB  
**Used For:**
- Identifying entities in articles
- Entity resolution (merging "Apple" and "Apple Inc.")
- Building entity graphs
- Feed filtering by entity

**Example:** Extracts "Tesla", "Elon Musk", "California" from an article

---

### 3. microsoft/deberta-v3-small (Sentiment Analysis)
**Purpose:** Classify article sentiment (positive/negative/neutral)  
**Size:** ~160 MB  
**Used For:**
- Sentiment badges on articles
- Risk assessment (negative sentiment = higher risk)
- Trend analysis (sentiment over time)

**Output:** Positive/Negative/Neutral + confidence score

---

### 4. tabularisai/multilingual-sentiment-analysis
**Purpose:** Sentiment analysis for non-English articles  
**Size:** ~500 MB  
**Used For:**
- Spanish, French, German, Chinese news articles
- Global PR monitoring
- Fallback when DeBERTa doesn't support the language

---

## 📊 Model Summary Table

| Model | Size | VRAM | Purpose | Status |
|-------|------|------|---------|--------|
| Qwen 3B-Instruct | 6.5GB | 6-8GB | Chatbot, Summaries, Recommendations | ✅ Downloaded |
| Qwen 3B-AWQ | 2GB | 3-4GB | Same as above (faster) | ✅ Downloaded |
| BGE-large-en-v1.5 | 1.3GB | 2GB | Embeddings for clustering | ✅ Downloaded |
| GLiNER-small | 200MB | 1GB | Entity extraction | ✅ Downloaded |
| DeBERTa-v3-small | 160MB | 1GB | Sentiment analysis | ✅ Downloaded |
| Tabularisai sentiment | 500MB | 1GB | Multilingual sentiment | ✅ Downloaded |

**Total:** ~10-11 GB disk space  
**All models already downloaded!** ✅

---

## 🎮 Your Hardware

**GPU:** NVIDIA GeForce RTX 5050 Laptop (8GB VRAM)  
**Recommendation:** Qwen 3B-Instruct (perfect fit!)

**What fits:**
- ✅ Qwen 3B (~6GB VRAM) — Plenty of room
- ✅ Qwen 3B-AWQ (~3GB VRAM) — Even more room
- ❌ Qwen 7B (~14GB VRAM) — Won't fit

**Concurrent usage:**
- Qwen 3B (6GB) + embeddings (2GB) = 8GB total ✅

---

## 🚀 How to Start vLLM

### Using Your Downloaded Model (Recommended):
```bash
cd /home/vijay/Projects/veetrack-v
./start-vllm.sh
```

This will:
- Use Qwen/Qwen2.5-3B-Instruct (already downloaded)
- Start on port 8080
- Use your RTX 5050 GPU
- Enable chatbot + AI features

### Expected Output:
```
🚀 Starting vLLM server for VeeTrack...
📍 Port: 8080
🤖 Model: Qwen/Qwen2.5-3B-Instruct

🎮 GPU detected:
NVIDIA GeForce RTX 5050 Laptop GPU, 8151 MiB

Starting vLLM server...
Access at: http://localhost:8080/v1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INFO:     Loading model Qwen/Qwen2.5-3B-Instruct...
INFO:     Model loaded successfully
INFO:     Uvicorn running on http://127.0.0.1:8080
```

---

## 🔄 Upgrading Models (Future)

If you want to upgrade to better models later:

### For Chatbot (vLLM):
```bash
# Download Qwen 7B (if you get more VRAM)
.venv/bin/python -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen2.5-7B-Instruct')"

# Or Qwen 14B (needs 24GB+ VRAM)
# Or Qwen 32B (needs 48GB+ VRAM)
```

### For Embeddings:
```bash
# Upgrade to larger embedding model (2048-dim)
.venv/bin/python -c "from huggingface_hub import snapshot_download; snapshot_download('BAAI/bge-large-en-v1.5')"
```

But your current models are perfect for production PR monitoring!

---

## ✅ Summary

**You have all models downloaded!**
- Qwen 3B for chatbot ✅
- BGE for embeddings ✅
- GLiNER for entities ✅
- DeBERTa for sentiment ✅

**Your GPU (RTX 5050, 8GB) is perfect for:**
- Qwen 3B-Instruct
- Fast chatbot responses
- Real-time AI summaries

**Ready to start vLLM?**
```bash
./start-vllm.sh
```

Then test the chatbot at http://localhost:3000!
