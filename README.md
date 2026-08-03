# VeeTrack: AI-Powered PR Intelligence Platform

**VeeTrack** is a next-generation media intelligence platform designed specifically for PR professionals, executives, and communications teams. It replaces traditional, cluttered spreadsheet dashboards (like Meltwater or Brandwatch) with a premium, mobile-first **"Flipboard-style"** 3D swipe UI.

The platform continuously monitors global news (via NewsData API), clusters related articles into cohesive storylines, and uses local, on-premise AI models (via Ollama) to automatically generate **Executive Briefs** ("What Happened" and "Why It Matters") alongside tailored **PR Recommendations**.

---

## 🏗️ System Architecture

The codebase is structured as a modern full-stack monorepo, divided into two main environments:

### 1. `veetrack-frontend` (Next.js 15)
- **Framework**: Next.js 15 (App Router), React 19, TypeScript
- **Styling**: TailwindCSS 4, Framer Motion
- **Design System**: Mobile-first, dark-mode native, high-end editorial typography.
- **Physics Engine**: Custom 3D DOM manipulation inside `src/components/flip/` handling gestural math (`useFlipGesture.ts`) and CSS 3D transforms (`VerticalFlipCard.tsx` / `HorizontalFlipCard.tsx`) to recreate physical magazine page turns.
- **State**: Zustand for global state, React Query for API caching.

### 2. `veetrack-backend` (FastAPI + Celery + Ollama)
- **API (FastAPI)**: High-performance asynchronous API serving the frontend feed and handling search queries.
- **Workers (Celery)**: Background task workers managing a sophisticated NLP pipeline. It periodically ingests news, extracts entities, and triggers AI analysis asynchronously.
- **AI Engine (Ollama)**: Uses `qwen2.5:7b` running locally for 100% private, on-premise generation of Executive Briefings and PR strategy recommendations.
- **Database**: PostgreSQL with `pgvector` for similarity search, accessed via SQLAlchemy ORM.
- **Cache & Message Broker**: Redis.

---

## 📂 Core Handoff Directory Guide

For future developers or agencies taking over this repository, here are the most critical directories:

### Frontend (`veetrack-frontend/`)
* **`src/app/(feed)/`**: The core shell of the application, including the layout wrapper, bottom navigation, and search overlay.
* **`src/components/flip/`**: The crown jewel of the UI. This folder contains all the complex 3D math and gesture tracking required to make the pages "flip" like a real book. Modify `flipMath.ts` to adjust the physics.
* **`src/components/pages/`**: The individual pages within a story. 
  * `Page1Original.tsx`: The primary article view with the hero image.
  * `Page2Insight.tsx`: The AI-generated Executive Brief.
  * `Page3Cluster.tsx`: The topic timeline / related articles.
  * `Page4Recommendations.tsx`: The AI PR strategy recommendations.
* **`src/components/ui/`**: Reusable design system components (Engagement Row, Badges, etc).

### Backend (`veetrack-backend/`)
* **`src/app/api/v1/feed.py`**: The main API endpoint. It contains the logic for the "Fast Path" (fetching from Redis) and the "Live Fallback Path" (fetching live from NewsData and generating AI responses on the fly).
* **`src/workers/tasks/`**: Contains the Celery background tasks that power the data engine:
  * `ingestion/watch_scheduled.py`: The cron job that wakes up and pulls new articles for tracked entities.
  * `llm/generate_summary.py`: The task that asks Ollama to write the Executive Brief.
* **`src/app/infrastructure/db/models/`**: SQLAlchemy schema definitions (Articles, Stories, Entities).
* **`alembic/versions/`**: Database migration history.

---

## 🚀 How to Run Locally

We have provided two unified startup scripts at the root of the repository to make booting the stack effortless.

### Prerequisites
1. **Docker**: Must be installed and running.
2. **Node.js (v20+)**: Required for the frontend.
3. **Ollama**: Required for AI features. Install via `curl -fsSL https://ollama.com/install.sh | sh`.

### Environment Variables
Copy `.env.example` to `.env` in the root directory and fill in any required API keys (e.g., `NEWSDATA_API_KEY`).

### Booting the Stack

**Terminal 1: Start the Backend & Database**
```bash
./start-backend.sh
```
*This script will:*
1. Boot Postgres and Redis via Docker.
2. Run database migrations.
3. Start the Ollama daemon and pull the AI model automatically.
4. Start the FastAPI server (Port 8000).
5. Start the Celery workers.

**Terminal 2: Start the Frontend**
```bash
./start-frontend.sh
```
*This script will start the Next.js development server on Port 3000.*

---

## ☁️ Deployment Guide

### Frontend Deployment (Vercel)
The frontend is optimized for deployment on Vercel.
1. Connect this GitHub repository to a new Vercel project.
2. Vercel will automatically detect the Next.js framework inside `/veetrack-frontend`.
3. In Vercel Environment Variables, set `NEXT_PUBLIC_API_URL` to point to your live backend (e.g., `https://api.yourdomain.com/api/v1`).
4. Deploy!

### Backend Deployment (AWS / GCP / DigitalOcean)
Because the backend runs heavy AI models locally (Ollama/Qwen) and uses Docker for Postgres/Redis, it is best deployed on a VPS or cloud instance with decent RAM (8GB+ recommended) rather than a serverless platform.
1. Clone the repository to the server.
2. Ensure Docker and Ollama are installed.
3. Set your production `.env` file.
4. Run `./start-backend.sh` (or wrap it in a systemd service).
5. Use Nginx or Caddy to expose port 8000 via a secure HTTPS domain.

*(For local testing on mobile devices, you can securely tunnel the backend using `npx localtunnel --port 8000` or `ssh -R 80:localhost:8000 nokey@localhost.run` and paste the resulting URL into your Vercel Environment Variables).*
