# api/v1

FastAPI routers and Pydantic request/response schemas.

**Rules:**
- Routers call application services only — no direct DB/Redis/LLM access.
- Pydantic schemas here are API contracts; keep them separate from domain entities.
- No business logic in route handlers; every handler should be ≤10 lines.

**What belongs here:** `auth.py`, `feed.py`, `stories.py`, `watchlists.py`, `exports.py`,
`admin.py` routers; `schemas/` sub-package with Pydantic request/response models.
