# core

Cross-cutting infrastructure: DI wiring, config, security utilities.

**What belongs here:**
- `config.py` — `pydantic-settings` `Settings` class; required vars (`DATABASE_URL`, `REDIS_URL`,
  `JWT_SECRET`) raise `ValidationError` on startup if missing.
- `container.py` — composition root; builds and wires all dependencies (repositories, services)
  into `fastapi.Depends` providers.
- `security.py` — JWT encode/decode, password hashing helpers.
