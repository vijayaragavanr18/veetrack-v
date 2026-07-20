#!/bin/bash
# Start vLLM server on port 8080 for VeeTrack chatbot and AI features

set -e

echo "🚀 Starting vLLM server for VeeTrack..."
echo "📍 Port: 8080"
echo "🤖 Model: Qwen/Qwen2.5-7B-Instruct"
echo ""

# Check GPU
if command -v nvidia-smi &> /dev/null; then
    echo "🎮 GPU detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    echo ""
else
    echo "⚠️  No GPU detected - will use CPU (slow)"
    echo ""
fi

# Check if vLLM is installed
if ! .venv/bin/python -c "import vllm" 2>/dev/null; then
    echo "❌ vLLM not installed in .venv"
    echo ""
    echo "Install with:"
    echo "  .venv/bin/pip install vllm"
    exit 1
fi

# Start vLLM
echo "Starting vLLM server..."
echo "Access at: http://localhost:8080/v1"
echo ""
echo "Press Ctrl+C to stop"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

.venv/bin/python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-7B-Instruct \
  --port 8080 \
  --host 127.0.0.1 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.90
