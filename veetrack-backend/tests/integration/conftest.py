"""Shared configuration for integration tests.

All tests under tests/integration/ are automatically marked with
``pytest.mark.integration`` so CI can run them in a separate job:

  pytest tests/integration/          # only integration tests (needs live infra)
  pytest tests/unit/ -m "not integration"   # unit-only, no infra required
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-mark every test in this directory as 'integration'."""
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
