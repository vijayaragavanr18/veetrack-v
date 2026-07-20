"""VeeTrack load-test suite — Phase 27 Performance Optimization.

Latency budget (from architecture doc "seconds not hours"):
  Fast Path   GET /feed?entity=<tracked>   p50 < 20 ms,  p95 < 50 ms
  Cold Path   GET /feed?entity=<untracked> p50 < 200 ms, p95 < 500 ms
  Story detail GET /stories/{id}            p50 < 30 ms,  p95 < 80 ms

Run (from repo root):
  cd apps/api
  uv run locust -f ../../perf/locustfile.py \
      --host http://localhost:8000 \
      --users 50 --spawn-rate 10 \
      --run-time 60s --headless \
      --csv ../../perf/results/run_$(date +%Y%m%dT%H%M%S)

Target hardware: single FastAPI process (4 uvicorn workers) + Redis on localhost.
Adjust --users for production multi-replica deployments.
"""

from __future__ import annotations

import os
import random
import string
from typing import Any

from locust import FastHttpUser, between, events, task

# ---------------------------------------------------------------------------
# Config (override via environment)
# ---------------------------------------------------------------------------

_HOST = os.getenv("LOCUST_HOST", "http://localhost:8000")
_JWT_TOKEN = os.getenv(
    "LOCUST_JWT_TOKEN",
    "REPLACE_ME_WITH_A_VALID_JWT",  # obtain via POST /api/v1/auth/login
)

# Tracked entities — these should exist in the test DB so Fast Path is exercised.
# Override via LOCUST_FAST_ENTITIES env var (comma-separated).
_FAST_ENTITIES: list[str] = os.getenv(
    "LOCUST_FAST_ENTITIES", "Tesla,Apple,Microsoft,Amazon,Google"
).split(",")

# Latency budgets (milliseconds) — used in custom event listeners below.
_FAST_P95_BUDGET_MS = 50
_COLD_P95_BUDGET_MS = 500
_STORY_P95_BUDGET_MS = 80


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _rand_keyword(length: int = 8) -> str:
    """Generate a random keyword guaranteed to be unknown (triggers Cold Path)."""
    return "zt_" + "".join(random.choices(string.ascii_lowercase, k=length))


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class FastPathUser(FastHttpUser):
    """Simulates a logged-in user browsing tracked entities (Fast Path).

    Weight: 8 — 80% of simulated traffic is Fast Path (reflecting real usage
    once entities are warmed; first-hit cold searches are relatively rare).
    """

    weight = 8
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        self._headers = {"Authorization": f"Bearer {_JWT_TOKEN}"}
        self._story_ids: list[str] = []

    @task(10)
    def get_fast_feed(self) -> None:
        entity = random.choice(_FAST_ENTITIES)
        with self.client.get(
            "/api/v1/feed",
            params={"entity": entity, "limit": 20},
            headers=self._headers,
            name="/feed [fast-path]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data: dict[str, Any] = resp.json()
                if data.get("path") != "fast":
                    # Cold miss on what should be a tracked entity — not a failure
                    # but we want visibility.
                    resp.success()
                else:
                    resp.success()
                    # Collect story IDs for the story-detail task below.
                    for story in data.get("stories", [])[:3]:
                        if len(self._story_ids) < 20:
                            self._story_ids.append(story["id"])
            elif resp.status_code == 401:
                resp.failure("Unauthorized — set LOCUST_JWT_TOKEN")
            else:
                resp.failure(f"Unexpected {resp.status_code}")

    @task(5)
    def get_fast_feed_paginated(self) -> None:
        entity = random.choice(_FAST_ENTITIES)
        # First page
        with self.client.get(
            "/api/v1/feed",
            params={"entity": entity, "limit": 20},
            headers=self._headers,
            name="/feed [fast-path page-1]",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"page 1 failed: {resp.status_code}")
                return
            resp.success()
            cursor = resp.json().get("next_cursor")

        if cursor:
            with self.client.get(
                "/api/v1/feed",
                params={"entity": entity, "cursor": cursor, "limit": 20},
                headers=self._headers,
                name="/feed [fast-path page-2]",
                catch_response=True,
            ) as resp2:
                if resp2.status_code == 200:
                    resp2.success()
                else:
                    resp2.failure(f"page 2 failed: {resp2.status_code}")

    @task(3)
    def get_story_detail(self) -> None:
        if not self._story_ids:
            return
        story_id = random.choice(self._story_ids)
        with self.client.get(
            f"/api/v1/stories/{story_id}",
            headers=self._headers,
            name="/stories/{id}",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}")


class ColdPathUser(FastHttpUser):
    """Simulates a new user searching for an unknown keyword (Cold Path).

    Weight: 2 — 20% of traffic; cold searches auto-promote so the ratio
    decreases over time as entities become tracked.
    """

    weight = 2
    wait_time = between(2.0, 5.0)

    def on_start(self) -> None:
        self._headers = {"Authorization": f"Bearer {_JWT_TOKEN}"}

    @task
    def get_cold_feed(self) -> None:
        keyword = _rand_keyword()
        with self.client.get(
            "/api/v1/feed",
            params={"entity": keyword, "limit": 10},
            headers=self._headers,
            name="/feed [cold-path]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Unauthorized — set LOCUST_JWT_TOKEN")
            else:
                resp.failure(f"Unexpected {resp.status_code}")


# ---------------------------------------------------------------------------
# Test-run event hooks — emit budget violations as warnings
# ---------------------------------------------------------------------------


@events.quitting.add_listener
def check_latency_budgets(environment: Any, **kwargs: Any) -> None:
    """Print a budget-violation summary when the test run ends."""
    stats = environment.stats
    violations: list[str] = []

    for name, entry in stats.entries.items():
        path, label = name if isinstance(name, tuple) else (name, "")
        p95_ms = entry.get_response_time_percentile(0.95)
        if p95_ms is None:
            continue

        if "fast-path" in label or "fast-path" in path:
            if p95_ms > _FAST_P95_BUDGET_MS:
                violations.append(
                    f"  FAST PATH p95 {p95_ms:.0f}ms > budget {_FAST_P95_BUDGET_MS}ms — {path}"
                )
        elif "cold-path" in label or "cold-path" in path:
            if p95_ms > _COLD_P95_BUDGET_MS:
                violations.append(
                    f"  COLD PATH p95 {p95_ms:.0f}ms > budget {_COLD_P95_BUDGET_MS}ms — {path}"
                )
        elif "stories" in path:
            if p95_ms > _STORY_P95_BUDGET_MS:
                violations.append(
                    f"  STORY DETAIL p95 {p95_ms:.0f}ms > budget {_STORY_P95_BUDGET_MS}ms — {path}"
                )

    if violations:
        print("\n⚠  LATENCY BUDGET VIOLATIONS:")
        for v in violations:
            print(v)
        environment.process_exit_code = 1
    else:
        print("\n✓ All latency budgets met.")
