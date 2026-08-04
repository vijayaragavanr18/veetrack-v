# VeeTrack: Autonomous Agentic PR Intelligence Platform

**VeeTrack** is a next-generation media intelligence platform designed for PR professionals, executives, and communications teams. It replaces traditional dashboard spreadsheets with a premium, mobile-first **3D swipe UI** (Flipboard-style). 

Under the hood, VeeTrack is powered by a **5-Agent Autonomous HiveMind Swarm**. These specialized agents continuously monitor global news, semantically deduplicate content, cluster related articles into cohesive storylines, and use local on-premise AI models (via Ollama) to autonomously generate **Executive Briefings** and **PR Action Plans**.

---

## 🧠 The 5-Agent HiveMind Architecture

VeeTrack's intelligence is driven by a lightweight, custom Python orchestration layer rather than heavy frameworks, maximizing performance and deterministic control over local LLM outputs. 

1. **🕵️ Scout Agent (Web Discovery)**: Scours the web using the NewsData API and dynamic MCP tool registration. It identifies breaking news and trending topics across global media outlets.
2. **🛡️ Gatekeeper Agent (Semantic Deduplication)**: Receives raw articles and runs them through a Vector DB (`pgvector`). It ensures we don't process duplicate stories by matching semantic embeddings.
3. **🧬 Synthesizer Agent (Clustering)**: Uses HDBSCAN and cosine similarity to group deduplicated articles into unified "Story Clusters" based on contextual narrative.
4. **📊 Analyst Agent (Executive Briefs)**: Processes full clusters and commands the local Ollama LLM to draft concise, high-level "What Happened" and "Why It Matters" executive summaries.
5. **👔 Executive PR Agent (Strategy & Comms)**: Analyzes the crisis/risk level of the story and generates tactical response plans, press release angles, and internal talking points for the C-Suite.

---

## 🚀 How to Clone and Run Locally (Cross-Platform)

VeeTrack is containerized with Docker, meaning it will run consistently across **Linux, macOS, and Windows (via WSL2)**.

### Step 1: Prerequisites
- **Git**: To clone the repository.
- **Docker & Docker Compose**: Required for running the PostgreSQL and Redis containers.
- **Node.js (v20+)**: Required for running the Next.js Turbopack frontend.
- **Ollama**: Required for running the local on-premise AI models. [Download Ollama here](https://ollama.com/download).

### Step 2: Clone the Repository
```bash
git clone https://github.com/vijayaragavanr18/veetrack-v.git
cd veetrack-v
```

### Step 3: Configure Environment Variables
Copy the example environment variables file to set up your local configuration:
```bash
cp .env.example .env
```
Open `.env` and add your `NEWSDATA_API_KEY`. 

> ⚠️ **IMPORTANT: Laptop Performance Tuning**
> By default, the app is configured to use the `qwen2.5:7b` AI model. If you are running this on a laptop with limited RAM or without a dedicated GPU, you can experience severe slowdowns.
> 
> **To optimize for standard laptops:**
> Open your `.env` file and change `LLM_LOCAL_MODEL=qwen2.5:7b` to `LLM_LOCAL_MODEL=qwen2.5:3b`. 
> Also, update the `MODEL` variable in `start-ollama.sh` to `"qwen2.5:3b"`. This smaller 3B parameter model runs blazingly fast on almost any modern laptop!

### Step 4: Boot the Stack (No Code Modification Required!)

We have provided two unified startup scripts at the root of the repository to boot the entire stack effortlessly.

**Terminal 1: Start the Backend & Databases**
```bash
./start-backend.sh
```
*What this does automatically:*
1. Boots Postgres (with `pgvector`) and Redis via Docker Compose.
2. Runs database migrations (Alembic).
3. Verifies the Ollama daemon and automatically pulls your configured Qwen model.
4. Starts the FastAPI server on port `8000` and boots up the Celery background worker agents.

**Terminal 2: Start the Frontend**
```bash
./start-frontend.sh
```
*What this does automatically:*
1. Installs all required Node.js dependencies (`pnpm install`).
2. Starts the Next.js 15 Turbopack development server on `http://localhost:3000`.

### Step 5: View the App
Open your web browser and navigate to **[http://localhost:3000](http://localhost:3000)**. 
*(Tip: Press `F12` and click the "Device Toolbar" icon in Chrome to simulate the premium mobile 3D swiping experience!)*

---

## ☁️ Deployment Guide

- **Frontend (Vercel)**: The frontend is fully optimized for edge deployment on Vercel. Simply connect your GitHub repository to Vercel, and set the `NEXT_PUBLIC_API_URL` environment variable to point to your hosted backend API.
- **Backend (VPS / Cloud Instance)**: Because the backend runs heavy NLP workloads, Celery workers, and local Ollama models, it is best deployed on a VPS (AWS EC2, DigitalOcean Droplet, etc.) with at least 8GB+ RAM. Use `docker-compose` to manage the containers in production and expose the FastAPI service via an Nginx reverse proxy.
