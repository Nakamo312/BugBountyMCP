from __future__ import annotations

from typing import Any, Mapping, Protocol
from uuid import UUID


class CursorLike(Protocol):
    def execute(self, query: str, parameters: dict[str, object] | None = None) -> object: ...
    def fetchall(self) -> list[Mapping[str, Any]]: ...
    def fetchone(self) -> Mapping[str, Any] | None: ...


class ConnectionLike(Protocol):
    def cursor(self) -> CursorLike: ...


def cursor_for(connection: ConnectionLike) -> CursorLike:
    """Return a plain cursor without entering context-managed cursor objects.

    Callers that need deterministic cursor closing must use their driver's
    context manager directly. This helper intentionally avoids calling
    ``__enter__`` because it cannot also guarantee the matching ``__exit__``.
    """

    return connection.cursor()


def fetchall(connection: ConnectionLike, query: str, parameters: dict[str, object], *, rollback_on_error: bool = False) -> list[Mapping[str, Any]]:
    cursor = cursor_for(connection)
    try:
        cursor.execute(query, parameters)
        return list(cursor.fetchall())
    except Exception:
        if rollback_on_error and hasattr(connection, "rollback"):
            connection.rollback()
        raise


def required_uuid_value(value: Any, name: str) -> UUID:
    if isinstance(value, UUID):
        return value
    if value is None:
        raise ValueError(f"{name} must not be empty")
    return UUID(str(value))


def required_row_uuid(row: Mapping[str, Any], key: str, *, context: str = "row") -> UUID:
    value = optional_uuid(row.get(key))
    if value is None:
        raise ValueError(f"{context} requires {key}")
    return value


def optional_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def optional_uuid_text(value: Any) -> str | None:
    uuid_value = optional_uuid(value)
    return str(uuid_value) if uuid_value is not None else None


def required_text_value(value: Any, name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{name} must not be empty")
    return text


def required_row_text(row: Mapping[str, Any], key: str, *, context: str = "row") -> str:
    text = optional_text(row.get(key))
    if text is None:
        raise ValueError(f"{context} requires non-empty {key}")
    return text


def optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def adapt_json_parameters_for_cursor(cursor: CursorLike, parameters: dict[str, object], *, json_keys: set[str] | frozenset[str]) -> dict[str, object]:
    if not any(key in parameters for key in json_keys):
        return parameters
    if not is_psycopg2_cursor(cursor):
        return parameters
    try:
        from psycopg2.extras import Json
    except ModuleNotFoundError:
        Json = _JsonAdapterFallback
    adapted = dict(parameters)
    for key in json_keys:
        if key in adapted:
            adapted[key] = Json(adapted[key])
    return adapted


def is_psycopg2_cursor(cursor: CursorLike) -> bool:
    module = cursor.__class__.__module__
    return module == "psycopg2" or module.startswith("psycopg2.")


class _JsonAdapterFallback:
    def __init__(self, value: object) -> None:
        self.adapted = value
