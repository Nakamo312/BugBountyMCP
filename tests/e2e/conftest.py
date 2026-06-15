from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env.integration"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "e2e: tests requiring isolated Postgres and Neo4j services",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.getenv("RUN_E2E_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_E2E_TESTS=1 to run e2e tests")
    for item in items:
        if item.get_closest_marker("e2e") is not None:
            item.add_marker(skip)


def _load_env() -> None:
    if not ENV_FILE.exists():
        return
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _postgres_settings() -> dict[str, str]:
    _load_env()
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "55432"),
        "database": os.getenv("POSTGRES_DB", "bugbounty_integration_test"),
        "user": os.getenv("POSTGRES_USER", "bugbounty_integration_test"),
        "password": os.getenv("POSTGRES_PASSWORD", "bugbounty_integration_test"),
    }


def _assert_e2e_database(settings: dict[str, str]) -> None:
    database = settings["database"].lower()
    user = settings["user"].lower()
    host = settings["host"].lower()
    port = settings["port"]
    joined = " ".join([database, user, host, port])
    forbidden = ["prod", "production", "staging", "bugbounty_prod"]
    if any(token in joined for token in forbidden):
        raise RuntimeError(f"Refusing to run e2e tests against {settings!r}")
    if "test" not in database and "integration" not in database:
        raise RuntimeError(
            "E2E POSTGRES_DB must contain 'test' or 'integration': "
            f"{settings['database']!r}"
        )
    if port in {"5432", "6432"} and host in {"localhost", "127.0.0.1", "postgres"}:
        raise RuntimeError(
            "E2E tests must not use the default Postgres port. "
            f"Got {host}:{port}."
        )


def _sync_url(settings: dict[str, str]) -> str:
    user = quote_plus(settings["user"])
    password = quote_plus(settings["password"])
    return (
        f"postgresql+psycopg2://{user}:{password}@"
        f"{settings['host']}:{settings['port']}/{settings['database']}"
    )


def _assert_neo4j_clear_allowed(*, uri: str, database: str, allow_env: str | None = None) -> None:
    allow_value = os.getenv("ALLOW_E2E_NEO4J_CLEAR") if allow_env is None else allow_env
    if _is_integration_neo4j_uri(uri):
        return
    if _is_test_name(database):
        return
    if allow_value == "1" and _is_test_name(database):
        return
    raise RuntimeError(
        "Refusing to clear Neo4j because target is not clearly test-only: "
        f"uri={uri!r}, database={database!r}"
    )


def _is_integration_neo4j_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    return parsed.hostname in {"localhost", "127.0.0.1"} and parsed.port == 57687


def _is_test_name(value: str) -> bool:
    normalized = value.lower()
    return "test" in normalized or "integration" in normalized


@pytest.fixture(scope="session")
def e2e_postgres_settings() -> dict[str, str]:
    settings = _postgres_settings()
    _assert_e2e_database(settings)
    return settings


@pytest.fixture(scope="session")
def e2e_postgres_url(e2e_postgres_settings: dict[str, str]) -> str:
    return _sync_url(e2e_postgres_settings)


@pytest.fixture(scope="session")
def e2e_postgres_engine(
    e2e_postgres_settings: dict[str, str],
    e2e_postgres_url: str,
):
    for key, value in {
        "POSTGRES_HOST": e2e_postgres_settings["host"],
        "POSTGRES_PORT": e2e_postgres_settings["port"],
        "POSTGRES_DB": e2e_postgres_settings["database"],
        "POSTGRES_USER": e2e_postgres_settings["user"],
        "POSTGRES_PASSWORD": e2e_postgres_settings["password"],
        "DATABASE_URL": e2e_postgres_url.replace("postgresql+psycopg2://", "postgresql://"),
    }.items():
        os.environ[key] = value

    config = Config(str(REPO_ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(e2e_postgres_url, future=True)
    try:
        with engine.connect() as connection:
            database = connection.execute(text("select current_database()")).scalar_one()
        if database != e2e_postgres_settings["database"]:
            raise RuntimeError(
                f"Connected to unexpected database {database!r}; "
                f"expected {e2e_postgres_settings['database']!r}"
            )
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def e2e_neo4j_database() -> str:
    _load_env()
    return os.getenv("NEO4J_DATABASE", "neo4j")


@pytest.fixture(scope="session")
def e2e_neo4j_driver(e2e_neo4j_database: str):
    _load_env()
    from neo4j import GraphDatabase

    if os.getenv("RUN_E2E_TESTS") != "1":
        raise RuntimeError("Refusing to initialize e2e Neo4j driver without RUN_E2E_TESTS=1")
    uri = os.getenv("NEO4J_URI", f"bolt://localhost:{os.getenv('NEO4J_BOLT_PORT', '57687')}")
    _assert_neo4j_clear_allowed(
        uri=uri,
        database=e2e_neo4j_database,
    )
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "bugbounty-integration-test")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
        with driver.session(database=e2e_neo4j_database) as session:
            session.run("MATCH (n) DETACH DELETE n").consume()
        yield driver
    finally:
        driver.close()
