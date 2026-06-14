from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine


REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env.integration"


def _load_integration_env() -> None:
    if not ENV_FILE.exists():
        return
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _postgres_settings() -> dict[str, str]:
    _load_integration_env()
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": os.getenv("POSTGRES_PORT", "55432"),
        "database": os.getenv("POSTGRES_DB", "bugbounty_integration_test"),
        "user": os.getenv("POSTGRES_USER", "bugbounty_integration_test"),
        "password": os.getenv("POSTGRES_PASSWORD", "bugbounty_integration_test"),
    }


def _assert_integration_database(settings: dict[str, str]) -> None:
    database = settings["database"].lower()
    user = settings["user"].lower()
    host = settings["host"].lower()
    port = settings["port"]
    joined = " ".join([database, user, host, port])
    forbidden = ["prod", "production", "staging", "bugbounty_prod"]
    if any(token in joined for token in forbidden):
        raise RuntimeError(f"Refusing to run integration tests against {settings!r}")
    if "test" not in database and "integration" not in database:
        raise RuntimeError(
            "Integration POSTGRES_DB must contain 'test' or 'integration': "
            f"{settings['database']!r}"
        )
    if port in {"5432", "6432"} and host in {"localhost", "127.0.0.1", "postgres"}:
        raise RuntimeError(
            "Integration tests must not use the default Postgres port. "
            f"Got {host}:{port}."
        )


def _sync_url(settings: dict[str, str]) -> str:
    user = quote_plus(settings["user"])
    password = quote_plus(settings["password"])
    return (
        f"postgresql+psycopg2://{user}:{password}@"
        f"{settings['host']}:{settings['port']}/{settings['database']}"
    )


def _async_url(settings: dict[str, str]) -> str:
    user = quote_plus(settings["user"])
    password = quote_plus(settings["password"])
    return (
        f"postgresql+asyncpg://{user}:{password}@"
        f"{settings['host']}:{settings['port']}/{settings['database']}"
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: tests requiring isolated dockerized external services",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.getenv("RUN_INTEGRATION_TESTS") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_INTEGRATION_TESTS=1 to run integration tests")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def integration_postgres_settings() -> dict[str, str]:
    settings = _postgres_settings()
    _assert_integration_database(settings)
    return settings


@pytest.fixture(scope="session")
def integration_postgres_sync_url(integration_postgres_settings: dict[str, str]) -> str:
    return _sync_url(integration_postgres_settings)


@pytest.fixture(scope="session")
def integration_postgres_async_url(integration_postgres_settings: dict[str, str]) -> str:
    return _async_url(integration_postgres_settings)


@pytest.fixture(scope="session")
def migrated_postgres(integration_postgres_settings: dict[str, str]) -> dict[str, str]:
    for key, value in {
        "POSTGRES_HOST": integration_postgres_settings["host"],
        "POSTGRES_PORT": integration_postgres_settings["port"],
        "POSTGRES_DB": integration_postgres_settings["database"],
        "POSTGRES_USER": integration_postgres_settings["user"],
        "POSTGRES_PASSWORD": integration_postgres_settings["password"],
    }.items():
        os.environ[key] = value

    config = Config(str(REPO_ROOT / "alembic.ini"))
    command.upgrade(config, "head")
    return integration_postgres_settings


@pytest.fixture(scope="session")
def integration_sync_engine(
    migrated_postgres: dict[str, str],
    integration_postgres_sync_url: str,
):
    engine = create_engine(integration_postgres_sync_url, future=True)
    try:
        with engine.connect() as connection:
            database = connection.execute(text("select current_database()")).scalar_one()
        if database != migrated_postgres["database"]:
            raise RuntimeError(
                f"Connected to unexpected database {database!r}; "
                f"expected {migrated_postgres['database']!r}"
            )
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
async def integration_async_engine(
    migrated_postgres: dict[str, str],
    integration_postgres_async_url: str,
):
    engine = create_async_engine(integration_postgres_async_url, future=True)
    try:
        async with engine.connect() as connection:
            database = (await connection.execute(text("select current_database()"))).scalar_one()
        if database != migrated_postgres["database"]:
            raise RuntimeError(
                f"Connected to unexpected database {database!r}; "
                f"expected {migrated_postgres['database']!r}"
            )
        yield engine
    finally:
        await engine.dispose()
