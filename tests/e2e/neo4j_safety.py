from __future__ import annotations

import os
from urllib.parse import urlparse


def assert_neo4j_clear_allowed(*, uri: str, database: str, allow_env: str | None = None) -> None:
    allow_value = os.getenv("ALLOW_E2E_NEO4J_CLEAR") if allow_env is None else allow_env
    if is_integration_neo4j_uri(uri):
        return
    if is_test_name(database):
        return
    if allow_value == "1" and is_test_name(database):
        return
    raise RuntimeError(
        "Refusing to clear Neo4j because target is not clearly test-only: "
        f"uri={uri!r}, database={database!r}"
    )


def is_integration_neo4j_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    return parsed.hostname in {"localhost", "127.0.0.1"} and parsed.port == 57687


def is_test_name(value: str) -> bool:
    normalized = value.lower()
    return "test" in normalized or "integration" in normalized
