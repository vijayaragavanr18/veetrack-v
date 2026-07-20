# domain

The innermost layer. Contains entities, value objects, and repository/service interfaces.

**Rules:**
- Zero imports from `application`, `infrastructure`, or `api` layers.
- No framework dependencies (no FastAPI, SQLAlchemy, Redis, etc.).
- All interfaces (protocols/ABCs) that `infrastructure` must implement live here.

**What belongs here:** `Article`, `Story`, `Entity`, `Workspace`, `User` dataclasses/pydantic models;
`ArticleRepository`, `StoryRepository` abstract interfaces; domain exceptions.
