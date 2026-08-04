#!/usr/bin/env bash
# =============================================================================
# VeeTrack Tunnel — Cloudflare Tunnel for high-speed, zero-warning proxying
#
#   Usage: ./start-tunnel.sh
# =============================================================================

CLOUDFLARED_BIN="$HOME/.local/bin/cloudflared"

if [ ! -f "$CLOUDFLARED_BIN" ]; then
  echo "Installing cloudflared to $HOME/.local/bin..."
  mkdir -p "$HOME/.local/bin"
  curl -L -o "$CLOUDFLARED_BIN" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x "$CLOUDFLARED_BIN"
fi

echo "▶ Starting Cloudflare Tunnel for http://localhost:8000..."
"$CLOUDFLARED_BIN" tunnel --url http://localhost:8000
