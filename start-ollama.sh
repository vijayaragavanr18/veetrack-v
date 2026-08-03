#!/bin/bash
# Start Ollama for VeeTrack AI features (chatbot, summaries, recommendations)
# Ollama runs as a background daemon — this script ensures it's running and the model is pulled.

set -e

MODEL="qwen2.5:7b"

echo "Starting Ollama for VeeTrack..."
echo "Model: $MODEL"
echo ""

# Check if ollama is installed
if ! command -v ollama &>/dev/null; then
    echo "Ollama not installed."
    echo ""
    echo "Install with:"
    echo "  curl -fsSL https://ollama.com/install.sh | sh"
    echo ""
    echo "Then re-run this script."
    exit 1
fi

# Start ollama serve in background if not already running
if ! curl -sf http://localhost:11434/ >/dev/null 2>&1; then
    echo "Starting Ollama daemon..."
    ollama serve &>/dev/null &
    sleep 2
    echo "Ollama daemon started."
else
    echo "Ollama daemon already running."
fi

# Pull the model if not already downloaded
echo ""
echo "Checking model $MODEL..."
if ollama list | grep -q "$MODEL"; then
    echo "Model already downloaded."
else
    echo "Pulling $MODEL (~2 GB, one-time download)..."
    ollama pull "$MODEL"
fi

echo ""
echo "Ollama ready at: http://localhost:11434"
echo "OpenAI-compatible API: http://localhost:11434/v1"
echo ""
echo "To stop: pkill ollama"
