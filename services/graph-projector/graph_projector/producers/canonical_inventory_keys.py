from __future__ import annotations

from ipaddress import ip_address
from uuid import UUID


def canonical_inventory_dedupe_key(program_id: UUID | str, parser_version: str) -> str:
    return f"canonical-inventory:{program_id}:{parser_version}"


def inventory_service_key(*, origin: str, port: int, scheme: str) -> str:
    return f"{canonical_service_origin(origin)}:{int(port)}/{scheme.strip().lower()}"


def canonical_service_origin(value: str) -> str:
    text = value.strip().lower().rstrip(".")
    if not text:
        return text
    return canonical_ip_address(text)


def canonical_ip_address(value: str) -> str:
    text = value.strip()
    try:
        return str(ip_address(text))
    except ValueError:
        return text
