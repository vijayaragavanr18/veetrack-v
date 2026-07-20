# infrastructure

Concrete implementations of domain interfaces. All I/O lives here.

**Sub-packages:**
- `db/` — SQLAlchemy models + async repositories (implements domain repository interfaces)
- `connectors/` — `SourceConnector` implementations for NewsData.io, TwitterAPI.io, RSS, YouTube
- `llm/` — `LLMGateway` abstraction + vLLM client + hosted Claude client
- `cache/` — Redis client wrapper

**Rules:**
- May import from `domain` and `application`.
- All external I/O (DB, HTTP, Redis) is confined here — never leaks into `application` or `domain`.
