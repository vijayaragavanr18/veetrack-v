"""GPU/batch-size constants for NLP worker tasks.

These numbers are tuned for 8 GB VRAM (RTX 4060 / RTX 5050) with all four
models loaded simultaneously (BGE-M3 + GLiNER + ModernBERT + Qwen3-4B AWQ).

Derivation is in docs/27_PERFORMANCE_TUNING.md §4.
Override via environment variables for different hardware.

IMPORTANT: only one Celery worker process should run on the nlp queue
per GPU.  Use --concurrency 1 when launching the nlp worker.
Run ingestion/alerts/llm queues on separate worker processes.
"""

from __future__ import annotations

import os

# BGE-M3 (1024-dim, fp16) — 32 × 512-token sequences ≈ 1.4 GB peak VRAM.
EMBED_BATCH_SIZE: int = int(os.getenv("VEETRACK_EMBED_BATCH_SIZE", "32"))

# GLiNER-large — 16 × 384-token sequences ≈ 0.9 GB peak VRAM.
NER_BATCH_SIZE: int = int(os.getenv("VEETRACK_NER_BATCH_SIZE", "16"))

# ModernBERT-base — 64 × 512-token sequences ≈ 0.5 GB peak VRAM.
SENTIMENT_BATCH_SIZE: int = int(os.getenv("VEETRACK_SENTIMENT_BATCH_SIZE", "64"))

# Qwen3-4B AWQ — used for recommendation adjudication; always called one at a
# time (the exec brief is low-volume, high-value; no batching needed).
LLM_LOCAL_MAX_NEW_TOKENS: int = int(os.getenv("VEETRACK_LLM_MAX_NEW_TOKENS", "512"))

# PyTorch CUDA allocator hint — reduce fragmentation on 8 GB cards.
# Set via PYTORCH_CUDA_ALLOC_CONF env var before importing torch.
# Worker launch script should export this before calling celery.
CUDA_ALLOC_CONF: str = "max_split_size_mb:512,garbage_collection_threshold:0.8"
