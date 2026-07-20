"""Architecture enforcement tests.

Ensure that the domain layer has no imports from infrastructure or API layers.
This is a structural guardrail — it catches accidental dependency inversions early.
"""

from __future__ import annotations

import ast
from pathlib import Path


def _get_imports(file_path: Path) -> list[str]:
    """Extract all top-level import module names from a Python source file."""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _all_python_files(directory: Path) -> list[Path]:
    return list(directory.rglob("*.py"))


DOMAIN_DIR = Path(__file__).parent.parent.parent / "app" / "domain"
FORBIDDEN_IN_DOMAIN = ["app.infrastructure", "app.api", "fastapi", "sqlalchemy", "redis"]


def test_domain_has_no_infrastructure_imports() -> None:
    """No file under app/domain/ may import from app.infrastructure or app.api."""
    violations: list[str] = []
    for py_file in _all_python_files(DOMAIN_DIR):
        imports = _get_imports(py_file)
        for imp in imports:
            for forbidden in FORBIDDEN_IN_DOMAIN:
                if imp.startswith(forbidden):
                    violations.append(f"{py_file.name}: imports '{imp}'")

    assert not violations, (
        "Domain layer dependency violation(s) detected:\n" + "\n".join(violations)
    )


APPLICATION_DIR = Path(__file__).parent.parent.parent / "app" / "application"
FORBIDDEN_IN_APPLICATION = ["app.infrastructure", "app.api", "fastapi", "sqlalchemy", "redis"]


def test_application_has_no_infrastructure_imports() -> None:
    """No file under app/application/ may import from app.infrastructure or app.api."""
    violations: list[str] = []
    for py_file in _all_python_files(APPLICATION_DIR):
        imports = _get_imports(py_file)
        for imp in imports:
            for forbidden in FORBIDDEN_IN_APPLICATION:
                if imp.startswith(forbidden):
                    violations.append(f"{py_file.name}: imports '{imp}'")

    assert not violations, (
        "Application layer dependency violation(s) detected:\n" + "\n".join(violations)
    )
