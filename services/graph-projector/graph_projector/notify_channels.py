from __future__ import annotations

import re

_POSTGRES_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def validate_postgres_notify_channel(value: str, *, field_name: str = "channel") -> str:
    if not isinstance(value, str) or not _POSTGRES_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"unsafe PostgreSQL notify channel for {field_name}: {value!r}")
    return value


def listen_statement(channel: str) -> str:
    return f"LISTEN {validate_postgres_notify_channel(channel)};"
