# syntax=docker/dockerfile:1.7
# Next.js standalone output Docker image.
# Requires next.config.ts: output: "standalone"
#
# Build context must be the monorepo root so shared packages are available.
# Example: docker build -f infra/docker/web.Dockerfile -t veetrack-web .

# ── Stage 1: deps ─────────────────────────────────────────────────────────────
FROM node:20-alpine AS deps

WORKDIR /app

# Install pnpm via corepack (ships with Node 20, avoids global npm install)
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

# Copy workspace manifests first — changes here bust the install cache
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./

# Copy package manifests for every workspace member that will be installed.
# packages/shared-types must be here so pnpm resolves the local dependency.
COPY packages/shared-types/package.json ./packages/shared-types/package.json
COPY apps/web/package.json ./apps/web/package.json

RUN pnpm install --frozen-lockfile

# ── Stage 2: builder ──────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

# Bring in node_modules from deps stage
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules

# Copy all source — shared types must be present before the build
COPY packages/ ./packages/
COPY apps/web/ ./apps/web/
# Root config files referenced by turbo / Next.js
COPY package.json pnpm-workspace.yaml turbo.json ./

ENV NEXT_TELEMETRY_DISABLED=1

RUN pnpm --filter web build

# ── Stage 3: runner ───────────────────────────────────────────────────────────
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

# Non-root user (uid 1001 — avoids collision with node's uid 1000)
RUN addgroup --system --gid 1001 nodejs && \
    adduser  --system --uid 1001 nextjs

# Standalone output contains a self-contained server.js + required node_modules
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/static    ./apps/web/.next/static
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/public          ./apps/web/public

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -qO- http://localhost:3000/ || exit 1

CMD ["node", "apps/web/server.js"]
