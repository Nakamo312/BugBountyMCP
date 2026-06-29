from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID

from ..row_codec import (
    optional_text,
    optional_uuid_text,
    required_row_uuid,
)
from .canonical_inventory_keys import canonical_ip_address, inventory_service_key


@dataclass(frozen=True)
class CanonicalInventoryRow:
    program_id: UUID
    host_id: str | None
    hostname: str
    ip_id: str | None
    ip_address: str
    host_ip_source: str | None
    service: tuple[str, str, int] | None
    service_id: str | None
    technologies: list[str]


def parse_canonical_inventory_row(row: Mapping[str, Any]) -> CanonicalInventoryRow | None:
    hostname = _optional_hostname(row.get("hostname"))
    ip_address = _optional_ip_address(row.get("ip_address"))
    if hostname is None or ip_address is None:
        return None
    return CanonicalInventoryRow(
        program_id=required_row_uuid(row, "program_id", context="canonical inventory row"),
        host_id=optional_uuid_text(row.get("host_id")),
        hostname=hostname,
        ip_id=optional_uuid_text(row.get("ip_id")),
        ip_address=ip_address,
        host_ip_source=optional_text(row.get("host_ip_source")),
        service=_optional_service(row, ip_address),
        service_id=optional_uuid_text(row.get("service_id")),
        technologies=_technology_names(row.get("technologies")),
    )


def _optional_hostname(value: Any) -> str | None:
    text = optional_text(value)
    if text is None:
        return None
    hostname = text.lower().rstrip(".")
    return hostname or None


def _optional_ip_address(value: Any) -> str | None:
    text = optional_text(value)
    if text is None:
        return None
    return canonical_ip_address(text)


def _optional_service(row: Mapping[str, Any], ip_address: str) -> tuple[str, str, int] | None:
    if row.get("service_id") is None and row.get("service_scheme") is None and row.get("service_port") is None:
        return None
    scheme = optional_text(row.get("service_scheme"))
    if scheme is None or row.get("service_port") is None:
        return None
    port = int(row["service_port"])
    scheme = scheme.lower()
    return inventory_service_key(ip=ip_address, port=port, scheme=scheme), scheme, port


def _technology_names(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return sorted(str(key).strip().lower() for key, enabled in value.items() if enabled and str(key).strip())
    if isinstance(value, (list, tuple, set)):
        return sorted(str(item).strip().lower() for item in value if str(item).strip())
    text = optional_text(value)
    return [text.lower()] if text is not None else []
