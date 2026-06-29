from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CliSettings:
    """Environment-backed CLI defaults.

    The CLI is a control-plane client. It must talk to the public API and must
    not connect directly to Postgres, Neo4j, LangGraph, RabbitMQ, or runners.
    """

    api_url: str = "http://localhost:8000"
    api_prefix: str = "/api/v1"
    api_token: str | None = None
    agent_internal_token: str | None = None
    program_id: UUID | None = None
    campaign_id: UUID | None = None
    created_by: str = "cli"
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "CliSettings":
        return cls(
            api_url=_strip_trailing_slash(os.getenv("BB_API_URL", "http://localhost:8000")),
            api_prefix=_normalize_prefix(os.getenv("BB_API_PREFIX", "/api/v1")),
            api_token=_optional_text(os.getenv("BB_API_TOKEN")),
            agent_internal_token=_optional_text(os.getenv("BB_AGENT_INTERNAL_TOKEN"))
            or _optional_text(os.getenv("AGENT_PROTOCOL_INTERNAL_TOKEN")),
            program_id=_optional_uuid(os.getenv("BB_PROGRAM_ID")),
            campaign_id=_optional_uuid(os.getenv("BB_CAMPAIGN_ID")),
            created_by=_optional_text(os.getenv("BB_CREATED_BY")) or "cli",
            timeout_seconds=_float_env("BB_TIMEOUT_SECONDS", default=30.0),
        )

    @property
    def base_url(self) -> str:
        return f"{self.api_url}{self.api_prefix}"


def _strip_trailing_slash(value: str) -> str:
    stripped = value.strip()
    return stripped[:-1] if stripped.endswith("/") else stripped


def _normalize_prefix(value: str) -> str:
    stripped = value.strip() or "/api/v1"
    if not stripped.startswith("/"):
        stripped = f"/{stripped}"
    return stripped[:-1] if stripped.endswith("/") else stripped


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _optional_uuid(value: str | None) -> UUID | None:
    stripped = _optional_text(value)
    if stripped is None:
        return None
    return UUID(stripped)


def _float_env(name: str, *, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
