# Models in VeeTrack

This document lists all AI models used in VeeTrack and their purposes.

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
| BGE-large-en-v1.5 | 1.3GB | 2GB | Embeddings for clustering | ✅ Downloaded |
| GLiNER-small | 200MB | 1GB | Entity extraction | ✅ Downloaded |
| DeBERTa-v3-small | 160MB | 1GB | Sentiment analysis | ✅ Downloaded |
| Tabularisai sentiment | 500MB | 1GB | Multilingual sentiment | ✅ Downloaded |

**Total:** ~2.1 GB disk space  
**All models already downloaded!** ✅

---

## 🎮 Your Hardware

**GPU:** NVIDIA GeForce RTX 5050 Laptop (8GB VRAM)  

**Concurrent usage:**
- embeddings (2GB) + entities (1GB) + sentiment (1GB) = 4GB total ✅

---

## 🔄 Upgrading Models (Future)

If you want to upgrade to better models later:

### For Embeddings:
```bash
# Upgrade to larger embedding model (2048-dim)
.venv/bin/python -c "from huggingface_hub import snapshot_download; snapshot_download('BAAI/bge-large-en-v1.5')"
```

But your current models are perfect for production PR monitoring!

---

## ✅ Summary

**You have all models downloaded!**
- BGE for embeddings ✅
- GLiNER for entities ✅
- DeBERTa for sentiment ✅
