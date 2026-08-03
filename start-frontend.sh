#!/usr/bin/env bash
# =============================================================================
# VeeTrack Frontend — run this in a second terminal
#
#   Terminal 1 (backend):   ./start-backend.sh
#   Terminal 2 (frontend):  ./start-frontend.sh
# =============================================================================
set -e
cd "$(dirname "$0")/veetrack-frontend"

echo "▶  Installing deps (if needed)..."
npx pnpm install --frozen-lockfile 2>/dev/null || npx pnpm install

echo "▶  Starting Next.js on http://localhost:3000 ..."
echo ""
npx pnpm dev
