# application

Use cases and application services. Orchestrates domain objects and calls domain interfaces.

**Rules:**
- May import from `domain` only.
- No FastAPI, SQLAlchemy, Redis, or HTTP client imports.
- Receives dependencies via constructor injection (passed in from `core/container.py`).

**What belongs here:** `FeedService`, `StoryService`, `AuthService`, `WatchlistService` — one
class per use-case group; each method maps to one user-facing operation.
