from __future__ import annotations

from ipaddress import ip_address
from uuid import UUID


def canonical_inventory_dedupe_key(program_id: UUID | str, parser_version: str) -> str:
    return f"canonical-inventory:{program_id}:{parser_version}"


def inventory_service_key(*, ip: str, port: int, scheme: str) -> str:
    return f"{canonical_ip_address(ip)}:{int(port)}/{scheme.strip().lower()}"


def canonical_ip_address(value: str) -> str:
    text = value.strip()
    try:
        return str(ip_address(text))
    except ValueError:
        return text
