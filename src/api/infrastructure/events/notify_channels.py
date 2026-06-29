"""PostgreSQL NOTIFY channel validation helpers."""
from __future__ import annotations

import re

_POSTGRES_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def validate_postgres_notify_channel(value: str, *, field_name: str = "notify_channel") -> str:
    """Return a channel name that is safe for LISTEN/NOTIFY wiring.

    PostgreSQL treats channel names as identifiers in LISTEN/NOTIFY commands,
    while pg_notify accepts the channel as text. Keeping the same identifier
    contract for both sides prevents config drift and avoids allowing arbitrary
    SQL-shaped names at the boundary.
    """

    if not isinstance(value, str) or not _POSTGRES_IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"unsafe PostgreSQL notify channel for {field_name}: {value!r}")
    return value
