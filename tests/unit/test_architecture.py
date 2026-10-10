"""Erzwingt die Schichtenregeln aus Architekturvorgabe 3.2 und Entwicklungsregeln 2.1."""

import ast
import re
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "src" / "meine_kasse"

FORBIDDEN_IMPORTS = {
    "domain": ("meine_kasse.application", "meine_kasse.infrastructure", "meine_kasse.presentation"),
    "application": ("meine_kasse.infrastructure", "meine_kasse.presentation"),
    "presentation": ("meine_kasse.infrastructure",),
}
THIRD_PARTY_FORBIDDEN = {
    "domain": ("sqlalchemy", "PySide6", "alembic", "argon2"),
    "application": ("sqlalchemy", "PySide6", "alembic", "argon2"),
    "presentation": ("sqlalchemy", "alembic", "argon2"),
}


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


@pytest.mark.parametrize("layer", sorted(FORBIDDEN_IMPORTS))
def test_layer_imports(layer: str) -> None:
    violations = []
    for path in (SOURCE / layer).rglob("*.py"):
        for name in _imports(path):
            forbidden = FORBIDDEN_IMPORTS[layer] + THIRD_PARTY_FORBIDDEN[layer]
            if name.startswith(forbidden):
                violations.append(f"{path.relative_to(SOURCE)} importiert {name}")
    assert not violations, "\n".join(violations)


def test_no_float_annotations_for_money() -> None:
    offenders = []
    for path in SOURCE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.arg) and node.annotation is not None:
                if "float" in ast.unparse(node.annotation) and "cent" in node.arg:
                    offenders.append(f"{path.relative_to(SOURCE)}: {node.arg}")
    assert not offenders, "\n".join(offenders)


def test_sql_only_in_infrastructure() -> None:
    sql_patterns = (
        re.compile(r"exec_driver_sql|sqlite3|(?<![\w.])text\("),
        re.compile(r"\b(SELECT\s.+\sFROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b"),
    )
    offenders = []
    for path in SOURCE.rglob("*.py"):
        relative = path.relative_to(SOURCE).as_posix()
        if relative.startswith("infrastructure/"):
            continue
        content = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{relative}: {pattern.pattern}" for pattern in sql_patterns if pattern.search(content)
        )
    assert not offenders, "\n".join(offenders)
